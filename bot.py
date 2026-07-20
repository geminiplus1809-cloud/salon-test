import asyncio
from datetime import datetime, timedelta, time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, ADMIN_CHAT_ID, DB_PATH
import db as salon_db

def ikb(items):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=cb)] for t, cb in items]
    )

class Booking(StatesGroup):
    service = State()
    master = State()
    date = State()
    time = State()
    contact = State()
    confirm = State()

def fmt_dt(iso_ts: str):
    dt = datetime.fromisoformat(iso_ts)
    return dt.strftime("%d.%m %H:%M")

def generate_slots(conn, master_id: int, days: int = 21):
    cur = conn.cursor()
    today = datetime.now().date()

    for d in range(days):
        day = today + timedelta(days=d)
        start = datetime.combine(day, time(10, 0))
        end = datetime.combine(day, time(19, 0))

        t = start
        while t < end:
            cur.execute(
                "INSERT OR IGNORE INTO slots(master_id, start_ts, is_active) VALUES(?,?,1)",
                (master_id, t.isoformat(timespec="minutes"))
            )
            t += timedelta(minutes=60)

    conn.commit()

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Set it in environment variables.")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    conn = salon_db.connect(DB_PATH)
    salon_db.init_db(conn)
    salon_db.seed_demo(conn)

    generate_slots(conn, master_id=1, days=21)
    generate_slots(conn, master_id=2, days=21)

    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Записаться")],
                [KeyboardButton(text="Контакты / Адрес")],
            ],
            resize_keyboard=True
        )
        await m.answer("Привет! Я бот записи в маникюрный салон.\nВыберите действие:", reply_markup=kb)

    @dp.message(F.text == "Контакты / Адрес")
    async def contacts(m: Message):
        await m.answer("Адрес: тестовый\nТелефон: тестовый\nГрафик: 10:00–19:00\n")

    @dp.message(F.text == "Записаться")
    async def book(m: Message, state: FSMContext):
        services = salon_db.list_services(conn)
        buttons = [(f"{s['name']} ({s['duration_min']} мин)", f"svc:{s['id']}") for s in services]
        await state.set_state(Booking.service)
        await m.answer("Выберите услугу:", reply_markup=ikb(buttons))

    @dp.callback_query(Booking.service, F.data.startswith("svc:"))
    async def pick_service(c: CallbackQuery, state: FSMContext):
        service_id = int(c.data.split(":")[1])
        await state.update_data(service_id=service_id)

        masters = salon_db.list_masters(conn)
        buttons = [(m["name"], f"mst:{m['id']}") for m in masters]
        await state.set_state(Booking.master)
        await c.message.edit_text("Выберите мастера:", reply_markup=ikb(buttons))
        await c.answer()

    @dp.callback_query(Booking.master, F.data.startswith("mst:"))
    async def pick_master(c: CallbackQuery, state: FSMContext):
        master_id = int(c.data.split(":")[1])
        await state.update_data(master_id=master_id)

        dates = salon_db.list_dates_for_master(conn, master_id)
        if not dates:
            await c.message.edit_text("Нет доступных дат. Выберите другого мастера.")
            await state.clear()
            await c.answer()
            return

        buttons = [(d, f"dt:{d}") for d in dates]
        await state.set_state(Booking.date)
        await c.message.edit_text("Выберите дату:", reply_markup=ikb(buttons))
        await c.answer()

    @dp.callback_query(Booking.date, F.data.startswith("dt:"))
    async def pick_date(c: CallbackQuery, state: FSMContext):
        date_str = c.data.split(":", 1)[1]
        data = await state.get_data()
        master_id = data["master_id"]

        times = salon_db.list_times_for_master_and_date(conn, master_id, date_str)
        if not times:
            await c.message.edit_text("На эту дату нет свободного времени. Выберите другую дату.")
            await c.answer()
            return

        buttons = [(fmt_dt(t), f"tm:{t}") for t in times]
        await state.set_state(Booking.time)
        await c.message.edit_text("Выберите время:", reply_markup=ikb(buttons))
        await c.answer()

    @dp.callback_query(Booking.time, F.data.startswith("tm:"))
    async def pick_time(c: CallbackQuery, state: FSMContext):
        start_ts = c.data.split(":", 1)[1]
        await state.update_data(start_ts=start_ts)

        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить контакт", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await state.set_state(Booking.contact)
        await c.message.answer("Отправьте контакт (кнопкой) или напишите телефон текстом:", reply_markup=kb)
        await c.answer()

    @dp.message(Booking.contact)
    async def get_contact(m: Message, state: FSMContext):
        phone = None
        if m.contact and m.contact.phone_number:
            phone = m.contact.phone_number
        elif m.text:
            phone = m.text.strip()

        if not phone:
            await m.answer("Не вижу телефон. Попробуйте ещё раз.")
            return

        await state.update_data(phone=phone, user_name=m.from_user.full_name)
        data = await state.get_data()

        confirm_text = (
            "Проверьте запись:\n"
            f"- Время: {fmt_dt(data['start_ts'])}\n"
            f"- Телефон: {data['phone']}\n\n"
            "Подтвердить?"
        )
        buttons = [("✅ Подтвердить", "ok"), ("❌ Отмена", "cancel")]
        await state.set_state(Booking.confirm)
        await m.answer(confirm_text, reply_markup=ikb(buttons))

    @dp.callback_query(Booking.confirm, F.data == "ok")
    async def confirm(c: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        try:
            salon_db.create_appointment(
                conn,
                user_id=c.from_user.id,
                user_name=data.get("user_name") or c.from_user.full_name,
                phone=data["phone"],
                service_id=data["service_id"],
                master_id=data["master_id"],
                start_ts=data["start_ts"],
            )
        except Exception:
            await c.message.edit_text("Этот слот уже заняли. Начните заново: нажмите «Записаться».")
            await state.clear()
            await c.answer()
            return

        await c.message.edit_text("Запись подтверждена! До встречи.")
        await state.clear()
        await c.answer()

        if ADMIN_CHAT_ID:
            await c.bot.send_message(
                ADMIN_CHAT_ID,
                "Новая запись:\n"
                f"- Клиент: {data.get('user_name')}\n"
                f"- Телефон: {data['phone']}\n"
                f"- Время: {fmt_dt(data['start_ts'])}\n"
            )

    @dp.callback_query(Booking.confirm, F.data == "cancel")
    async def cancel(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await c.message.edit_text("Ок, отменено.")
        await c.answer()

    @dp.message(Command("day"))
    async def admin_day(m: Message):
        if ADMIN_CHAT_ID and m.chat.id != ADMIN_CHAT_ID:
            return
        parts = (m.text or "").split()
        if len(parts) != 2:
            await m.answer("Использование: /day YYYY-MM-DD")
            return
        rows = salon_db.list_appointments_by_date(conn, parts[1])
        if not rows:
            await m.answer("Записей нет.")
            return
        text = "\n".join([
            f"#{r['id']} {fmt_dt(r['start_ts'])} — {r['service']} — {r['master']} — {r['user_name']} ({r['phone']})"
            for r in rows
        ])
        await m.answer(text)

    @dp.message(Command("cancel"))
    async def admin_cancel(m: Message):
        if ADMIN_CHAT_ID and m.chat.id != ADMIN_CHAT_ID:
            return
        parts = (m.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit():
            await m.answer("Использование: /cancel ID")
            return
        salon_db.cancel_appointment(conn, int(parts[1]))
        await m.answer("Отменено.")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
