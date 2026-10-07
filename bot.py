import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем конфиги из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = "8838"

bot = Bot(token=TOKEN)
dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_photo = State()

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_db()
    # Таблица пользователей
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT
        )
    """)
    await conn.close()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
        message.from_user.id,
        message.from_user.username
    )
    await conn.close()
    await message.answer("Привет! Добро пожаловать в бот Agrovista.")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
