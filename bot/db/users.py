import aiomysql
from bot.db.connector import DBConnector

async def register_user(tg_user_id: int, username: str, first_name: str, last_name: str, language_code: str):
    pool = await DBConnector.get_conn()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            ## Check if user exists
            await cur.execute(
                "SELECT id FROM users WHERE tg_user_id=%s",
                (tg_user_id,)
            )
            res = await cur.fetchone()
            if res:
                ## Update last_seen (recheck - maybe not update!!)
                await cur.execute(
                    "UPDATE users SET last_seen=NOW() WHERE tg_user_id=%s",
                    (tg_user_id,)
                )
            else:
                await cur.execute(
                    """
                    INSERT INTO users
                    (tg_user_id, username, first_name, last_name, language_code, last_seen)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    (tg_user_id, username, first_name, last_name, language_code)
                )

