import asyncio
import secrets
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Peer:
    id: str
    ws: any  # WebSocket
    joined_at: float
    name: Optional[str] = None  # display name (sent by client)


@dataclass
class Room:
    peers: Dict[str, Peer]

    def other_peer(self, pid: str):
        for k, p in self.peers.items():
            if k != pid:
                return p
        return None


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.lock = asyncio.Lock()

    async def join(self, room_id: str, ws):
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                room = Room(peers={})
                self.rooms[room_id] = room
            pid = secrets.token_hex(4)
            peer = Peer(id=pid, ws=ws, joined_at=asyncio.get_event_loop().time())
            room.peers[pid] = peer
            return peer

    async def leave(self, room_id: str, pid: str):
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return
            room.peers.pop(pid, None)
            if not room.peers:
                self.rooms.pop(room_id, None)

    async def get_room(self, room_id: str):
        async with self.lock:
            return self.rooms.get(room_id)