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
                ## Update last_seen
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


async def search_users(query: str):
    pool = await DBConnector.get_conn()
    q = f"%{query}%"
    sql = """
        SELECT tg_user_id, username, first_name, last_name, avatar_url, status, language_code, last_seen
        FROM users
        WHERE
            username LIKE %s OR
            first_name LIKE %s OR
            last_name LIKE %s OR
            CAST(tg_user_id AS CHAR) LIKE %s
        LIMIT 20
    """
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, (q, q, q, q))
            rows = await cur.fetchall()
    return rows


async def set_avatar_url(tg_user_id: int, avatar_url: str):
    """
    Persist cached avatar URL for the user into DB.
    The avatar_url should typically be a relative web path like '/static/avatars/<id>.jpg'
    (web client will consume it directly; the bot will convert to absolute via APP_BASE_URL when sending).
    """
    pool = await DBConnector.get_conn()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET avatar_url=%s WHERE tg_user_id=%s",
                (avatar_url, tg_user_id)
            )

