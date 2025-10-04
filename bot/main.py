import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN
from bot.routes.basic import router as basic_router
from bot.db.connector import DBConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def on_startup():
    await DBConnector.init_pool()
    logging.info("DB pool initialized")

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(basic_router)

    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())