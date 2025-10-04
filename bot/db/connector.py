import aiomysql
from bot.config import MYSQL_HOST, MYSQL_PORT, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD


class DBConnector:
    pool = None

    @classmethod
    async def init_pool(cls):
        if cls.pool is None:
            cls.pool = await aiomysql.create_pool(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                db=MYSQL_DB,
                autocommit=True,
                minsize=1,
                maxsize=10,
                charset="utf8mb4"
            )
        return cls.pool

    @classmethod
    async def get_conn(cls):
        if cls.pool is None:
            await cls.init_pool()
        return cls.pool

