import asyncio
import secrets
from dataclasses import dataclass
from typing import Dict, Optional, List


@dataclass
class Peer:
    id: str
    ws: any  ## WebSocket
    joined_at: float
    name: Optional[str] = None  ## display name (sent by client)
    uid: Optional[str] = None   ## stable user identity (tg_user_id or client id)
    avatar: Optional[str] = None  ## avatar url if any


@dataclass
class Room:
    peers: Dict[str, Peer]
    owner_uid: Optional[str] = None  ## room owner identity (first user hello with uid)

    def other_peer(self, pid: str):
        for k, p in self.peers.items():
            if k != pid:
                return p
        return None

    def list_peers_except(self, pid: str) -> List[Peer]:
        return [p for k, p in self.peers.items() if k != pid]

    def find_by_uid(self, uid: str) -> Optional[Peer]:
        for p in self.peers.values():
            if p.uid and p.uid == uid:
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

