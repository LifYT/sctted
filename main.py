import os
import asyncio
import logging
import sys
import math
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- КОНФИГ ---
# Теперь токен берется из переменных окружения BotHost
API_TOKEN = os.getenv("BOT_TOKEN")

# Защита от дурака: если токен не найден, бот напишет об этом в лог
if not API_TOKEN:
    sys.exit("❌ ОШИБКА: Переменная окружения BOT_TOKEN не найдена. Укажите её в панели BotHost.")

ADMIN_ID = 5822741823  
CHANNEL_ID = '@sacredvisuals' 
CHANNEL_URL = 'https://t.me/sacredvisuals'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗЫ ---
promo_db = {"LIF": {"percent": 10, "desc": "Скидка 10%"}}
users_db = set()

keys_db = {}

PLANS = {
    "week": "Неделя",
    "month": "Месяц",
    "life": "Навсегда"
}

# --- STATES ---
class BuyFlow(StatesGroup):
    waiting_for_promo = State()
    waiting_for_plan = State()

class KeyFlow(StatesGroup):
    waiting_for_key = State()

class TicketFlow(StatesGroup):
    in_ticket = State()

class AdminStates(StatesGroup):
    waiting_for_ad = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ---

async def is_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить клиент", callback_data="buy")],
        [InlineKeyboardButton(text="🆓 Бесплатная версия", callback_data="free_version")],
        [InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ])

def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
    ])

def plans_kb(discount_percent=0):
    plans = [("plan_week", "Неделя", 69), ("plan_month", "Месяц", 189), ("plan_life", "Навсегда", 369)]
    buttons = []

    for cb_data, name, price in plans:
        final_price = math.ceil(price * (1 - discount_percent / 100))
        text = f"{name} — {final_price}₽"
        if discount_percent > 0:
            text += f" (скидка {discount_percent}%)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=cb_data)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- START ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)

    if await is_subscribed(message.from_user.id):
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"✨ Добро пожаловать в SacredVisuals.\n"
            f"Выберите действие:",
            reply_markup=main_keyboard()
        )
    else:
        await message.answer(
            "❌ **Доступ ограничен!**\nПодпишитесь на канал:",
            reply_markup=sub_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена!", reply_markup=main_keyboard())
    else:
        await callback.answer("⚠️ Вы не подписались!", show_alert=True)

# --- ПОДДЕРЖКА КНОПКА ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)

    await callback.message.answer(
        "💬 **Вы открыли чат поддержки!**\n\n"
        "Напишите сообщение — администратор ответит здесь.",
        parse_mode="Markdown"
    )

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новый тикет</b>\n\n"
        f"[TICKET_ID: {callback.from_user.id}]\n"
        f"👤 @{callback.from_user.username}\n"
        f"🆔 <code>{callback.from_user.id}</code>",
        parse_mode="HTML"
    )

# --- ПОКУПКА ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer(
        "🎟 **Введите промокод** или нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Без промокода", discount=0)

    await callback.message.edit_text(
        "🛒 **Выберите тариф:**",
        reply_markup=plans_kb(0),
        parse_mode="Markdown"
    )

    await state.set_state(BuyFlow.waiting_for_plan)

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()

    if code in promo_db:
        discount = promo_db[code]["percent"]
        await state.update_data(promo=code, discount=discount)

        await message.answer(
            f"✅ Промокод `{code}` применён!\nВыберите тариф:",
            reply_markup=plans_kb(discount),
            parse_mode="Markdown"
        )

        await state.set_state(BuyFlow.waiting_for_plan)
    else:
        await message.answer("❌ Неверный промокод")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    promo = data.get("promo", "Без промокода")
    discount = data.get("discount", 0)

    plans = {
        "plan_week": ("Неделя", 69),
        "plan_month": ("Месяц", 189),
        "plan_life": ("Навсегда", 369)
    }

    name, price = plans[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))

    user = callback.from_user

    await state.set_state(TicketFlow.in_ticket)

    await callback.message.answer(
        f"🧾 **Заявка создана!**\n\n"
        f"📦 Тариф: *{name}*\n"
        f"🎟 Промокод: *{promo}*\n"
        f"💵 К্যালিфикат: *{final_price}₽*\n\n"
        f"💬 Напишите сообщение — админ ответит здесь:",
        parse_mode="Markdown"
    )

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новый заказ (тикет)</b>\n\n"
        f"[TICKET_ID: {user.id}]\n"
        f"👤 @{user.username}\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"📦 Тариф: {name}\n"
        f"🎟 Промокод: {promo}\n"
        f"💵 Сумма: {final_price}₽",
        parse_mode="HTML"
    )

# --- КЛЮЧИ ---

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()

    if key in keys_db:
        data = keys_db[key]
        desc = data["desc"]
        plan = data["plan"]

        del keys_db[key]

        await state.set_state(TicketFlow.in_ticket)

        await message.answer(
            f"✅ **Ключ успешно активирован!**\n\n"
            f"📦 **Тариф:** *{PLANS.get(plan)}*\n"
            f"🎁 **Вы получили:** *{desc}*\n\n"
            f"💬 Напишите сообщение в поддержку:",
            parse_mode="Markdown"
        )

        await bot.send_message(
            ADMIN_ID,
            f"🟢 <b>Открыт тикет</b>\n\n"
            f"[TICKET_ID: {message.from_user.id}]\n"
            f"👤 @{message.from_user.username}\n"
            f"🆔 <code>{message.from_user.id}</code>\n"
            f"📦 {PLANS.get(plan)} | {desc}",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Неверный ключ")

# --- ТИКЕТЫ ---

@dp.message(TicketFlow.in_ticket)
async def ticket(message: types.Message):
    user = message.from_user

    await bot.send_message(
        ADMIN_ID,
        f"[TICKET_ID: {user.id}]\n👤 @{user.username}"
    )

    await bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def reply(message: types.Message):
    try:
        text = message.reply_to_message.text

        if "[TICKET_ID:" not in text:
            return

        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])

        await bot.copy_message(
            chat_id=uid,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )

    except:
        await message.answer("❌ Ошибка ответа")

# --- АДМИН ---

@dp.message(Command("help"), F.from_user.id == ADMIN_ID)
async def admin_help(message: types.Message):
    await message.answer(
        "🛠 **Команды:**\n\n"
        "/addpromo КОД %\n"
        "/delpromo КОД\n"
        "/addkey КЛЮЧ ТАРИФ ОПИСАНИЕ\n"
        "/list\n"
        "/ad",
        parse_mode="Markdown"
    )

@dp.message(Command("addkey"), F.from_user.id == ADMIN_ID)
async def add_key(message: types.Message):
    parts = message.text.split(maxsplit=3)

    if len(parts) == 4:
        key, plan, desc = parts[1], parts[2], parts[3]

        if plan not in PLANS:
            await message.answer("week / month / life")
            return

        keys_db[key] = {"desc": desc, "plan": plan}
        await message.answer("✅ Ключ добавлен")
    else:
        await message.answer("Формат: /addkey KEY plan desc")

@dp.message(Command("list"), F.from_user.id == ADMIN_ID)
async def list_keys(message: types.Message):
    text = "\n".join([
        f"{k} — {PLANS[v['plan']]} | {v['desc']}"
        for k, v in keys_db.items()
    ]) or "Пусто"

    await message.answer(text)

# --- РАССЫЛКА ---

@dp.message(Command("ad"), F.from_user.id == ADMIN_ID)
async def start_ad(message: types.Message, state: FSMContext):
    await message.answer("📢 Отправь сообщение для рассылки:")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_ad(message: types.Message, state: FSMContext):
    count = 0
    await message.answer("⏳ Рассылка...")

    for uid in users_db:
        try:
            if message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "")
            else:
                await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except:
            continue

    await message.answer(f"✅ Отправлено: {count}")
    await state.clear()

# --- RUN ---

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())