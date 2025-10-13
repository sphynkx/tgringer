from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.utils.rooms import RoomManager

router = APIRouter()
rooms = RoomManager()


@router.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str):
    await websocket.accept()
    peer = await rooms.join(room_id, websocket)
    print(f"[WS] joined room={room_id} peer={peer.id}")
    try:
        room = await rooms.get_room(room_id)
        if room:
            existing = room.list_peers_except(peer.id)
            await websocket.send_json({
                "type": "peers",
                "owner_uid": room.owner_uid or "",
                "peers": [{"id": p.id, "name": p.name or "", "avatar": p.avatar or "", "uid": p.uid or ""} for p in existing]
            })
            for p in existing:
                try:
                    await p.ws.send_json({"type": "peer-joined", "id": peer.id, "name": peer.name or "", "avatar": peer.avatar or "", "uid": peer.uid or ""})
                except Exception as e:
                    print(f"[WS] failed peer-joined notify to={p.id}: {e}")

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            room = await rooms.get_room(room_id)
            if not room:
                print(f"[WS] room missing room={room_id} peer={peer.id}")
                break

            if msg_type == "hello":
                peer.name = msg.get("name") or None
                peer.uid = (msg.get("uid") or "").strip() or None
                peer.avatar = msg.get("avatar") or None

                # Enforce uniqueness by uid
                if peer.uid:
                    conflict = room.find_by_uid(peer.uid)
                    if conflict and conflict.id != peer.id:
                        # Duplicate identity detected
                        try:
                            await websocket.send_json({"type": "error", "code": "duplicate", "message": "Already connected"})
                        except Exception:
                            pass
                        print(f"[WS] duplicate uid, closing room={room_id} uid={peer.uid} existing={conflict.id} new={peer.id}")
                        await websocket.close()
                        break

                    # Set owner on first uid that arrives
                    if not room.owner_uid:
                        room.owner_uid = peer.uid
                        print(f"[WS] owner set room={room_id} owner_uid={room.owner_uid}")

                print(f"[WS] hello room={room_id} peer={peer.id} name={peer.name} uid={peer.uid}")
                # Inform others
                for p in room.list_peers_except(peer.id):
                    try:
                        await p.ws.send_json({"type": "peer-info", "id": peer.id, "name": peer.name or "", "avatar": peer.avatar or "", "uid": peer.uid or ""})
                    except Exception as e:
                        print(f"[WS] failed to send peer-info to={p.id}: {e}")
                continue

            if msg_type in ("offer", "answer", "ice"):
                target = msg.get("to")
                data = msg.get("data")
                if target:
                    dst = room.peers.get(target)
                    if dst:
                        try:
                            await dst.ws.send_json({"type": msg_type, "from": peer.id, "data": data})
                            print(f"[WS] relay {msg_type} room={room_id} from={peer.id} to={dst.id}")
                        except Exception as e:
                            print(f"[WS] relay error {msg_type} room={room_id} from={peer.id} to={target}: {e}")
                    else:
                        print(f"[WS] relay skip, unknown target room={room_id} from={peer.id} to={target}")
                else:
                    # 1:1 fallback for legacy clients
                    other = room.other_peer(peer.id)
                    if other:
                        try:
                            await other.ws.send_json({"type": msg_type, "from": peer.id, "data": data})
                            print(f"[WS] relay(1to1) {msg_type} room={room_id} from={peer.id} to={other.id}")
                        except Exception as e:
                            print(f"[WS] relay(1to1) error {msg_type} room={room_id} from={peer.id}: {e}")
                continue

            if msg_type == "bye":
                for p in room.list_peers_except(peer.id):
                    try:
                        await p.ws.send_json({"type": "bye", "id": peer.id})
                        print(f"[WS] bye room={room_id} from={peer.id} to={p.id}")
                    except Exception as e:
                        print(f"[WS] failed to send bye to={p.id}: {e}")
                continue

            print(f"[WS] ignore msg type={msg_type} room={room_id} peer={peer.id}")
    except WebSocketDisconnect:
        print(f"[WS] disconnect room={room_id} peer={peer.id}")
    finally:
        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            for p in room.list_peers_except(peer.id):
                try:
                    await p.ws.send_json({"type": "peer-left", "id": peer.id})
                    print(f"[WS] peer-left room={room_id} from={peer.id} to={p.id}")
                except Exception as e:
                    print(f"[WS] failed to send peer-left to={p.id}: {e}")