## DB helpers for recording routes: owner resolution and call resolution
## All DB access is centralized here.

from typing import Optional

from server.db import get_pool
from server.db import calls as callsdb


async def fallback_owner_uid(room_uid: str) -> Optional[str]:
    """
    Best-effort resolve current or last owner Telegram user id (tg_user_id) for the room.
    - Prefer an active (not ended) call for the room
    - Otherwise, take the most recent call's owner
    Returns tg_user_id as string, or None.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                ## Prefer active call owner
                await cur.execute(
                    "SELECT u.tg_user_id "
                    "FROM call_logs cl "
                    "JOIN users u ON u.id = cl.owner_id "
                    "WHERE cl.room_uid=%s AND cl.ended_at IS NULL "
                    "ORDER BY cl.started_at DESC LIMIT 1",
                    (room_uid,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])

                ## Otherwise, last call owner
                await cur.execute(
                    "SELECT u.tg_user_id "
                    "FROM call_logs cl "
                    "JOIN users u ON u.id = cl.owner_id "
                    "WHERE cl.room_uid=%s "
                    "ORDER BY cl.started_at DESC LIMIT 1",
                    (room_uid,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])
    except Exception as e:
        print(f"[DB:recording] fallback_owner_uid failed (ignored): {e}")
    return None


async def resolve_call_id(room_uid: str, owner_tg_uid: str, rec_started_ts: int) -> Optional[int]:
    """
    Resolve call_logs.id for (room_uid, owner), preferring a not-ended call.
    If none active, pick the latest call started at or before recording start time.
    Returns call_logs.id or None.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                owner_id = await callsdb.get_user_id_by_tg(owner_tg_uid)
                if not owner_id:
                    return None

                ## Prefer active call
                await cur.execute(
                    "SELECT id FROM call_logs "
                    "WHERE room_uid=%s AND owner_id=%s AND ended_at IS NULL "
                    "ORDER BY started_at DESC LIMIT 1",
                    (room_uid, owner_id)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return int(row[0])

                ## Fallback to latest call started before recording
                await cur.execute(
                    "SELECT id FROM call_logs "
                    "WHERE room_uid=%s AND owner_id=%s AND started_at<=FROM_UNIXTIME(%s) "
                    "ORDER BY started_at DESC LIMIT 1",
                    (room_uid, owner_id, rec_started_ts)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return int(row[0])
    except Exception as e:
        print(f"[DB:recording] resolve_call_id failed (ignored): {e}")
    return None
