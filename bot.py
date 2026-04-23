import asyncio
import json
import uuid
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "ADD_YOUR_TOKEN"
DATA_FILE = "db.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ================= DB =================

def load_db():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

db = load_db()

def ensure_user(user_id):
    if user_id not in db:
        db[user_id] = {
            "tasks": [],
            "score": 0,
            "links": {"parents": [], "teachers": []}
        }
        save_db()

def get_task(user_id, task_id):
    if user_id not in db:
        return None
    return next((t for t in db[user_id]["tasks"] if t["id"] == task_id), None)

# ================= FSM =================

class AddTask(StatesGroup):
    text = State()
    mode = State()
    time = State()

class EditTask(StatesGroup):
    text = State()
    time = State()

# ================= UI =================

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📋 Мои задачи")],
        [KeyboardButton(text="📊 Статистика")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

time_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Дедлайн")],
        [KeyboardButton(text="⏱ Через время")],
        [KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True
)

def task_kb(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅", callback_data=f"done:{task_id}"),
            InlineKeyboardButton(text="✏️", callback_data=f"edit:{task_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"del:{task_id}")
        ]
    ])

def clear_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Очистить выполненные", callback_data="clear_done")]
    ])

# ================= START =================

@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(msg.from_user.id)
    ensure_user(user_id)

    await msg.answer(f"🚀 Трекер задач\n\nТвой ID: {user_id}", reply_markup=menu)

# ================= BASIC =================

@dp.message(F.text == "❌ Отмена")
async def cancel(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Отменено", reply_markup=menu)

@dp.message(F.text == "📋 Мои задачи")
async def show_tasks(msg: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(msg.from_user.id)
    ensure_user(user_id)

    tasks = db[user_id]["tasks"]

    if not tasks:
        return await msg.answer("📭 Нет задач")

    for t in tasks:
        status = "✅" if t["done"] else "❌"
        deadline = datetime.fromisoformat(t["deadline"]).strftime("%d.%m %H:%M")

        await msg.answer(
            f"{status} {t['text']}\n📅 {deadline}",
            reply_markup=task_kb(t["id"]) if not t["done"] else None
        )

    if any(t["done"] for t in tasks):
        await msg.answer("⚙️ Управление задачами:", reply_markup=clear_kb())

@dp.message(F.text == "📊 Статистика")
async def stats(msg: types.Message):
    user_id = str(msg.from_user.id)
    ensure_user(user_id)

    tasks = db[user_id]["tasks"]

    done = sum(1 for t in tasks if t["done"])
    total = len(tasks)
    percent = int((done / total) * 100) if total else 0

    await msg.answer(
        f"📊 Статистика:\n"
        f"✅ {done}/{total}\n"
        f"📈 {percent}%\n"
        f"🏆 Баллы: {db[user_id]['score']}"
    )

# ================= ADD TASK =================

@dp.message(F.text == "➕ Добавить задачу")
async def add_start(msg: types.Message, state: FSMContext):
    await state.set_state(AddTask.text)
    await msg.answer("✏️ Введи задачу", reply_markup=cancel_kb)

@dp.message(AddTask.text)
async def add_text(msg: types.Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await state.set_state(AddTask.mode)
    await msg.answer("⏳ Как задать время?", reply_markup=time_choice_kb)

@dp.message(AddTask.mode)
async def choose_mode(msg: types.Message, state: FSMContext):
    if msg.text not in ["📅 Дедлайн", "⏱ Через время"]:
        return await msg.answer("❌ Выбери кнопку")

    await state.update_data(mode=msg.text)
    await state.set_state(AddTask.time)

    if msg.text == "📅 Дедлайн":
        await msg.answer("📅 Введи: ДД.ММ ЧЧ:ММ")
    else:
        await msg.answer("⏱ Введи минуты")

@dp.message(AddTask.time)
async def add_time(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = str(msg.from_user.id)
    ensure_user(user_id)

    try:
        if data["mode"] == "📅 Дедлайн":
            deadline = datetime.strptime(msg.text, "%d.%m %H:%M")
            deadline = deadline.replace(year=datetime.now().year)
        else:
            deadline = datetime.now() + timedelta(minutes=int(msg.text))
    except:
        return await msg.answer("❌ Ошибка формата")

    task_id = str(uuid.uuid4())

    db[user_id]["tasks"].append({
        "id": task_id,
        "text": data["text"],
        "done": False,
        "deadline": deadline.isoformat()
    })
    save_db()

    scheduler.add_job(reminder, "date", run_date=deadline, args=[user_id, task_id])

    await state.clear()
    await msg.answer("✅ Задача добавлена", reply_markup=menu)

# ================= CALLBACKS =================

@dp.callback_query(F.data.startswith("done:"))
async def done(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    ensure_user(user_id)

    task_id = callback.data.split(":")[1]
    task = get_task(user_id, task_id)

    if not task:
        return await callback.answer("Ошибка")

    task["done"] = True
    db[user_id]["score"] += 10
    save_db()

    await callback.message.edit_text("✅ Выполнено +10")
    await callback.answer()

    text = f"✅ Ученик выполнил задачу:\n{task['text']}"

    for p in db[user_id]["links"]["parents"]:
        await bot.send_message(int(p), text)

    for t in db[user_id]["links"]["teachers"]:
        await bot.send_message(int(t), text)

@dp.callback_query(F.data.startswith("del:"))
async def delete(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    ensure_user(user_id)

    task_id = callback.data.split(":")[1]
    db[user_id]["tasks"] = [t for t in db[user_id]["tasks"] if t["id"] != task_id]
    save_db()

    await callback.message.edit_text("🗑 Удалено")

@dp.callback_query(F.data.startswith("edit:"))
async def edit_start(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_id=callback.data.split(":")[1])
    await state.set_state(EditTask.text)
    await callback.message.answer("✏️ Новый текст")

@dp.message(EditTask.text)
async def edit_text(msg: types.Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await state.set_state(EditTask.time)
    await msg.answer("⏱ Введи минуты")

@dp.message(EditTask.time)
async def edit_time(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = str(msg.from_user.id)
    ensure_user(user_id)

    task = get_task(user_id, data["task_id"])
    if not task:
        return await msg.answer("Ошибка")

    task["text"] = data["text"]
    task["deadline"] = (datetime.now() + timedelta(minutes=int(msg.text))).isoformat()
    task["done"] = False

    save_db()

    await state.clear()
    await msg.answer("✅ Обновлено", reply_markup=menu)

@dp.callback_query(F.data == "clear_done")
async def clear_done_cb(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    ensure_user(user_id)

    before = len(db[user_id]["tasks"])

    db[user_id]["tasks"] = [t for t in db[user_id]["tasks"] if not t["done"]]
    save_db()

    after = len(db[user_id]["tasks"])

    await callback.message.edit_text(f"🧹 Удалено задач: {before - after}")
    await callback.answer()

# ================= REMINDER =================

async def reminder(user_id, task_id):
    task = get_task(user_id, task_id)
    if not task or task["done"]:
        return

    await bot.send_message(int(user_id), f"⏰ {task['text']}", reply_markup=task_kb(task_id))

# ================= RESTORE =================

async def restore():
    for user_id, user in db.items():
        for t in user["tasks"]:
            if not t["done"]:
                try:
                    deadline = datetime.fromisoformat(t["deadline"])
                    if deadline > datetime.now():
                        scheduler.add_job(reminder, "date", run_date=deadline, args=[user_id, t["id"]])
                except:
                    pass

# ================= LINKS =================

@dp.message(Command("parent"))
async def parent(msg: types.Message):
    args = msg.text.split()

    if len(args) < 2:
        return await msg.answer("❌ Используй: /parent ID")

    student_id = args[1]
    parent_id = str(msg.from_user.id)

    if student_id not in db:
        return await msg.answer("❌ Ученик не найден")

    if parent_id not in db[student_id]["links"]["parents"]:
        db[student_id]["links"]["parents"].append(parent_id)
        save_db()

    await msg.answer("✅ Вы привязаны как родитель")

@dp.message(Command("teacher"))
async def teacher(msg: types.Message):
    args = msg.text.split()

    if len(args) < 2:
        return await msg.answer("❌ Используй: /teacher ID")

    student_id = args[1]
    teacher_id = str(msg.from_user.id)

    if student_id not in db:
        return await msg.answer("❌ Ученик не найден")

    if teacher_id not in db[student_id]["links"]["teachers"]:
        db[student_id]["links"]["teachers"].append(teacher_id)
        save_db()

    await msg.answer("✅ Вы привязаны как учитель")

# ================= MAIN =================

async def main():
    scheduler.start()
    await restore()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())