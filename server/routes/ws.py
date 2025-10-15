## WebSocket signaling route with recording broadcast support and call logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.utils.rooms import RoomManager
from server.db import calls as callsdb

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
                "peers": [
                    {
                        "id": p.id,
                        "name": p.name or "",
                        "avatar": p.avatar or "",
                        "uid": p.uid or ""
                    } for p in existing
                ]
            })
            for p in existing:
                try:
                    await p.ws.send_json({
                        "type": "peer-joined",
                        "id": peer.id,
                        "name": peer.name or "",
                        "avatar": peer.avatar or "",
                        "uid": peer.uid or "",
                        "owner_uid": room.owner_uid or ""
                    })
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
                is_owner = bool(msg.get("is_owner"))

                ## Owner assignment (only first claim)
                if is_owner and peer.uid and not room.owner_uid:
                    room.owner_uid = peer.uid
                    print(f"[WS] owner set room={room_id} owner_uid={room.owner_uid}")
                    ## create call session in DB
                    try:
                        call_id = await callsdb.create_call_if_absent(room_id, room.owner_uid)
                        setattr(room, "call_id", call_id)
                    except Exception as e:
                        print(f"[WS] call create failed: {e}")
                    for p in room.peers.values():
                        try:
                            await p.ws.send_json({"type": "owner-set", "owner_uid": room.owner_uid})
                        except Exception as e:
                            print(f"[WS] failed to send owner-set to={p.id}: {e}")

                print(f"[WS] hello room={room_id} peer={peer.id} name={peer.name} uid={peer.uid} is_owner={is_owner}")

                ## participants accounting for non-owner
                if peer.uid and room.owner_uid and peer.uid != room.owner_uid:
                    try:
                        call_id = getattr(room, "call_id", None)
                        if not call_id and room.owner_uid:
                            call_id = await callsdb.create_call_if_absent(room_id, room.owner_uid)
                            setattr(room, "call_id", call_id)
                        if call_id:
                            await callsdb.participant_join(call_id, peer.uid, peer.name or "", peer.avatar or "")
                            await callsdb.mark_call_active(call_id)
                    except Exception as e:
                        print(f"[WS] participant join log failed: {e}")

                for p in room.list_peers_except(peer.id):
                    try:
                        await p.ws.send_json({
                            "type": "peer-info",
                            "id": peer.id,
                            "name": peer.name or "",
                            "avatar": peer.avatar or "",
                            "uid": peer.uid or ""
                        })
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
                        print(f"[WS] relay skip unknown target room={room_id} from={peer.id} to={target}")
                else:
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

            ## Recording broadcast (owner only)
            if msg_type in ("record-start", "record-pause", "record-resume", "record-stop"):
                if peer.uid and room.owner_uid and peer.uid == room.owner_uid:
                    payload = {
                        "type": msg_type,
                        "owner_uid": room.owner_uid,
                        "timestamp": msg.get("timestamp") or ""
                    }
                    for p in room.list_peers_except(peer.id):
                        try:
                            await p.ws.send_json(payload)
                        except Exception as e:
                            print(f"[WS] failed record broadcast type={msg_type} to={p.id}: {e}")
                    try:
                        call_id = getattr(room, "call_id", None)
                        if call_id:
                            evmap = {
                                "record-start": "record_start",
                                "record-pause": "record_pause",
                                "record-resume": "record_resume",
                                "record-stop": "record_stop",
                            }
                            await callsdb.add_event(call_id, None, evmap.get(msg_type, "record"), {"ts": payload["timestamp"]})
                    except Exception as e:
                        print(f"[WS] record event log failed: {e}")
                else:
                    print(f"[WS] record attempt denied (not owner) room={room_id} peer={peer.id}")
                continue

            print(f"[WS] ignore msg type={msg_type} room={room_id} peer={peer.id}")
    except WebSocketDisconnect:
        print(f"[WS] disconnect room={room_id} peer={peer.id}")
    finally:
        try:
            room = await rooms.get_room(room_id)
            call_id = getattr(room, "call_id", None) if room else None
            if call_id and peer.uid:
                if room and room.owner_uid and peer.uid == room.owner_uid:
                    await callsdb.finalize_call(call_id, ended_reason="owner_leave")
                else:
                    await callsdb.participant_leave(call_id, peer.uid, None)
                    if room:
                        other_non_owner = 0
                        for pid, p in room.peers.items():
                            if p.uid and room.owner_uid and p.uid != room.owner_uid and pid != peer.id:
                                other_non_owner += 1
                        if other_non_owner == 0 and room.owner_uid:
                            await callsdb.finalize_call(call_id, ended_reason="no_peers_left")
        except Exception as e:
            print(f"[WS] finalize/leave log failed: {e}")

        await rooms.leave(room_id, peer.id)
        room = await rooms.get_room(room_id)
        if room:
            for p in room.list_peers_except(peer.id):
                try:
                    await p.ws.send_json({"type": "peer-left", "id": peer.id})
                    print(f"[WS] peer-left room={room_id} from={peer.id} to={p.id}")
                except Exception as e:
                    print(f"[WS] failed to send peer-left to={p.id}: {e}")

