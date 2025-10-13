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
        offerer_id = None
        if room and len(room.peers) == 1:
            offerer_id = peer.id
        elif room and len(room.peers) == 2:
            # Define offerer (earliest peer)
            sorted_peers = sorted(room.peers.values(), key=lambda p: p.joined_at)
            offerer_id = sorted_peers[0].id
            # Notify both peers they are ready
            for p in room.peers.values():
                await p.ws.send_json({"type": "ready", "id": p.id, "offerer": offerer_id})
            print(f"[WS] ready broadcast room={room_id} offerer={offerer_id}")
            # If names already known, forward them to the counterpart
            a, b = sorted_peers[0], sorted_peers[1]
            if a.name:
                try:
                    await b.ws.send_json({"type": "peer-info", "id": a.id, "name": a.name})
                    print(f"[WS] late peer-info -> {b.id} name={a.name}")
                except Exception as e:
                    print(f"[WS] failed late peer-info a->b: {e}")
            if b.name:
                try:
                    await a.ws.send_json({"type": "peer-info", "id": b.id, "name": b.name})
                    print(f"[WS] late peer-info -> {a.id} name={b.name}")
                except Exception as e:
                    print(f"[WS] failed late peer-info b->a: {e}")

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            room = await rooms.get_room(room_id)
            if not room:
                print(f"[WS] room missing room={room_id} peer={peer.id}")
                break

            other = room.other_peer(peer.id)

            if msg_type == "hello":
                # Store peer display name and forward to the other peer (if present)
                peer.name = msg.get("name") or None
                print(f"[WS] hello room={room_id} peer={peer.id} name={peer.name}")
                if other:
                    try:
                        await other.ws.send_json({
                            "type": "peer-info",
                            "id": peer.id,
                            "name": peer.name or ""
                        })
                        print(f"[WS] forwarded peer-info room={room_id} from={peer.id} to={other.id} name={peer.name}")
                    except Exception as e:
                        print(f"[WS] failed to send peer-info: {e}")
                continue

            if not other:
                # Waiting for the second peer
                print(f"[WS] no other yet room={room_id} peer={peer.id} msg={msg_type}")
                continue

            if msg_type in ("offer", "answer", "ice"):
                await other.ws.send_json({
                    "type": msg_type,
                    "from": peer.id,
                    "data": msg.get("data")
                })
                print(f"[WS] relay {msg_type} room={room_id} from={peer.id} to={other.id}")
            elif msg_type == "bye":
                await other.ws.send_json({"type": "bye"})
                print(f"[WS] bye room={room_id} from={peer.id} to={other.id}")
    except WebSocketDisconnect:
        print(f"[WS] disconnect room={room_id} peer={peer.id}")
    finally:
        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            other = room.other_peer(peer.id)
            if other:
                try:
                    await other.ws.send_json({"type": "peer-left"})
                    print(f"[WS] peer-left room={room_id} from={peer.id} to={other.id}")
                except Exception as e:
                    print(f"[WS] failed to send peer-left: {e}")