from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.utils.rooms import RoomManager

router = APIRouter()
rooms = RoomManager()


@router.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str):
    await websocket.accept()
    peer = await rooms.join(room_id, websocket)
    try:
        room = await rooms.get_room(room_id)
        offerer_id = None
        if room and len(room.peers) == 1:
            offerer_id = peer.id
        elif room and len(room.peers) == 2:
            sorted_peers = sorted(room.peers.values(), key=lambda p: p.joined_at)
            offerer_id = sorted_peers[0].id
            for p in room.peers.values():
                await p.ws.send_json({"type": "ready", "id": p.id, "offerer": offerer_id})

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            room = await rooms.get_room(room_id)
            if not room:
                break
            other = room.other_peer(peer.id)
            if not other:
                continue

            if msg_type in ("offer", "answer", "ice"):
                await other.ws.send_json({
                    "type": msg_type,
                    "from": peer.id,
                    "data": msg.get("data")
                })
            elif msg_type == "bye":
                await other.ws.send_json({"type": "bye"})
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            other = room.other_peer(peer.id)
            if other:
                try:
                    await other.ws.send_json({"type": "peer-left"})
                except Exception:
                    pass

