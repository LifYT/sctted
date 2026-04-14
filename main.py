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
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    sys.exit("❌ ОШИБКА: Переменная BOT_TOKEN не найдена.")

ADMIN_ID = 5822741823
CHANNEL_ID = '@sacredvisuals'
CHANNEL_URL = 'https://t.me/sacredvisuals'
FREE_VERSION_URL = "https://www.dropbox.com/scl/fi/fud621oa9imlxniv4vpx6/SacredVisuals-1.21.4-FREE.jar?rlkey=enae4vae8pszr96adcgewzf3c&st=hhgt0vqf&dl=1"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗЫ ---
promo_db = {"LIF": {"percent": 10, "desc": "Скидка 10%"} }
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
    buttons = [[InlineKeyboardButton(text=f"{n} — {math.ceil(p*(1-discount_percent/100))}₽", callback_data=c)] for c, n, p in plans]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ОБРАБОТЧИКИ ЗАКРЫТИЯ ---

# Кнопка для юзера
@dp.callback_query(F.data == "user_close_ticket")
async def user_close_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤝 Обращение завершено. Вы вернулись в меню.", reply_markup=main_keyboard())
    await bot.send_message(ADMIN_ID, f"🚫 **Юзер @{callback.from_user.username} закрыл тикет (кнопкой).**", parse_mode="Markdown")
    await callback.answer()

# Команда /close (общая)
@dp.message(Command("close"))
async def close_ticket_cmd(message: types.Message, state: FSMContext):
    # 1. Если пишет АДМИН в ответ на сообщение
    if message.from_user.id == ADMIN_ID and message.reply_to_message:
        try:
            raw_text = message.reply_to_message.text or message.reply_to_message.caption
            uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
            
            # Очищаем состояние того пользователя
            u_state = FSMContext(storage=dp.storage, key=types.StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
            await u_state.clear()
            
            await bot.send_message(uid, "✅ **Ваш тикет был закрыт администратором.**", reply_markup=main_keyboard(), parse_mode="Markdown")
            await message.answer(f"✅ Тикет [ID: {uid}] закрыт для обеих сторон.")
        except Exception:
            await message.answer("❌ Ошибка: Вы должны ответить на сообщение, содержащее [TICKET_ID: ...]")
    
    # 2. Если пишет ЮЗЕР (или админ сам себе)
    else:
        await state.clear()
        await message.answer("🤝 Обращение завершено. Вы вернулись в меню.", reply_markup=main_keyboard())
        if message.from_user.id != ADMIN_ID:
            await bot.send_message(ADMIN_ID, f"🚫 **Юзер @{message.from_user.username} закрыл тикет (командой).**", parse_mode="Markdown")

# --- ГЛАВНАЯ ЛОГИКА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    await message.answer(f"👋 Привет, {message.from_user.first_name}!\n✨ SacredVisuals приветствует тебя.", reply_markup=main_keyboard())

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer("🆓 **Бесплатная версия**\nНажми кнопку для перехода:", reply_markup=download_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(
        "💬 **Чат поддержки открыт.**\nПишите сообщение, админ ответит вам здесь.\n\n_Чтобы выйти, используйте кнопку ниже или /close_", 
        reply_markup=user_close_ticket_kb(),
        parse_mode="Markdown"
    )
    await bot.send_message(ADMIN_ID, f"🆕 **Новый тикет**\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}", parse_mode="Markdown")

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    # Если это команда /close — не пересылаем (её перехватит Command("close"))
    if message.text == "/close": return

    await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
    await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text == "/close": return
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# --- ПОКУПКА ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 Введите промокод:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]]))

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Нет", discount=0)
    await callback.message.edit_text("🛒 Выберите тариф:", reply_markup=plans_kb(0))
    await state.set_state(BuyFlow.waiting_for_plan)

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("🧾 **Заявка на покупку создана.**\nПрикрепите чек оплаты или задайте вопрос админу:", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"💰 **Новый заказ!**\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}", parse_mode="Markdown")

# --- ПРОЧЕЕ ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    await message.answer(f"🛠 Админ-панель\nВсего юзеров: {len(users_db)}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
