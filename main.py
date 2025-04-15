import asyncio
import sqlite3
import random
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Инициализация бота
API_TOKEN = ""
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)

# Список цитат (будет заполнен при запуске)
QUOTES = []


# Функция для скрейпинга цитат с сайта
def fetch_quotes():
    global QUOTES
    url = "https://ru.citaty.net/temy/distsiplina/"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Находим все цитаты на странице
        quote_elements = soup.find_all("div", class_="quote__body")
        QUOTES = [quote.get_text(strip=True) for quote in quote_elements]
        if not QUOTES:
            QUOTES = [
                "Дисциплина — это решение делать то, чего очень не хочется делать, чтобы достичь того, чего очень хочется достичь."]
        print(f"Загружено {len(QUOTES)} цитат")
    except Exception as e:
        print(f"Ошибка при загрузке цитат: {e}")
        QUOTES = [
            "Дисциплина — это решение делать то, чего очень не хочется делать, чтобы достичь того, чего очень хочется достичь."]


# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()

    # Таблица для задач
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        task TEXT,
        time TEXT
    )""")

    # Таблица для пользователей
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY
    )""")

    # Проверяем, есть ли столбец id в таблице tasks
    c.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in c.fetchall()]
    if 'id' not in columns:
        c.execute("""CREATE TABLE temp_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            task TEXT,
            time TEXT
        )""")
        c.execute(
            "INSERT INTO temp_tasks (user_id, category, task, time) SELECT user_id, category, task, time FROM tasks")
        c.execute("DROP TABLE tasks")
        c.execute("ALTER TABLE temp_tasks RENAME TO tasks")

    conn.commit()
    conn.close()


init_db()


# Функция для добавления пользователя в базу
def add_user(user_id):
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


# Функция для получения всех пользователей
def get_all_users():
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users


# Фоновая задача для отправки цитат
async def send_quotes_periodically():
    while True:
        if QUOTES:
            quote = random.choice(QUOTES)
            users = get_all_users()
            for user_id in users:
                try:
                    await bot.send_message(user_id, f"💡 Цитата о дисциплине:\n{quote}")
                except Exception as e:
                    print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
        await asyncio.sleep(300)  # 5 минут = 300 секунд


# Определение состояний для FSM
class TaskForm(StatesGroup):
    category = State()
    task = State()
    time = State()
    delete_id = State()


# Функция для создания кнопки "Меню"
def get_menu_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Меню", callback_data="menu")]
    ])


# Команда /start
@dp.message(CommandStart())
async def start_command(message: Message):
    user_id = message.from_user.id
    add_user(user_id)  # Добавляем пользователя в базу
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Школа", callback_data="category_school")],
        [InlineKeyboardButton(text="Хобби", callback_data="category_hobby")],
        [InlineKeyboardButton(text="Свободное время", callback_data="category_freetime")]
    ])
    await message.answer("Выберите категорию:", reply_markup=keyboard)


# Обработка кнопки "Меню"
@dp.callback_query(lambda c: c.data == "menu")
async def process_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Школа", callback_data="category_school")],
        [InlineKeyboardButton(text="Хобби", callback_data="category_hobby")],
        [InlineKeyboardButton(text="Свободное время", callback_data="category_freetime")]
    ])
    await callback.message.edit_text("Выберите категорию:", reply_markup=keyboard)
    await callback.answer()


# Обработка выбора категории
@dp.callback_query(lambda c: c.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить задачу", callback_data=f"add_{category}"),
            InlineKeyboardButton(text="Посмотреть все", callback_data=f"view_{category}")
        ],
        [InlineKeyboardButton(text="Удалить задачу", callback_data=f"delete_{category}")]
    ])
    await callback.message.edit_text(f"Выбрана категория: {category.capitalize()}", reply_markup=keyboard)
    await callback.answer()


# Обработка кнопки "Добавить задачу"
@dp.callback_query(lambda c: c.data.startswith("add_"))
async def add_task(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите описание задачи:")
    await state.set_state(TaskForm.task)
    await callback.answer()


# Получение описания задачи
@dp.message(TaskForm.task)
async def process_task_description(message: Message, state: FSMContext):
    await state.update_data(task=message.text)
    await message.answer("Введите время выполнения задачи (например, 14:00):", reply_markup=get_menu_button())
    await state.set_state(TaskForm.time)


# Получение времени и сохранение задачи
@dp.message(TaskForm.time)
async def process_task_time(message: Message, state: FSMContext):
    user_data = await state.get_data()
    category = user_data["category"]
    task = user_data["task"]
    time = message.text
    user_id = message.from_user.id

    # Сохранение в базу данных
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()
    c.execute("INSERT INTO tasks (user_id, category, task, time) VALUES (?, ?, ?, ?)",
              (user_id, category, task, time))
    conn.commit()
    conn.close()

    await message.answer(
        f"Задача '{task}' добавлена в категорию '{category.capitalize()}' на {time}!",
        reply_markup=get_menu_button()
    )
    await state.clear()


# Обработка кнопки "Посмотреть все"
@dp.callback_query(lambda c: c.data.startswith("view_"))
async def view_tasks(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    user_id = callback.from_user.id

    # Получение задач из базы данных
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()
    c.execute("SELECT id, task, time FROM tasks WHERE user_id = ? AND category = ?", (user_id, category))
    tasks = c.fetchall()
    conn.close()

    if tasks:
        response = f"Задачи в категории '{category.capitalize()}':\n"
        for task_id, task, time in tasks:
            response += f"ID: {task_id} - {task} ({time})\n"
    else:
        response = f"В категории '{category.capitalize()}' пока нет задач."

    await callback.message.edit_text(response, reply_markup=get_menu_button())
    await callback.answer()


# Обработка кнопки "Удалить задачу"
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_task_prompt(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await callback.message.edit_text("Введите номер (ID) задачи для удаления:")
    await state.set_state(TaskForm.delete_id)
    await callback.answer()


# Удаление задачи по ID
@dp.message(TaskForm.delete_id)
async def process_task_deletion(message: Message, state: FSMContext):
    user_data = await state.get_data()
    category = user_data["category"]
    user_id = message.from_user.id
    try:
        task_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный номер задачи (целое число).",
                             reply_markup=get_menu_button())
        return

    # Проверка и удаление задачи
    conn = sqlite3.connect("schedule.db")
    c = conn.cursor()
    c.execute("SELECT id FROM tasks WHERE id = ? AND user_id = ? AND category = ?",
              (task_id, user_id, category))
    task = c.fetchone()
    if task:
        c.execute("DELETE FROM tasks WHERE id = ? AND user_id = ? AND category = ?",
                  (task_id, user_id, category))
        conn.commit()
        await message.answer(f"Задача с ID {task_id} удалена!", reply_markup=get_menu_button())
    else:
        await message.answer(f"Задача с ID {task_id} не найдена в категории '{category.capitalize()}'.",
                             reply_markup=get_menu_button())
    conn.close()
    await state.clear()


# Запуск бота
async def main():
    # Загружаем цитаты при старте
    fetch_quotes()
    # Запускаем фоновую задачу отправки цитат
    asyncio.create_task(send_quotes_periodically())
    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    print('Бот Дисциплина запущен')
    asyncio.run(main())

