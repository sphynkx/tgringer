## Async MariaDB pool using aiomysql
## Exposes get_pool() for other modules

import os
import asyncio
import aiomysql


_POOL = None
_POOL_LOCK = asyncio.Lock()


async def get_pool():
    """
    Get or create a global aiomysql pool.
    """
    global _POOL
    if _POOL:
        return _POOL
    async with _POOL_LOCK:
        if _POOL:
            return _POOL
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = int(os.getenv("DB_PORT", "3306"))
        user = os.getenv("DB_USER", "tgringer")
        password = os.getenv("DB_PASSWORD", "")
        dbname = os.getenv("DB_NAME", "tgringer")
        minsize = int(os.getenv("DB_POOL_MIN", "1"))
        maxsize = int(os.getenv("DB_POOL_MAX", "5"))

        _POOL = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=dbname,
            minsize=minsize,
            maxsize=maxsize,
            autocommit=True,
            charset="utf8mb4"
        )
        return _POOL

