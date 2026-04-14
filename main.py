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
    sys.exit("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в настройках хостинга.")

ADMIN_ID = 5822741823
CHANNEL_ID = '@sacredvisuals'
CHANNEL_URL = 'https://t.me/sacredvisuals'
FREE_VERSION_URL = "https://t.me/sacredvisuals/1" # Твоя ссылка

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
    buttons = [[InlineKeyboardButton(text=f"{n} — {math.ceil(p*(1-discount_percent/100))}₽", callback_data=c)] for c, n, p in plans]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Ключи", callback_data="adm_list_keys")],
        [InlineKeyboardButton(text="❌ Закрыть меню", callback_data="adm_close_menu")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    if await is_subscribed(message.from_user.id):
        await message.answer(f"👋 Привет, {message.from_user.first_name}!\n\n✨ Добро пожаловать.", reply_markup=main_keyboard())
    else:
        await message.answer("❌ Подпишитесь на канал для доступа:", reply_markup=sub_keyboard())

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer(f"🆓 **Бесплатная версия доступна тут:**\n\n{FREE_VERSION_URL}", parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    await message.answer(f"🛠 Админ-панель\nЮзеров: {len(users_db)}", reply_markup=admin_kb())

# --- ИСПРАВЛЕННЫЙ ТИКЕТ И /CLOSE ---

@dp.message(Command("close"))
async def close_ticket_cmd(message: types.Message, state: FSMContext):
    # Если пишет админ в ответ на тикет
    if message.from_user.id == ADMIN_ID and message.reply_to_message:
        try:
            text = message.reply_to_message.text or message.reply_to_message.caption
            uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
            user_state = FSMContext(storage=dp.storage, key=types.StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
            await user_state.clear()
            await bot.send_message(uid, "✅ Ваше обращение закрыто администратором.", reply_markup=main_keyboard())
            await message.answer(f"✅ Тикет {uid} закрыт.")
        except:
            await message.answer("❌ Ошибка: ответьте на сообщение из тикета.")
    # Если пишет сам пользователь, чтобы выйти из режима поддержки
    else:
        current_state = await state.get_state()
        if current_state == TicketFlow.in_ticket:
            await state.clear()
            await message.answer("🤝 Обращение завершено. Вы вернулись в меню.", reply_markup=main_keyboard())
        else:
            await message.answer("У вас нет активных тикетов.")

@dp.message(TicketFlow.in_ticket)
async def ticket_msg_handler(message: types.Message):
    # Если пользователь в тикете прислал НЕ команду, пересылаем админу
    if message.text and message.text.startswith("/"):
        return # Игнорируем команды, чтобы их обработал соответствующий хендлер

    await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
    await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text and message.text.startswith("/"): return 
    try:
        text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# --- ОСТАЛЬНОЕ ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 Вы в чате поддержки. Пишите сообщение.\nЧтобы выйти, напишите /close", parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"🆕 Тикет\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}")

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 Введите промокод или нажмите кнопку:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]]))

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Нет", discount=0)
    await callback.message.edit_text("🛒 Выберите тариф:", reply_markup=plans_kb(0))
    await state.set_state(BuyFlow.waiting_for_plan)

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("🧾 Заявка создана. Опишите ваш вопрос или подтвердите оплату здесь:")
    await bot.send_message(ADMIN_ID, f"🆕 Новый заказ\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}")

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    # Тут твоя логика проверки ключа
    await message.answer("❌ Ключ не найден или уже активирован.")
    await state.clear()

@dp.callback_query(F.data == "adm_close_menu")
async def adm_close(c: types.CallbackQuery): await c.message.delete()

@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Отправьте сообщение для рассылки:")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def do_broadcast(message: types.Message, state: FSMContext):
    for uid in users_db:
        try: await bot.copy_message(uid, message.chat.id, message.message_id)
        except: continue
    await message.answer("✅ Готово")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
