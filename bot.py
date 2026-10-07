import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InputMediaPhoto

# Логирование
logging.basicConfig(level=logging.INFO)

# Конфигурация из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = "8838"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM Состояния
class AdminStates(StatesGroup):
    waiting_for_password = State()
    add_truck_photo = State()
    add_truck_name = State()
    add_truck_desc = State()
    add_trailer_photo = State()
    add_trailer_name = State()
    add_trailer_desc = State()
    broadcast_photo = State()
    broadcast_text = State()

# Подключение к БД
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trucks (
            id SERIAL PRIMARY KEY,
            truck_photo TEXT,
            truck_name TEXT,
            truck_desc TEXT,
            trailer_photo TEXT,
            trailer_name TEXT,
            trailer_desc TEXT,
            is_busy BOOLEAN DEFAULT FALSE,
            busy_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            status TEXT,
            finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            text TEXT,
            photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.close()

# Проверка, есть ли у пользователя выбранный грузовик
async def has_truck(user_id: int) -> bool:
    conn = await get_db()
    truck = await conn.fetchrow("SELECT id FROM trucks WHERE busy_by = $1", user_id)
    await conn.close()
    return truck is not None

# Динамическое главное меню для пользователя
async def get_user_main_kb(user_id: int):
    builder = ReplyKeyboardBuilder()
    in_trip = await has_truck(user_id)

    if in_trip:
        # Кнопки, когда у водителя есть грузовик
        builder.button(text="🚚 В пути")
        builder.button(text="🏬 На базе")
        builder.button(text="🚛 Мой грузовик")
        builder.button(text="🏁 Рейс окончен")
        builder.button(text="📰 Актуальные новости")
        builder.button(text="📢 ТГК")
        builder.button(text="🤝 ТГК кента")
        builder.button(text="🔑 Админ панель")
        builder.adjust(2, 2, 3, 1)
    else:
        # Обычные кнопки, когда грузовика нет
        builder.button(text="🚚 Просмотреть свободные грузовики")
        builder.button(text="📰 Актуальные новости")
        builder.button(text="📢 ТГК")
        builder.button(text="🤝 ТГК кента")
        builder.button(text="🔑 Админ панель")
        builder.adjust(1, 2, 2)

    return builder.as_markup(resize_keyboard=True)

# Меню админки
def get_admin_main_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Добавить грузовик")
    builder.button(text="🔓 Освободить грузовик")
    builder.button(text="📊 Активность")
    builder.button(text="📩 Рассылка по боту")
    builder.button(text="🚪 Выйти из админки")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# Кнопка отмены
def get_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Выйти")
    return builder.as_markup(resize_keyboard=True)

# Ссылки ТГК
def get_tgk_inline_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Наш ТГК", url="https://t.me/logovoDalnoboya")
    return builder.as_markup()

def get_tgk_friend_inline_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🤝 ТГК Кента", url="https://t.me/dalnoboy_ETS")
    return builder.as_markup()

# --- СТАРТ И ОБЩИЕ КОМАНДЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    conn = await get_db()
    await conn.execute(
        "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
        message.from_user.id, message.from_user.username
    )
    await conn.close()

    kb = await get_user_main_kb(message.from_user.id)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}! Добро пожаловать в бот Agrovista!\n"
        "Выбери нужный раздел в меню ниже.",
        reply_markup=kb
    )

@dp.message(F.text == "❌ Выйти")
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    kb = await get_user_main_kb(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=kb)

# --- ТГК КНОПКИ ---

@dp.message(F.text == "📢 ТГК")
async def process_tgk(message: types.Message):
    await message.answer("Переходи на наш канал:", reply_markup=get_tgk_inline_kb())

@dp.message(F.text == "🤝 ТГК кента")
async def process_tgk_friend(message: types.Message):
    await message.answer("Переходи на канал нашего кента:", reply_markup=get_tgk_friend_inline_kb())

# --- АДМИН ПАНЕЛЬ ---

@dp.message(F.text == "🔑 Админ панель")
async def admin_entry(message: types.Message, state: FSMContext):
    await message.answer("🔑 Введи пароль для входа в админ панель:", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.waiting_for_password)

@dp.message(AdminStates.waiting_for_password)
async def check_admin_password(message: types.Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        await state.clear()
        conn = await get_db()
        users = await conn.fetch("SELECT username, joined_at FROM users ORDER BY joined_at DESC LIMIT 5")
        await conn.close()

        text = "🔓 Добро пожаловать в Админ Панель!\n\n📋 **Последние зарегистрированные пользователи:**\n"
        for u in users:
            username = f"@{u['username']}" if u['username'] else "Без username"
            time_str = u['joined_at'].strftime("%Y-%m-%d %H:%M") if u['joined_at'] else "Неизвестно"
            text += f"• {username} ({time_str})\n"

        await message.answer(text, reply_markup=get_admin_main_kb(), parse_mode="Markdown")
    else:
        await message.answer("❌ Неверный пароль! Попробуй снова или нажми '❌ Выйти'.")

@dp.message(F.text == "🚪 Выйти из админки")
async def exit_admin(message: types.Message, state: FSMContext):
    await state.clear()
    kb = await get_user_main_kb(message.from_user.id)
    await message.answer("Вы вышли из админ панели.", reply_markup=kb)

# --- ОСВОБОЖДЕНИЕ ГРУЗОВИКА (ТОЛЬКО ДЛЯ АДМИНА) ---

@dp.message(F.text == "🔓 Освободить грузовик")
async def admin_free_truck_list(message: types.Message):
    conn = await get_db()
    busy_trucks = await conn.fetch("""
        SELECT t.id, t.truck_name, t.trailer_name, u.username, t.busy_by 
        FROM trucks t 
        LEFT JOIN users u ON t.busy_by = u.user_id 
        WHERE t.is_busy = TRUE
    """)
    await conn.close()

    if not busy_trucks:
        await message.answer("ℹ️ На данный момент нет занятых грузовиков.")
        return

    builder = InlineKeyboardBuilder()
    for truck in busy_trucks:
        user_info = f"@{truck['username']}" if truck['username'] else f"ID: {truck['busy_by']}"
        btn_text = f"🔓 {truck['truck_name']} ({user_info})"
        builder.button(text=btn_text, callback_data=f"admin_free_{truck['id']}")

    builder.adjust(1)
    await message.answer("🛠 **Выберите грузовик для освобождения:**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("admin_free_"))
async def process_admin_free_truck(callback: types.CallbackQuery):
    truck_id = int(callback.data.split("_")[2])
    conn = await get_db()
    truck = await conn.fetchrow("SELECT truck_name, busy_by FROM trucks WHERE id = $1", truck_id)

    if truck and truck['busy_by']:
        busy_user_id = truck['busy_by']
        await conn.execute("UPDATE trucks SET is_busy = FALSE, busy_by = NULL WHERE id = $1", truck_id)
        await conn.close()

        await callback.answer("✅ Грузовик успешно освобожден!", show_alert=True)
        await callback.message.edit_text(f"✅ Грузовик **{truck['truck_name']}** освобожден админом.", parse_mode="Markdown")

        # Уведомляем пользователя, что его грузовик освобожден
        try:
            kb = await get_user_main_kb(busy_user_id)
            await bot.send_message(busy_user_id, f"🔓 Администратор освободил ваш грузовик ({truck['truck_name']}).", reply_markup=kb)
        except Exception:
            pass
    else:
        await conn.close()
        await callback.answer("❌ Этот грузовик уже свободен.", show_alert=True)

# --- ДОБАВЛЕНИЕ ГРУЗОВИКА ---

@dp.message(F.text == "➕ Добавить грузовик")
async def add_truck_start(message: types.Message, state: FSMContext):
    await message.answer("📸 Скинь фото грузовика:", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.add_truck_photo)

@dp.message(AdminStates.add_truck_photo, F.photo)
async def process_truck_photo(message: types.Message, state: FSMContext):
    await state.update_data(truck_photo=message.photo[-1].file_id)
    await message.answer("🚚 Введи название грузовика (например, MAN TGX):")
    await state.set_state(AdminStates.add_truck_name)

@dp.message(AdminStates.add_truck_name)
async def process_truck_name(message: types.Message, state: FSMContext):
    await state.update_data(truck_name=message.text)
    await message.answer("📝 Введи описание грузовика (если нет, поставь `-`):")
    await state.set_state(AdminStates.add_truck_desc)

@dp.message(AdminStates.add_truck_desc)
async def process_truck_desc(message: types.Message, state: FSMContext):
    await state.update_data(truck_desc=message.text)
    await message.answer("📸 Скинь фото прицепа:")
    await state.set_state(AdminStates.add_trailer_photo)

@dp.message(AdminStates.add_trailer_photo, F.photo)
async def process_trailer_photo(message: types.Message, state: FSMContext):
    await state.update_data(trailer_photo=message.photo[-1].file_id)
    await message.answer("🚛 Введи название прицепа:")
    await state.set_state(AdminStates.add_trailer_name)

@dp.message(AdminStates.add_trailer_name)
async def process_trailer_name(message: types.Message, state: FSMContext):
    await state.update_data(trailer_name=message.text)
    await message.answer("📝 Введи описание прицепа (если нет, поставь `-`):")
    await state.set_state(AdminStates.add_trailer_desc)

@dp.message(AdminStates.add_trailer_desc)
async def save_truck_and_notify(message: types.Message, state: FSMContext):
    await state.update_data(trailer_desc=message.text)
    data = await state.get_data()
    await state.clear()

    conn = await get_db()
    await conn.execute("""
        INSERT INTO trucks (truck_photo, truck_name, truck_desc, trailer_photo, trailer_name, trailer_desc)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, data['truck_photo'], data['truck_name'], data['truck_desc'], data['trailer_photo'], data['trailer_name'], data['trailer_desc'])

    users = await conn.fetch("SELECT user_id FROM users")
    await conn.close()

    await message.answer("✅ Новая сцепка успешно добавлена!", reply_markup=get_admin_main_kb())

    media = [
        InputMediaPhoto(media=data['truck_photo'], caption=f"🎉 **Добавлена новая сцепка на фирму Agrovista!**\n\n🚚 **Грузовик:** {data['truck_name']}\n📝 {data['truck_desc']}\n\n🚛 **Прицеп:** {data['trailer_name']}\n📝 {data['trailer_desc']}", parse_mode="Markdown"),
        InputMediaPhoto(media=data['trailer_photo'])
    ]

    for user in users:
        try:
            await bot.send_media_group(chat_id=user['user_id'], media=media)
        except Exception:
            pass

# --- РАССЫЛКА ---

@dp.message(F.text == "📩 Рассылка по боту")
async def start_broadcast(message: types.Message, state: FSMContext):
    await message.answer("📸 Скинь фото для рассылки (если без фото, отправь `-`):", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.broadcast_photo)

@dp.message(AdminStates.broadcast_photo)
async def process_broadcast_photo(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(photo=message.photo[-1].file_id)
    else:
        await state.update_data(photo=None)
    await message.answer("✍️ Напиши текст рассылки:")
    await state.set_state(AdminStates.broadcast_text)

@dp.message(AdminStates.broadcast_text)
async def run_broadcast(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    conn = await get_db()
    users = await conn.fetch("SELECT user_id FROM users")
    await conn.close()

    count = 0
    for user in users:
        try:
            if data.get('photo'):
                await bot.send_photo(chat_id=user['user_id'], photo=data['photo'], caption=message.text)
            else:
                await bot.send_message(chat_id=user['user_id'], text=message.text)
            count += 1
        except Exception:
            pass

    await message.answer(f"✅ Рассылка отправлена {count} пользователям!", reply_markup=get_admin_main_kb())

# --- СТАТУСЫ В РЕЙСЕ ---

@dp.message(F.text == "🚚 В пути")
async def status_on_the_way(message: types.Message):
    if not await has_truck(message.from_user.id):
        await message.answer("❌ У вас нет занятого грузовика!")
        return

    conn = await get_db()
    await conn.execute("INSERT INTO activity (user_id, username, status) VALUES ($1, $2, $3)",
                       message.from_user.id, message.from_user.username, "В пути 🚚")
    await conn.close()
    await message.answer("🟢 Ваш статус обновлен: **В пути** 🚚", parse_mode="Markdown")

@dp.message(F.text == "🏬 На базе")
async def status_at_base(message: types.Message):
    if not await has_truck(message.from_user.id):
        await message.answer("❌ У вас нет занятого грузовика!")
        return

    conn = await get_db()
    await conn.execute("INSERT INTO activity (user_id, username, status) VALUES ($1, $2, $3)",
                       message.from_user.id, message.from_user.username, "На базе 🏬")
    await conn.close()
    await message.answer("🔵 Ваш статус обновлен: **На базе** 🏬", parse_mode="Markdown")

@dp.message(F.text == "🏁 Рейс окончен")
async def finish_trip(message: types.Message):
    if not await has_truck(message.from_user.id):
        await message.answer("❌ У вас нет занятого грузовика!")
        return

    conn = await get_db()
    await conn.execute("INSERT INTO activity (user_id, username, status) VALUES ($1, $2, $3)",
                       message.from_user.id, message.from_user.username, "Рейс окончен 🏁")
    await conn.close()

    await message.answer("🏆 Отличная работа! Информация записана в активность. Ожидайте, пока администратор освободит ваш грузовик.")

@dp.message(F.text == "📊 Активность")
async def show_activity(message: types.Message):
    conn = await get_db()
    records = await conn.fetch("SELECT username, status, finished_at FROM activity ORDER BY finished_at DESC LIMIT 15")
    await conn.close()

    if not records:
        await message.answer("📊 Активность пока отсутствует.")
        return

    text = "📊 **История активности водителей:**\n\n"
    for r in records:
        username = f"@{r['username']}" if r['username'] else "Без username"
        status = r['status'] or "Рейс окончен 🏁"
        time_str = r['finished_at'].strftime("%d.%m %H:%M")
        text += f"• {username} — {status} ({time_str})\n"

    await message.answer(text, parse_mode="Markdown")

# --- ПРОСМОТР И ВЫБОР ГРУЗОВИКОВ ---

async def send_truck_card(chat_id: int, page: int):
    conn = await get_db()
    total = await conn.fetchval("SELECT COUNT(*) FROM trucks")
    if total == 0:
        await conn.close()
        await bot.send_message(chat_id, "🚛 Грузовики пока не добавлены.")
        return

    truck = await conn.fetchrow("SELECT * FROM trucks ORDER BY id LIMIT 1 OFFSET $1", page)
    await conn.close()

    status_str = "🔴 Занят" if truck['is_busy'] else "🟢 Свободен"
    caption = (
        f"🚚 **Грузовик:** {truck['truck_name']}\n"
        f"📝 {truck['truck_desc']}\n\n"
        f"🚛 **Прицеп:** {truck['trailer_name']}\n"
        f"📝 {truck['trailer_desc']}\n\n"
        f"Статус: {status_str}"
    )

    builder = InlineKeyboardBuilder()
    if not truck['is_busy']:
        builder.button(text="🔑 Занять грузовик", callback_data=f"take_truck_{truck['id']}")

    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"truck_page_{page - 1}"))
    if page + 1 < total:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперед ▶️", callback_data=f"truck_page_{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    media = [
        InputMediaPhoto(media=truck['truck_photo'], caption=caption, parse_mode="Markdown"),
        InputMediaPhoto(media=truck['trailer_photo'])
    ]

    await bot.send_media_group(chat_id=chat_id, media=media)
    await bot.send_message(chat_id=chat_id, text=f"Грузовик {page + 1} из {total}", reply_markup=builder.as_markup())

@dp.message(F.text == "🚚 Просмотреть свободные грузовики")
async def view_trucks(message: types.Message):
    await send_truck_card(message.chat.id, 0)

@dp.callback_query(F.data.startswith("truck_page_"))
async def process_truck_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await callback.message.delete()
    await send_truck_card(callback.message.chat.id, page)
    await callback.answer()

@dp.callback_query(F.data.startswith("take_truck_"))
async def take_truck(callback: types.CallbackQuery):
    truck_id = int(callback.data.split("_")[2])
    conn = await get_db()

    if await has_truck(callback.from_user.id):
        await conn.close()
        await callback.answer("❌ У вас уже есть занятый грузовик!", show_alert=True)
        return

    truck = await conn.fetchrow("SELECT is_busy FROM trucks WHERE id = $1", truck_id)
    if truck['is_busy']:
        await conn.close()
        await callback.answer("❌ Этот грузовик уже кто-то занял!", show_alert=True)
        return

    await conn.execute("UPDATE trucks SET is_busy = TRUE, busy_by = $1 WHERE id = $2", callback.from_user.id, truck_id)
    await conn.close()

    await callback.answer("✅ Вы успешно заняли этот грузовик!", show_alert=True)
    kb = await get_user_main_kb(callback.from_user.id)
    await callback.message.answer("🚚 Вы заняли грузовик! Теперь вам доступны кнопки управления рейсом.", reply_markup=kb)

# --- МОЙ ГРУЗОВИК И НОВОСТИ ---

@dp.message(F.text == "🚛 Мой грузовик")
async def my_truck(message: types.Message):
    conn = await get_db()
    truck = await conn.fetchrow("SELECT * FROM trucks WHERE busy_by = $1", message.from_user.id)
    await conn.close()

    if not truck:
        await message.answer("❌ У вас пока нет выбранного грузовика.")
        return

    caption = (
        f"🚛 **Ваш текущий грузовик:**\n\n"
        f"🚚 **Грузовик:** {truck['truck_name']}\n📝 {truck['truck_desc']}\n\n"
        f"🚛 **Прицеп:** {truck['trailer_name']}\n📝 {truck['trailer_desc']}"
    )
    media = [
        InputMediaPhoto(media=truck['truck_photo'], caption=caption, parse_mode="Markdown"),
        InputMediaPhoto(media=truck['trailer_photo'])
    ]
    await message.answer_media_group(media=media)

@dp.message(F.text == "📰 Актуальные новости")
async def show_news(message: types.Message):
    conn = await get_db()
    news = await conn.fetchrow("SELECT * FROM news ORDER BY created_at DESC LIMIT 1")
    await conn.close()

    if not news:
        await message.answer("📰 Новостей пока нет, ожидайте обновлений!")
    else:
        if news['photo']:
            await message.answer_photo(photo=news['photo'], caption=news['text'])
        else:
            await message.answer(text=news['text'])

# --- ЗАПУСК БОТА ---

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
