import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

TOKEN = "8838420735:AAEJPPdnm6BklJCSFY87MgLHptwJL8pcM4"  # Твой токен бота из сообщения выше
ADMIN_PASSWORD = "8838"

DB_FILE = "database.db"

# Состояния для FSM (добавление грузовика админом)
class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_photo = State()

# Инициализация базы данных
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        # Таблица грузовиков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trucks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                photo_id TEXT,
                status TEXT DEFAULT 'свободен', -- свободен / занят
                status_place TEXT DEFAULT 'на базе', -- в рейсе / на базе / на стоянке
                owner_id INTEGER DEFAULT NULL
            )
        """)
        await db.commit()

# Главное меню (обычный пользователь)
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚛 Список грузовиков")
    builder.button(text="👤 Мой грузовик")
    builder.button(text="👑 Админ-панель")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

# Меню статуса грузовика для владельца
def get_truck_status_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 На базе", callback_data="status_base")
    builder.button(text="🟡 В рейсе", callback_data="status_trip")
    builder.button(text="🔴 На стоянке", callback_data="status_parking")
    builder.button(text="🔓 Освободить грузовик", callback_data="release_truck")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()

@dp_start_handler := None # заглушка для порядка

async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (message.from_user.id, message.from_user.username or "Без имени")
        )
        await db.commit()
    
    await message.answer(
        "Привет! Добро пожаловать в систему управления грузовиками.\n"
        "Выбирай нужное действие на клавиатуре внизу 👇",
        reply_markup=get_main_keyboard()
    )

# Команда /friend
async def cmd_friend(message: types.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(DISTINCT owner_id) FROM trucks WHERE owner_id IS NOT NULL") as cursor:
            with_trucks = (await cursor.fetchone())[0]
            
        without_trucks = total_users - with_trucks
        if without_trucks < 0:
            without_trucks = 0

    await message.answer(
        f"📊 **Статистика системы:**\n\n"
        f"👥 Всего людей в базе: **{total_users}**\n"
        f"🚛 С фурами (заняли грузовик): **{with_trucks}**\n"
        f"🚶 Без фур: **{without_trucks}**"
    )

# Просмотр списка грузовиков
@router_message_trucks := None
async def show_trucks(message: types.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, name, description, photo_id, status, status_place, owner_id FROM trucks") as cursor:
            trucks = await cursor.fetchall()

    if not trucks:
        await message.answer("Пока что нет ни одного добавленного грузовика.")
        return

    for truck in trucks:
        t_id, name, desc, photo_id, status, status_place, owner_id = truck
        
        circle = "🟢" if status == "свободен" else "🔴"
        status_text = f"{circle} Свободен" if status == "свободен" else f"🔴 Занят (Статус: {status_place})"

        builder = InlineKeyboardBuilder()
        if status == "свободен":
            builder.button(text="📌 Занять грузовик", callback_data=f"take_{t_id}")
        else:
            builder.button(text="🔒 Занят", callback_data="already_taken")

        text = (
            f"🚛 **{name}**\n"
            f"📝 Описание: {desc}\n"
            f"Состояние: {status_text}"
        )

        if photo_id:
            await message.answer_photo(photo=photo_id, caption=text, reply_markup=builder.as_markup())
        else:
            await message.answer(text, reply_markup=builder.as_markup())

# Кнопка «Мой грузовик»
async def my_truck(message: types.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, name, description, photo_id, status_place FROM trucks WHERE owner_id = ?",
            (message.from_user.id,)
        ) as cursor:
            truck = await cursor.fetchone()

    if not truck:
        await message.answer("У тебя сейчас не занят ни один грузовик.")
        return

    t_id, name, desc, photo_id, status_place = truck
    text = (
        f"🛑 **Твой текущий грузовик:**\n"
        f"🚛 **{name}**\n"
        f"📝 {desc}\n"
        f"📍 Текущее положение: **{status_place}**"
    )
    
    if photo_id:
        await message.answer_photo(photo=photo_id, caption=text, reply_markup=get_truck_status_keyboard())
    else:
        await message.answer(text, reply_markup=get_truck_status_keyboard())

# Callback на занятие грузовика
async def callback_take_truck(callback: types.CallbackQuery):
    truck_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_FILE) as db:
        # Проверим, нет ли уже грузовика у этого юзера
        async with db.execute("SELECT id FROM trucks WHERE owner_id = ?", (user_id,)) as cursor:
            existing = await cursor.fetchone()
        
        if existing:
            await callback.answer("У тебя уже есть занятый грузовик! Сначала освободи его.", show_alert=True)
            return

        # Проверим, свободен ли целевой грузовик
        async with db.execute("SELECT status FROM trucks WHERE id = ?", (truck_id,)) as cursor:
            row = await cursor.fetchone()
            
        if not row or row[0] == "занят":
            await callback.answer("Этот грузовик уже кто-то занял!", show_alert=True)
            return

        # Занимаем
        await db.execute(
            "UPDATE trucks SET status = 'занят', owner_id = ?, status_place = 'на базе' WHERE id = ?",
            (user_id, truck_id)
        )
        await db.commit()

    await callback.message.answer("✅ Ты успешно занял грузовик! Теперь он отображается в разделе «Мой грузовик».")
    await callback.answer()

# Управление статусами своего грузовика
async def callback_truck_status(callback: types.CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_FILE) as db:
        if action == "release_truck":
            await db.execute(
                "UPDATE trucks SET status = 'свободен', owner_id = NULL, status_place = 'на базе' WHERE owner_id = ?",
                (user_id,)
            )
            await db.commit()
            await callback.message.edit_caption(caption="🔓 Ты освободил грузовик.") if callback.message.caption else await callback.message.edit_text("🔓 Ты освободил грузовик.")
            await callback.answer()
            return

        new_status = "на базе"
        if action == "status_trip":
            new_status = "в рейсе"
        elif action == "status_parking":
            new_status = "на стоянке"

        await db.execute(
            "UPDATE trucks SET status_place = ? WHERE owner_id = ?",
            (new_status, user_id)
        )
        await db.commit()

    await callback.answer(f"Статус изменен на: {new_status}")

# Админ-панель вход
async def admin_panel_handler(message: types.Message, state: FSMContext):
    await message.answer("🔑 Введи пароль от админ-панели:")
    await state.set_state(AdminStates.waiting_for_password)

async def check_admin_password(message: types.Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        builder = ReplyKeyboardBuilder()
        builder.button(text="➕ Добавить грузовик")
        builder.button(text="📋 Занятые грузовики")
        builder.button(text="👷 Список работников")
        builder.button(text="🚪 Выход из админки")
        builder.adjust(2, 2)
        
        await message.answer("✅ Добро пожаловать в админ-панель!", reply_markup=builder.as_markup(resize_keyboard=True))
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль. Попробуй еще раз или вернись в меню.", reply_markup=get_main_keyboard())
        await state.clear()

# Выход из админки
async def exit_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Выход из админ-панели выполнен.", reply_markup=get_main_keyboard())

# Добавление грузовика шаг 1
async def admin_start_add_truck(message: types.Message, state: FSMContext):
    await message.answer("Введи название нового грузовика:")
    await state.set_state(AdminStates.waiting_for_name)

async def admin_get_truck_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введи описание грузовика:")
    await state.set_state(AdminStates.waiting_for_desc)

async def admin_get_truck_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("Отправь фото грузовика (картинкой):")
    await state.set_state(AdminStates.waiting_for_photo)

async def admin_get_truck_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправ именно фото.")
        return
    
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO trucks (name, description, photo_id) VALUES (?, ?, ?)",
            (data['name'], data['desc'], photo_id)
        )
        await db.commit()

    await message.answer("✅ Грузовик успешно добавлен в базу!", reply_markup=get_main_keyboard())
    await state.clear()

# Просмотр занятых грузовиков админом
async def admin_view_busy(message: types.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT t.name, u.username FROM trucks t JOIN users u ON t.owner_id = u.user_id WHERE t.status = 'занят'"
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Сейчас нет занятых грузовиков.")
        return

    text = "🔴 **Занятые грузовики и их водители:**\n\n"
    for r in rows:
        text += f"🚛 Грузовик: **{r[0]}** | Работник: @{r[1]}\n"
    
    await message.answer(text)

# Список работников админом
async def admin_view_workers(message: types.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT username, user_id FROM users") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("В базе пока нет пользователей.")
        return

    text = "👷 **Список всех зарегистрированных работников:**\n\n"
    for r in rows:
        text += f"👤 @{r[0]} (ID: `{r[1]}`)\n"
    
    await message.answer(text)


async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Регистрация команд и кнопок
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_friend, Command("friend"))
    
    dp.message.register(show_trucks, F.text == "🚛 Список грузовиков")
    dp.message.register(my_truck, F.text == "👤 Мой грузовик")
    
    # Админка
    dp.message.register(admin_panel_handler, F.text == "👑 Админ-панель")
    dp.message.register(exit_admin, F.text == "🚪 Выход из админки")
    dp.message.register(admin_start_add_truck, F.text == "➕ Добавить грузовик")
    dp.message.register(admin_view_busy, F.text == "📋 Занятые грузовики")
    dp.message.register(admin_view_workers, F.text == "👷 Список работников")

    # Состояния FSM
    dp.message.register(check_admin_password, AdminStates.waiting_for_password)
    dp.message.register(admin_get_truck_name, AdminStates.waiting_for_name)
    dp.message.register(admin_get_truck_desc, AdminStates.waiting_for_desc)
    dp.message.register(admin_get_truck_photo, AdminStates.waiting_for_photo)

    # Колбэки
    dp.callback_query.register(callback_take_truck, F.data.startswith("take_"))
    dp.callback_query.register(callback_truck_status, F.data.in_({"status_base", "status_trip", "status_parking", "release_truck"}))

    print("Бот успешно запущен на планшете с локальной базой!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())