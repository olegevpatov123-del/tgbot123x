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


TOKEN = ""
DATA_FILE = "db.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()


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



def get_task(user_id, task_id):
    for t in db[user_id]["tasks"]:
        if t["id"] == task_id:
            return t
    return None



class AddTask(StatesGroup):
    text = State()
    time = State()



menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📋 Мои задачи")],
        [KeyboardButton(text="📊 Статистика")],
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)


def task_kb(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{task_id}")]
    ])



@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()

    user_id = str(msg.from_user.id)

    if user_id not in db:
        db[user_id] = {
            "tasks": [],
            "score": 0,
            "links": {
                "parents": [],
                "teachers": []
            }
        }
        save_db()

    await msg.answer(f"🚀 Трекер задач\n\nТвой ID: {user_id}", reply_markup=menu)



@dp.message(F.text == "❌ Отмена")
async def cancel(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Отменено", reply_markup=menu)



@dp.message(F.text == "📋 Мои задачи")
async def show_tasks(msg: types.Message, state: FSMContext):
    await state.clear()

    user_id = str(msg.from_user.id)
    tasks = db[user_id]["tasks"]

    if not tasks:
        return await msg.answer("📭 Нет задач")

    for t in tasks:
        status = "✅" if t["done"] else "❌"
        await msg.answer(
            f"{status} {t['text']}",
            reply_markup=task_kb(t["id"]) if not t["done"] else None
        )



@dp.message(F.text == "📊 Статистика")
async def stats(msg: types.Message, state: FSMContext):
    await state.clear()

    user_id = str(msg.from_user.id)
    tasks = db[user_id]["tasks"]

    done = sum(1 for t in tasks if t["done"])

    await msg.answer(f"📊 Выполнено: {done}/{len(tasks)}\n🏆 Баллы: {db[user_id]['score']}")



@dp.message(F.text == "➕ Добавить задачу")
async def add_start(msg: types.Message, state: FSMContext):
    await state.set_state(AddTask.text)
    await msg.answer("✏️ Введи задачу", reply_markup=cancel_kb)


@dp.message(AddTask.text)
async def add_text(msg: types.Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await state.set_state(AddTask.time)
    await msg.answer("⏱ Через сколько минут напомнить?")


@dp.message(AddTask.time)
async def add_time(msg: types.Message, state: FSMContext):
    try:
        minutes = int(msg.text)
    except:
        return await msg.answer("❌ Введи число")

    user_id = str(msg.from_user.id)
    data = await state.get_data()

    task_id = str(uuid.uuid4())
    deadline = datetime.now() + timedelta(minutes=minutes)

    task = {
        "id": task_id,
        "text": data["text"],
        "done": False,
        "deadline": deadline.isoformat(),
        "reminded": 0
    }

    db[user_id]["tasks"].append(task)
    save_db()

    scheduler.add_job(reminder, "date", run_date=deadline, args=[user_id, task_id])

    await state.clear()
    await msg.answer("✅ Задача добавлена", reply_markup=menu)



@dp.callback_query(F.data.startswith("done:"))
async def done(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    task_id = callback.data.split(":")[1]

    task = get_task(user_id, task_id)
    if not task:
        return await callback.answer("Не найдено")

    task["done"] = True
    db[user_id]["score"] += 10
    save_db()

    await callback.message.edit_text("✅ Выполнено +10")
    await callback.answer()

    
    for p in db[user_id]["links"]["parents"]:
        await bot.send_message(p, "👨‍👩‍👧 Ученик выполнил задачу")

    
    for t in db[user_id]["links"]["teachers"]:
        await bot.send_message(t, "👨‍🏫 Ученик выполнил задачу")



async def reminder(user_id, task_id):
    if user_id not in db:
        return

    task = get_task(user_id, task_id)
    if not task or task["done"]:
        return

    await bot.send_message(
        int(user_id),
        f"⏰ Напоминание:\n{task['text']}",
        reply_markup=task_kb(task_id)
    )

    task["reminded"] += 1
    save_db()

    if task["reminded"] < 3:
        scheduler.add_job(
            reminder,
            "date",
            run_date=datetime.now() + timedelta(minutes=30),
            args=[user_id, task_id]
        )




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



async def main():
    scheduler.start()
    await restore()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())