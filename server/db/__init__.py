## Async MariaDB pool using aiomysql
## Reads connection params from environment variables (MYSQL_* primary)

import os
import asyncio
import aiomysql


_POOL = None
_POOL_LOCK = asyncio.Lock()


def _env(name: str, default: str = "", alt: str = "") -> str:
    """
    Read env with primary name first, then optional alt fallback, then default.
    Primary names are MYSQL_* per project convention.
    """
    val = os.getenv(name)
    if val is not None and val != "":
        return val
    if alt:
        val = os.getenv(alt)
        if val is not None and val != "":
            return val
    return default


async def get_pool():
    """
    Get or create a global aiomysql pool using MYSQL_* environment variables.
    Required:
      - MYSQL_HOST
      - MYSQL_PORT
      - MYSQL_USER
      - MYSQL_PASSWORD
      - MYSQL_DB
    Optional:
      - MYSQL_POOL_MIN (default 1)
      - MYSQL_POOL_MAX (default 5)
    """
    global _POOL
    if _POOL:
        return _POOL
    async with _POOL_LOCK:
        if _POOL:
            return _POOL

        host = _env("MYSQL_HOST", "127.0.0.1", alt="DB_HOST")
        port = int(_env("MYSQL_PORT", "3306", alt="DB_PORT") or "3306")
        user = _env("MYSQL_USER", "root", alt="DB_USER")
        password = _env("MYSQL_PASSWORD", "", alt="DB_PASSWORD")
        dbname = _env("MYSQL_DB", "tgringer01", alt="DB_NAME")
        minsize = int(_env("MYSQL_POOL_MIN", "1", alt="DB_POOL_MIN") or "1")
        maxsize = int(_env("MYSQL_POOL_MAX", "5", alt="DB_POOL_MAX") or "5")

        _POOL = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=dbname,
            minsize=minsize,
            maxsize=maxsize,
            autocommit=True,
            charset="utf8mb4",
        )
        return _POOL
