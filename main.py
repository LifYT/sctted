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
API_TOKEN = os.getenv("BOT_TOKEN") or '8311674459:AAG9Ac0Dmwk7HTW1jY7i1srxFawOMG73-Fg'
ADMIN_ID = 5822741823  
CHANNEL_ID = '@sacredvisuals' 
CHANNEL_URL = 'https://t.me/sacredvisuals'
FREE_VERSION_URL = "https://t.me/sacredvisuals/1"

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

# --- КЛАВИАТУРЫ ---

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить клиент", callback_data="buy")],
        [InlineKeyboardButton(text="🆓 Бесплатная версия", callback_data="free_version")],
        [InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ])

def user_close_ticket_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть обращение", callback_data="user_close_ticket")]
    ])

def download_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать", url=FREE_VERSION_URL)]
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

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    await message.answer(f"👋 Привет, {message.from_user.first_name}!\n✨ Добро пожаловать.", reply_markup=main_keyboard())

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer("🆓 **Бесплатная версия**\nНажми кнопку для перехода:", reply_markup=download_keyboard(), parse_mode="Markdown")
    await callback.answer()

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
    await state.set_state(BuyFlow.waiting_for_plan)
    await callback.message.edit_text("🛒 **Выберите тариф:**", reply_markup=plans_kb(0), parse_mode="Markdown")
    await callback.answer()

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    if code in promo_db:
        discount = promo_db[code]["percent"]
        await state.update_data(promo=code, discount=discount)
        await state.set_state(BuyFlow.waiting_for_plan)
        await message.answer(f"✅ Промокод `{code}` применён!\nВыберите тариф:", reply_markup=plans_kb(discount), parse_mode="Markdown")
    else:
        await message.answer("❌ Неверный промокод. Попробуйте еще раз или нажмите кнопку «Нету» выше.")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    promo = data.get("promo", "Без промокода")
    discount = data.get("discount", 0)
    
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))

    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(
        f"🧾 **Заявка создана!**\n📦 Тариф: *{name}*\n🎟 Промокод: *{promo}*\n💵 К оплате: *{final_price}₽*\n\n"
        f"💬 Опишите ваш вопрос или прикрепите чек оплаты, админ ответит здесь:",
        reply_markup=user_close_ticket_kb(),
        parse_mode="Markdown"
    )
    
    # УВЕДОМЛЕНИЕ АДМИНУ (с обязательным ID для ответа)
    await bot.send_message(
        ADMIN_ID, 
        f"💰 **НОВЫЙ ЗАКАЗ**\n"
        f"[TICKET_ID: {callback.from_user.id}]\n"
        f"👤 Юзер: @{callback.from_user.username}\n"
        f"📦 Тариф: {name}\n"
        f"🎟 Промокод: {promo}\n"
        f"💵 Сумма: {final_price}₽",
        parse_mode="Markdown"
    )
    await callback.answer()

# --- ТИКЕТЫ И ПОДДЕРЖКА ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 **Чат поддержки открыт.**\nПишите сообщение админу:", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
    
    await bot.send_message(
        ADMIN_ID, 
        f"🆘 **НОВЫЙ ТИКЕТ**\n"
        f"[TICKET_ID: {callback.from_user.id}]\n"
        f"👤 Юзер: @{callback.from_user.username}",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    if message.text == "/close": return
    
    # Дублируем ID тикета админу при каждом сообщении для удобства Reply
    await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
    await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text == "/close": return
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except:
        await message.answer("❌ Ошибка: не удалось найти ID пользователя в сообщении.")

# --- ЗАКРЫТИЕ ---

@dp.callback_query(F.data == "user_close_ticket")
async def user_close_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤝 Обращение завершено. Вы вернулись в меню.", reply_markup=main_keyboard())
    await bot.send_message(ADMIN_ID, f"🚫 **Тикет закрыт пользователем**\n[TICKET_ID: {callback.from_user.id}]")
    await callback.answer()

@dp.message(Command("close"))
async def close_ticket_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID and message.reply_to_message:
        try:
            raw_text = message.reply_to_message.text or message.reply_to_message.caption
            uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
            u_state = FSMContext(storage=dp.storage, key=types.StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
            await u_state.clear()
            await bot.send_message(uid, "✅ **Ваш тикет закрыт администратором.**", reply_markup=main_keyboard(), parse_mode="Markdown")
            await message.answer(f"✅ Тикет [ID: {uid}] закрыт.")
        except:
            await message.answer("❌ Ошибка при закрытии.")
    else:
        await state.clear()
        await message.answer("🤝 Обращение завершено.", reply_markup=main_keyboard())

# --- КЛЮЧИ ---

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        await state.set_state(TicketFlow.in_ticket)
        await message.answer(f"✅ **Ключ активирован!**\n📦 Тариф: {PLANS.get(data['plan'])}\n💬 Чат с поддержкой открыт:", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
        await bot.send_message(ADMIN_ID, f"🟢 **КЛЮЧ АКТИВИРОВАН**\n[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}\n🔑 {key}")
    else:
        await message.answer("❌ Неверный ключ.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
