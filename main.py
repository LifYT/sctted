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
# Получаем токен из настроек BotHost
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    sys.exit("❌ ОШИБКА: Переменная BOT_TOKEN не задана в панели BotHost!")

ADMIN_ID = 5822741823  
CHANNEL_ID = '@sacredvisuals' 
CHANNEL_URL = 'https://t.me/sacredvisuals'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗЫ (Временные) ---
promo_db = {"LIF": {"percent": 10, "desc": "Скидка 10%"}}
users_db = set()
keys_db = {}

PLANS = {
    "week": "Неделя",
    "month": "Месяц",
    "life": "Навсегда"
}

# --- СОСТОЯНИЯ ---
class BuyFlow(StatesGroup):
    waiting_for_promo = State()
    waiting_for_plan = State()

class KeyFlow(StatesGroup):
    waiting_for_key = State()

class TicketFlow(StatesGroup):
    in_ticket = State()

class AdminStates(StatesGroup):
    waiting_for_ad = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    if await is_subscribed(message.from_user.id):
        await message.answer(f"👋 Привет, {message.from_user.first_name}!\nВыберите действие:", reply_markup=main_keyboard())
    else:
        await message.answer("❌ **Доступ ограничен!**\nПодпишитесь на канал:", reply_markup=sub_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена!", reply_markup=main_keyboard())
    else:
        await callback.answer("⚠️ Вы не подписались!", show_alert=True)

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 **Чат поддержки открыт!**\nНапишите сообщение администратору.")
    await bot.send_message(ADMIN_ID, f"🆕 Тикет от @{callback.from_user.username}\n[TICKET_ID: {callback.from_user.id}]", parse_mode="HTML")

# Логика покупки
@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 **Введите промокод**:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]
    ]), parse_mode="Markdown")

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Без промокода", discount=0)
    await callback.message.edit_text("🛒 **Выберите тариф:**", reply_markup=plans_kb(0), parse_mode="Markdown")
    await state.set_state(BuyFlow.waiting_for_plan)

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    if code in promo_db:
        discount = promo_db[code]["percent"]
        await state.update_data(promo=code, discount=discount)
        await message.answer(f"✅ Код `{code}` применён!", reply_markup=plans_kb(discount), parse_mode="Markdown")
        await state.set_state(BuyFlow.waiting_for_plan)
    else:
        await message.answer("❌ Неверный код")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plans = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans[callback.data]
    final_price = math.ceil(price * (1 - data.get("discount", 0) / 100))
    
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(f"🧾 Заявка: {name}\n💵 К оплате: {final_price}₽\nПришлите скрин оплаты:")
    await bot.send_message(ADMIN_ID, f"💰 Заказ от @{callback.from_user.username}\n[TICKET_ID: {callback.from_user.id}]\nТариф: {name}\nСумма: {final_price}₽")

# Система тикетов
@dp.message(TicketFlow.in_ticket)
async def ticket_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
        await bot.copy_message(ADMIN_ID, message.chat.id, message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(uid, message.chat.id, message.message_id)
    except:
        await message.answer("❌ Ошибка: ответьте на сообщение с ID тикета")

# --- ЗАПУСК ---

async def main():
    # Удаляем конфликтный вебхук перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
