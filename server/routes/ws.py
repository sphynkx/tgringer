import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.utils.rooms import RoomManager

router = APIRouter()
rooms = RoomManager()
log = logging.getLogger("tgringer.ws")


@router.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str):
    await websocket.accept()
    peer = await rooms.join(room_id, websocket)
    log.info("WS: joined room=%s peer=%s", room_id, peer.id)
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
            log.info("WS: ready broadcast room=%s offerer=%s", room_id, offerer_id)

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            room = await rooms.get_room(room_id)
            if not room:
                log.info("WS: room missing room=%s peer=%s", room_id, peer.id)
                break

            other = room.other_peer(peer.id)

            if msg_type == "hello":
                # Store peer display name and forward to the other peer
                peer.name = msg.get("name") or None
                if other:
                    try:
                        await other.ws.send_json({
                            "type": "peer-info",
                            "id": peer.id,
                            "name": peer.name or ""
                        })
                        log.info("WS: forwarded peer-info room=%s from=%s to=%s name=%s",
                                 room_id, peer.id, other.id, peer.name)
                    except Exception as e:
                        log.warning("WS: failed to send peer-info: %s", e)
                continue

            if not other:
                log.debug("WS: no other yet in room=%s peer=%s msg=%s", room_id, peer.id, msg_type)
                continue

            if msg_type in ("offer", "answer", "ice"):
                await other.ws.send_json({
                    "type": msg_type,
                    "from": peer.id,
                    "data": msg.get("data")
                })
                log.debug("WS: relay %s room=%s from=%s to=%s", msg_type, room_id, peer.id, other.id)
            elif msg_type == "bye":
                await other.ws.send_json({"type": "bye"})
                log.info("WS: bye room=%s from=%s to=%s", room_id, peer.id, other.id)
    except WebSocketDisconnect:
        log.info("WS: disconnect room=%s peer=%s", room_id, peer.id)
    finally:
        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            other = room.other_peer(peer.id)
            if other:
                try:
                    await other.ws.send_json({"type": "peer-left"})
                    log.info("WS: peer-left room=%s from=%s to=%s", room_id, peer.id, other.id)
                except Exception as e:
                    log.warning("WS: failed to send peer-left: %s", e)