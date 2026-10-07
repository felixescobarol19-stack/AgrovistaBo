import os
import asyncio
import logging
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InputMediaPhoto

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_PASSWORD = "8838"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM СОСТОЯНИЯ ---
class AdminStates(StatesGroup):
    add_truck_photo = State()
    add_truck_name = State()
    add_truck_desc = State()
    
    add_trailer_photo = State()
    add_trailer_name = State()
    add_trailer_desc = State()
    
    add_mods_link = State()
    confirm_add_truck = State()
    
    add_news_content = State()
    
    broadcast_content = State()
    broadcast_count = State()

# --- БАЗА ДАННЫХ ---
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
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
            mods_link TEXT,
            is_busy BOOLEAN DEFAULT FALSE,
            busy_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            status TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            text TEXT,
            photo_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS status_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            truck_info TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            user_id BIGINT PRIMARY KEY,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.close()

async def get_user_truck(user_id: int):
    conn = await get_db()
    truck = await conn.fetchrow("SELECT * FROM trucks WHERE busy_by = $1", user_id)
    await conn.close()
    return truck

async def notify_admin_live(text: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка отправки мгновенного уведомления администратору: {e}")

# --- КЛАВИАТУРЫ ---

async def get_user_main_kb(user_id: int):
    builder = ReplyKeyboardBuilder()
    truck = await get_user_truck(user_id)

    if truck:
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
        builder.button(text="🚚 Просмотреть свободные грузовики")
        builder.button(text="📰 Актуальные новости")
        builder.button(text="📢 ТГК")
        builder.button(text="🤝 ТГК кента")
        builder.button(text="🔑 Админ панель")
        builder.adjust(1, 2, 2)

    return builder.as_markup(resize_keyboard=True)

def get_admin_main_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Добавить грузовик")
    builder.button(text="🔓 Освободить грузовик")
    builder.button(text="👥 Работники")
    builder.button(text="📊 Итоги работников")
    builder.button(text="📜 Список пользователей")
    builder.button(text="📰 Опубликовать новость")
    builder.button(text="📩 Рассылка по боту")
    builder.button(text="🚪 Выйти из админки")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup(resize_keyboard=True)

def get_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Выйти")
    return builder.as_markup(resize_keyboard=True)

def get_confirm_truck_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Добавить сцепку")
    builder.button(text="❌ Выйти")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_pin_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 10):
        builder.button(text=str(i), callback_data=f"pin_num_{i}")
    builder.adjust(3)
    builder.row(
        types.InlineKeyboardButton(text="❌ Стереть", callback_data="pin_clear"),
        types.InlineKeyboardButton(text="0", callback_data="pin_num_0"),
        types.InlineKeyboardButton(text="🚫 Отмена", callback_data="pin_cancel")
    )
    return builder.as_markup()

user_pins = {}

# --- КОМАНДА /START И ВХОД В АДМИНКУ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    conn = await get_db()
    await conn.execute("""
        INSERT INTO users (user_id, username, full_name) 
        VALUES ($1, $2, $3) 
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name
    """, message.from_user.id, message.from_user.username, message.from_user.full_name)
    await conn.close()

    kb = await get_user_main_kb(message.from_user.id)
    await message.answer(
        f"👋 Здравствуйте, {message.from_user.first_name}!\n\n"
        "Вас приветствует бот компании Agrovista. Все меню и системы активированы. Выберите нужный раздел:",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(F.text == "❌ Выйти")
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    kb = await get_user_main_kb(message.from_user.id)
    await message.answer("🔄 Вы вернулись в главное меню.", reply_markup=kb)

@dp.message(F.text == "🔑 Админ панель")
async def admin_entry(message: types.Message):
    user_pins[message.from_user.id] = ""
    await message.answer(
        "🔐 **Введите PIN-код администратора:**\n\nПароль: `_`",
        reply_markup=get_pin_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("pin_"))
async def process_pin_input(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_pin = user_pins.get(user_id, "")
    action = callback.data

    if action == "pin_cancel":
        user_pins.pop(user_id, None)
        await callback.message.delete()
        await callback.answer("Вход отменен.")
        return

    if action == "pin_clear":
        current_pin = ""
    elif action.startswith("pin_num_"):
        num = action.split("_")[2]
        if len(current_pin) < 6:
            current_pin += num

    user_pins[user_id] = current_pin

    if current_pin == ADMIN_PASSWORD:
        user_pins.pop(user_id, None)
        await callback.message.delete()

        conn = await get_db()
        last_session = await conn.fetchrow("SELECT last_login FROM admin_sessions WHERE user_id = $1", user_id)
        
        if last_session:
            missed_logs = await conn.fetch("""
                SELECT username, truck_info, status, created_at 
                FROM status_logs 
                WHERE created_at > $1 
                ORDER BY created_at ASC
            """, last_session['last_login'])
        else:
            missed_logs = await conn.fetch("""
                SELECT username, truck_info, status, created_at 
                FROM status_logs 
                ORDER BY created_at DESC LIMIT 10
            """)

        await conn.execute("""
            INSERT INTO admin_sessions (user_id, last_login) VALUES ($1, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET last_login = CURRENT_TIMESTAMP
        """, user_id)
        await conn.close()

        welcome_text = "🔓 **Авторизация успешна.**\nДобро пожаловать в панель управления.\n"
        
        if missed_logs:
            report = "\n📋 **Пока вас не было в админке:**\n\n"
            for log in missed_logs:
                time_str = log['created_at'].strftime("%H:%M")
                u_name = f"@{log['username']}" if log['username'] else "Водитель"
                report += f"• **{u_name}** ({log['truck_info']}) — `{log['status']}` [{time_str}]\n"
            welcome_text += report
        else:
            welcome_text += "\n✨ Новых изменений статусов за время вашего отсутствия не зафиксировано."

        await callback.message.answer(welcome_text, reply_markup=get_admin_main_kb(), parse_mode="Markdown")
        await callback.answer("Доступ разрешен!")
        return

    masked_pin = "*" * len(current_pin) if current_pin else "_"
    try:
        await callback.message.edit_text(
            f"🔐 **Введите PIN-код администратора:**\n\nПароль: `{masked_pin}`",
            reply_markup=get_pin_keyboard(),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(F.text == "🚪 Выйти из админки")
async def exit_admin(message: types.Message, state: FSMContext):
    await state.clear()
    conn = await get_db()
    await conn.execute("""
        INSERT INTO admin_sessions (user_id, last_login) VALUES ($1, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET last_login = CURRENT_TIMESTAMP
    """, message.from_user.id)
    await conn.close()

    kb = await get_user_main_kb(message.from_user.id)
    await message.answer("🚪 Вы вышли из панели администратора.", reply_markup=kb)

# --- УПРАВЛЕНИЕ СТАТУСАМИ ---

async def update_user_status(message: types.Message, status_text: str, status_emoji: str):
    truck = await get_user_truck(message.from_user.id)
    if not truck:
        await message.answer("❌ У вас нет закреплённого грузовика. Сначала выберите сцепку в меню.")
        return

    full_status = f"{status_text} {status_emoji}"
    truck_info = f"{truck['truck_name']} + {truck['trailer_name']}"
    username = message.from_user.username or message.from_user.full_name

    conn = await get_db()
    await conn.execute("""
        INSERT INTO activity (user_id, username, status) VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE SET status = EXCLUDED.status, username = EXCLUDED.username
    """, message.from_user.id, message.from_user.username, full_status)

    await conn.execute("""
        INSERT INTO status_logs (user_id, username, truck_info, status) 
        VALUES ($1, $2, $3, $4)
    """, message.from_user.id, username, truck_info, full_status)
    await conn.close()

    user_mention = f"@{message.from_user.username}" if message.from_user.username else f"[{message.from_user.full_name}](tg://user?id={message.from_user.id})"

    await message.answer(
        f"Принято! Ваш статус обновлен: **{status_text}** {status_emoji}\n"
        f"Текущая сцепка: **{truck_info}**",
        parse_mode="Markdown"
    )

    admin_msg = (
        f"🔔 **ОБНОВЛЕНИЕ СТАТУСА ВОДИТЕЛЯ**\n\n"
        f"👤 **Водитель:** {user_mention}\n"
        f"🚛 **Сцепка:** {truck_info}\n"
        f"📌 **Статус:** {full_status}"
    )
    await notify_admin_live(admin_msg)

@dp.message(F.text == "🚚 В пути")
async def status_on_the_way(message: types.Message):
    await update_user_status(message, "В пути", "🚚")

@dp.message(F.text == "🏬 На базе")
async def status_at_base(message: types.Message):
    await update_user_status(message, "На базе", "🏬")

@dp.message(F.text == "🏁 Рейс окончен")
async def status_finished(message: types.Message):
    await update_user_status(message, "Рейс окончен", "🏁")

# --- НОВОСТИ ---

@dp.message(F.text == "📰 Актуальные новости")
async def show_news(message: types.Message):
    conn = await get_db()
    news = await conn.fetchrow("SELECT * FROM news ORDER BY id DESC LIMIT 1")
    await conn.close()

    if not news:
        await message.answer("📰 **Актуальных новостей на данный момент нет.**")
        return

    caption = f"📰 **АКТУАЛЬНЫЕ НОВОСТИ КОМПАНИИ:**\n\n{news['text']}"
    if news['photo_id']:
        await message.answer_photo(photo=news['photo_id'], caption=caption, parse_mode="Markdown")
    else:
        await message.answer(caption, parse_mode="Markdown")

@dp.message(F.text == "📰 Опубликовать новость")
async def start_publish_news(message: types.Message, state: FSMContext):
    await message.answer("✍️ Отправьте текст новости (можно с фотографией):", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.add_news_content)

@dp.message(AdminStates.add_news_content)
async def process_news_content(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    if not text and not photo_id:
        await message.answer("❌ Сообщение пустой новости не отправлено. Добавьте текст или фото.")
        return

    conn = await get_db()
    await conn.execute("INSERT INTO news (text, photo_id) VALUES ($1, $2)", text, photo_id)
    await conn.close()

    await state.clear()
    await message.answer("🎉 Новость опубликована! Она теперь доступна по кнопке «Актуальные новости».", reply_markup=get_admin_main_kb())

# --- ДОБАВЛЕНИЕ СЦЕПКИ И МОДОВ ---

@dp.message(F.text == "➕ Добавить грузовик")
async def add_truck_start(message: types.Message, state: FSMContext):
    await message.answer("📸 Отправьте изображение грузовика:", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.add_truck_photo)

@dp.message(AdminStates.add_truck_photo, F.photo)
async def process_truck_photo(message: types.Message, state: FSMContext):
    await state.update_data(truck_photo=message.photo[-1].file_id)
    await message.answer("🚚 Введите название и модель грузовика:")
    await state.set_state(AdminStates.add_truck_name)

@dp.message(AdminStates.add_truck_name)
async def process_truck_name(message: types.Message, state: FSMContext):
    await state.update_data(truck_name=message.text)
    await message.answer("📝 Введите описание грузовика (или отправьте `-`, если не требуется):")
    await state.set_state(AdminStates.add_truck_desc)

@dp.message(AdminStates.add_truck_desc)
async def process_truck_desc(message: types.Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text
    await state.update_data(truck_desc=desc)
    await message.answer("📸 Отправьте изображение прицепа:")
    await state.set_state(AdminStates.add_trailer_photo)

@dp.message(AdminStates.add_trailer_photo, F.photo)
async def process_trailer_photo(message: types.Message, state: FSMContext):
    await state.update_data(trailer_photo=message.photo[-1].file_id)
    await message.answer("🚛 Введите название прицепа:")
    await state.set_state(AdminStates.add_trailer_name)

@dp.message(AdminStates.add_trailer_name)
async def process_trailer_name(message: types.Message, state: FSMContext):
    await state.update_data(trailer_name=message.text)
    await message.answer("📝 Введите описание прицепа (или отправьте `-`, если не требуется):")
    await state.set_state(AdminStates.add_trailer_desc)

@dp.message(AdminStates.add_trailer_desc)
async def process_trailer_desc(message: types.Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text
    await state.update_data(trailer_desc=desc)
    await message.answer("🔗 Отправьте ссылку на модификации для сцепки (или отправьте `-`, если ссылки нет):")
    await state.set_state(AdminStates.add_mods_link)

@dp.message(AdminStates.add_mods_link)
async def process_mods_link(message: types.Message, state: FSMContext):
    mods_link = "" if message.text.strip() == "-" else message.text
    await state.update_data(mods_link=mods_link)

    data = await state.get_data()
    caption = (
        f"📋 **Подтверждение параметров сцепки:**\n\n"
        f"🚚 **Грузовик:** {data['truck_name']}\n"
        f"📝 **Описание:** {data.get('truck_desc') or 'Отсутствует'}\n\n"
        f"🚛 **Прицеп:** {data['trailer_name']}\n"
        f"📝 **Описание:** {data.get('trailer_desc') or 'Отсутствует'}\n\n"
        f"🔗 **Ссылка на моды:** {data.get('mods_link') or 'Отсутствует'}"
    )
    await message.answer(caption, reply_markup=get_confirm_truck_kb(), parse_mode="Markdown")
    await state.set_state(AdminStates.confirm_add_truck)

@dp.message(AdminStates.confirm_add_truck, F.text == "✅ Добавить сцепку")
async def save_truck_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    conn = await get_db()
    await conn.execute("""
        INSERT INTO trucks (truck_photo, truck_name, truck_desc, trailer_photo, trailer_name, trailer_desc, mods_link)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, data['truck_photo'], data['truck_name'], data['truck_desc'], 
       data['trailer_photo'], data['trailer_name'], data['trailer_desc'], data['mods_link'])
    await conn.close()

    await message.answer("✅ Сцепка занесена в автопарк!", reply_markup=get_admin_main_kb())

# --- АДМИНКА: СТАТИСТИКА И ПОЛЬЗОВАТЕЛИ ---

@dp.message(F.text == "👥 Работники")
async def show_workers_status(message: types.Message):
    conn = await get_db()
    users = await conn.fetch("SELECT user_id, username, full_name FROM users")
    activities = await conn.fetch("SELECT user_id, status FROM activity")
    await conn.close()

    act_dict = {a['user_id']: a['status'] for a in activities}

    on_the_way, at_base, finished, no_status = [], [], [], []

    for u in users:
        u_name = f"@{u['username']}" if u['username'] else f"{u['full_name']} (ID: {u['user_id']})"
        st = act_dict.get(u['user_id'])
        
        if st and "В пути" in st:
            on_the_way.append(u_name)
        elif st and "На базе" in st:
            at_base.append(u_name)
        elif st and "Рейс окончен" in st:
            finished.append(u_name)
        else:
            no_status.append(u_name)

    text = f"👥 **Текущий статус работников (Всего: {len(users)}):**\n\n"
    text += f"🚚 **В пути ({len(on_the_way)}):**\n" + ("\n".join([f"• {u}" for u in on_the_way]) if on_the_way else "Никого") + "\n\n"
    text += f"🏬 **На базе ({len(at_base)}):**\n" + ("\n".join([f"• {u}" for u in at_base]) if at_base else "Никого") + "\n\n"
    text += f"🏁 **Завершили рейс ({len(finished)}):**\n" + ("\n".join([f"• {u}" for u in finished]) if finished else "Никого") + "\n\n"
    text += f"💤 **Без активного рейса ({len(no_status)}):**\n" + ("\n".join([f"• {u}" for u in no_status]) if no_status else "Никого")

    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 Итоги работников")
async def show_workers_summary(message: types.Message):
    conn = await get_db()
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    busy_trucks = await conn.fetchval("SELECT COUNT(*) FROM trucks WHERE is_busy = TRUE")
    free_trucks = await conn.fetchval("SELECT COUNT(*) FROM trucks WHERE is_busy = FALSE")
    
    on_way = await conn.fetchval("SELECT COUNT(*) FROM activity WHERE status LIKE '%В пути%'")
    at_base = await conn.fetchval("SELECT COUNT(*) FROM activity WHERE status LIKE '%На базе%'")
    finished = await conn.fetchval("SELECT COUNT(*) FROM activity WHERE status LIKE '%Рейс окончен%'")
    await conn.close()

    text = (
        f"📊 **Итоги по составу и технике:**\n\n"
        f"👥 Зарегистрировано водителей: `{total_users}`\n"
        f"🚛 Занятых сцепок: `{busy_trucks}`\n"
        f"🟢 Свободных сцепок: `{free_trucks}`\n\n"
        f"📈 **Текущие статусы:**\n"
        f"• 🚚 В пути: `{on_way}`\n"
        f"• 🏬 На базе: `{at_base}`\n"
        f"• 🏁 Рейс окончен: `{finished}`"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📜 Список пользователей")
async def show_users_list(message: types.Message):
    conn = await get_db()
    users = await conn.fetch("SELECT user_id, username, full_name FROM users ORDER BY joined_at DESC")
    await conn.close()

    if not users:
        await message.answer("📜 Список пользователей пуст.")
        return

    text = f"📜 **Реестр водителей ({len(users)} чел.):**\n\n"
    for idx, u in enumerate(users, start=1):
        username = f"@{u['username']}" if u['username'] else "Без username"
        name = u['full_name'] or "Пользователь"
        text += f"{idx}. **{name}** | {username} | `ID: {u['user_id']}`\n"

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x+4000], parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

# --- РАССЫЛКА И ОСВОБОЖДЕНИЕ ГРУЗОВИКОВ ---

@dp.message(F.text == "📩 Рассылка по боту")
async def start_broadcast(message: types.Message, state: FSMContext):
    await message.answer("✍️ Отправьте сообщение для рассылки:", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.broadcast_content)

@dp.message(AdminStates.broadcast_content)
async def process_broadcast_content(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(photo=message.photo[-1].file_id, text=message.caption or "")
    else:
        await state.update_data(photo=None, text=message.text)

    builder = ReplyKeyboardBuilder()
    builder.button(text="1")
    builder.button(text="2")
    builder.button(text="3")
    builder.button(text="4")
    builder.button(text="❌ Выйти")
    builder.adjust(2, 2, 1)

    await message.answer("🔢 Укажите количество повторов отправки:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AdminStates.broadcast_count)

@dp.message(AdminStates.broadcast_count, F.text.in_({"1", "2", "3", "4"}))
async def run_broadcast_repeat(message: types.Message, state: FSMContext):
    repeats = int(message.text)
    data = await state.get_data()
    await state.clear()

    conn = await get_db()
    users = await conn.fetch("SELECT user_id FROM users")
    await conn.close()

    count = 0
    for user in users:
        try:
            for _ in range(repeats):
                if data.get('photo'):
                    await bot.send_photo(chat_id=user['user_id'], photo=data['photo'], caption=data.get('text'))
                else:
                    await bot.send_message(chat_id=user['user_id'], text=data['text'])
                await asyncio.sleep(0.1)
            count += 1
        except Exception:
            pass

    await message.answer(f"✅ Рассылка завершена. Сообщение доставлено пользователям: {count}.", reply_markup=get_admin_main_kb())

@dp.message(F.text == "🔓 Освободить грузовик")
async def admin_free_truck_list(message: types.Message):
    conn = await get_db()
    busy_trucks = await conn.fetch("""
        SELECT t.id, t.truck_name, u.username, t.busy_by 
        FROM trucks t 
        LEFT JOIN users u ON t.busy_by = u.user_id 
        WHERE t.is_busy = TRUE
    """)
    await conn.close()

    if not busy_trucks:
        await message.answer("ℹ️ Занятых грузовиков в данный момент нет.")
        return

    builder = InlineKeyboardBuilder()
    for truck in busy_trucks:
        user_info = f"@{truck['username']}" if truck['username'] else f"ID: {truck['busy_by']}"
        builder.button(text=f"🔓 {truck['truck_name']} ({user_info})", callback_data=f"admin_free_{truck['id']}")

    builder.adjust(1)
    await message.answer("🛠 Выберите сцепку, которую нужно освободить:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("admin_free_"))
async def process_admin_free_truck(callback: types.CallbackQuery):
    truck_id = int(callback.data.split("_")[2])
    conn = await get_db()
    truck = await conn.fetchrow("SELECT truck_name, busy_by FROM trucks WHERE id = $1", truck_id)

    if truck and truck['busy_by']:
        busy_user_id = truck['busy_by']
        await conn.execute("UPDATE trucks SET is_busy = FALSE, busy_by = NULL WHERE id = $1", truck_id)
        await conn.execute("DELETE FROM activity WHERE user_id = $1", busy_user_id)
        await conn.close()

        await callback.answer("✅ Сцепка освобождена!", show_alert=True)
        await callback.message.edit_text(f"✅ Сцепка **{truck['truck_name']}** снята с рейса и возвращена на базу.", parse_mode="Markdown")

        try:
            kb = await get_user_main_kb(busy_user_id)
            await bot.send_message(busy_user_id, f"🔓 Ваша сцепка (**{truck['truck_name']}**) была освобождена администратором.", reply_markup=kb)
        except Exception:
            pass
    else:
        await conn.close()
        await callback.answer("❌ Эта сцепка уже свободна.", show_alert=True)

# --- ПРОСМОТР И ВЫБОР СЦЕПКИ ---

async def send_truck_card(chat_id: int, page: int):
    conn = await get_db()
    total = await conn.fetchval("SELECT COUNT(*) FROM trucks")
    if total == 0:
        await conn.close()
        await bot.send_message(chat_id, "🚛 Доступных грузовиков в базе нет.")
        return

    truck = await conn.fetchrow("SELECT * FROM trucks ORDER BY id LIMIT 1 OFFSET $1", page)
    await conn.close()

    status_str = "🔴 Занят" if truck['is_busy'] else "🟢 Свободен"
    
    caption = (
        f"🚚 **Грузовик:** {truck['truck_name']}\n"
        f"📝 **Описание:** {truck['truck_desc'] or 'Отсутствует'}\n\n"
        f"🚛 **Прицеп:** {truck['trailer_name']}\n"
        f"📝 **Описание:** {truck['trailer_desc'] or 'Отсутствует'}\n\n"
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
    await bot.send_message(chat_id=chat_id, text=f"Сцепка {page + 1} из {total}", reply_markup=builder.as_markup())

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

    if await get_user_truck(callback.from_user.id):
        await conn.close()
        await callback.answer("❌ У вас уже есть активная сцепка!", show_alert=True)
        return

    truck = await conn.fetchrow("SELECT is_busy, mods_link, truck_name FROM trucks WHERE id = $1", truck_id)
    if truck['is_busy']:
        await conn.close()
        await callback.answer("❌ Этот грузовик уже занят другой машиной!", show_alert=True)
        return

    await conn.execute("UPDATE trucks SET is_busy = TRUE, busy_by = $1 WHERE id = $2", callback.from_user.id, truck_id)
    await conn.close()

    await callback.answer("✅ Вы закрепили за собой эту сцепку!", show_alert=True)
    kb = await get_user_main_kb(callback.from_user.id)
    
    msg_text = f"🔑 Вы приняли сцепку **{truck['truck_name']}**! Главное меню обновилось."
    
    if truck['mods_link']:
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 Скачать моды на сцепку", url=truck['mods_link'])
        await callback.message.answer(
            f"{msg_text}\n\nСсылка на скачивание ваших модификаций:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(msg_text, parse_mode="Markdown")

    await callback.message.answer("Главное меню готова к работе:", reply_markup=kb)

# --- МОЙ ГРУЗОВИК И КАНАЛЫ ---

@dp.message(F.text == "🚛 Мой грузовик")
async def my_truck(message: types.Message):
    truck = await get_user_truck(message.from_user.id)

    if not truck:
        await message.answer("❌ За вами не закреплён ни один грузовик.")
        return

    caption = (
        f"🚛 **Ваша текущая сцепка:**\n\n"
        f"🚚 **Грузовик:** {truck['truck_name']}\n"
        f"📝 **Описание:** {truck['truck_desc'] or 'Отсутствует'}\n\n"
        f"🚛 **Прицеп:** {truck['trailer_name']}\n"
        f"📝 **Описание:** {truck['trailer_desc'] or 'Отсутствует'}"
    )
    media = [
        InputMediaPhoto(media=truck['truck_photo'], caption=caption, parse_mode="Markdown"),
        InputMediaPhoto(media=truck['trailer_photo'])
    ]
    await message.answer_media_group(media=media)

    if truck['mods_link']:
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 Скачать моды на сцепку", url=truck['mods_link'])
        await message.answer("Ссылка на сборку модов:", reply_markup=builder.as_markup())

@dp.message(F.text == "📢 ТГК")
async def process_tgk(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Перейти в наш канал", url="https://t.me/logovoDalnoboya")
    await message.answer("Наш официальный Telegram-канал:", reply_markup=builder.as_markup())

@dp.message(F.text == "🤝 ТГК кента")
async def process_tgk_friend(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🤝 Перейти в ТГК Кента", url="https://t.me/dalnoboy_ETS")
    await message.answer("Канал нашего партнера:", reply_markup=builder.as_markup())

# --- ЗАПУСК БОТА ---

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
