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
            # Send the new peer a list of existing peers (with known names)
            existing = room.list_peers_except(peer.id)
            await websocket.send_json({
                "type": "peers",
                "peers": [{"id": p.id, "name": p.name or ""} for p in existing]
            })
            # Notify others that a new peer joined
            for p in existing:
                try:
                    await p.ws.send_json({"type": "peer-joined", "id": peer.id, "name": peer.name or ""})
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
                # Store peer display name and inform others
                peer.name = msg.get("name") or None
                print(f"[WS] hello room={room_id} peer={peer.id} name={peer.name}")
                for p in room.list_peers_except(peer.id):
                    try:
                        await p.ws.send_json({"type": "peer-info", "id": peer.id, "name": peer.name or ""})
                    except Exception as e:
                        print(f"[WS] failed to send peer-info to={p.id}: {e}")
                continue

            # Addressed signaling (mesh): offer/answer/ice carry "to"
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
                    # Backward compatibility for 1:1 clients without "to"
                    other = room.other_peer(peer.id)
                    if other:
                        try:
                            await other.ws.send_json({"type": msg_type, "from": peer.id, "data": data})
                            print(f"[WS] relay(1to1) {msg_type} room={room_id} from={peer.id} to={other.id}")
                        except Exception as e:
                            print(f"[WS] relay(1to1) error {msg_type} room={room_id} from={peer.id}: {e}")
                continue

            if msg_type == "bye":
                # Inform everyone that this peer is hanging up
                for p in room.list_peers_except(peer.id):
                    try:
                        await p.ws.send_json({"type": "bye", "id": peer.id})
                        print(f"[WS] bye room={room_id} from={peer.id} to={p.id}")
                    except Exception as e:
                        print(f"[WS] failed to send bye to={p.id}: {e}")
                continue

            # Optional: ignore unknown types
            print(f"[WS] ignore msg type={msg_type} room={room_id} peer={peer.id}")
    except WebSocketDisconnect:
        print(f"[WS] disconnect room={room_id} peer={peer.id}")
    finally:
        # Notify others about leaving
        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            for p in room.list_peers_except(peer.id):
                try:
                    await p.ws.send_json({"type": "peer-left", "id": peer.id})
                    print(f"[WS] peer-left room={room_id} from={peer.id} to={p.id}")
                except Exception as e:
                    print(f"[WS] failed to send peer-left to={p.id}: {e}")