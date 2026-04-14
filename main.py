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
FREE_VERSION_URL = "https://www.dropbox.com/scl/fi/fud621oa9imlxniv4vpx6/SacredVisuals-1.21.4-FREE.jar?rlkey=enae4vae8pszr96adcgewzf3c&st=hhgt0vqf&dl=1"

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
        if discount_percent > 0: text += f" (-{discount_percent}%)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    await message.answer(f"👋 Привет, {message.from_user.first_name}!\nДобро пожаловать в SacredVisuals.", reply_markup=main_keyboard())

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer("🆓 **Бесплатная версия**\nНажми для перехода:", reply_markup=download_keyboard(), parse_mode="Markdown")
    await callback.answer()

# --- ЦЕПОЧКА ПОКУПКИ ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 **Введите промокод** (или нажмите «Нету»):", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]]),
        parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Нет", discount=0)
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
        await message.answer(f"✅ Промокод `{code}` применён!", reply_markup=plans_kb(discount), parse_mode="Markdown")
    else:
        await message.answer("❌ Неверный код. Попробуйте еще раз или используйте кнопку «Нету» в сообщении выше.")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    promo = data.get("promo", "Нет")
    discount = data.get("discount", 0)
    
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))

    # ПЕРЕВОДИМ В РЕЖИМ ТИКЕТА
    await state.set_state(TicketFlow.in_ticket)
    
    # Сообщение пользователю
    await callback.message.answer(
        f"🧾 **Заявка создана!**\n📦 Тариф: {name}\n💵 К оплате: {final_price}₽\n\n"
        f"💬 Напишите сообщение или прикрепите чек. Админ ответит прямо здесь:",
        reply_markup=user_close_ticket_kb(), parse_mode="Markdown"
    )
    
    # КРИТИЧЕСКОЕ УВЕДОМЛЕНИЕ АДМИНУ
    await bot.send_message(
        ADMIN_ID, 
        f"💰 **НОВЫЙ ЗАКАЗ**\n"
        f"[TICKET_ID: {callback.from_user.id}]\n"
        f"👤 Юзер: @{callback.from_user.username}\n"
        f"🆔 ID: {callback.from_user.id}\n"
        f"📦 Тариф: {name}\n"
        f"💵 Сумма: {final_price}₽\n"
        f"🎟 Промо: {promo}",
        parse_mode="Markdown"
    )
    await callback.answer()

# --- ЛОГИКА ТИКЕТОВ ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 **Чат поддержки открыт.**\nПишите ваш вопрос:", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
    
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
    
    # Отправляем админу заголовок с ID, чтобы он мог сделать Reply
    await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
    # Копируем само сообщение (текст, фото, стикеры)
    await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text == "/close": return
    try:
        # Ищем ID в тексте сообщения, на которое отвечает админ
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except:
        await message.answer("❌ Ошибка: Не найден ID пользователя. Ответьте (Reply) на сообщение с пометкой TICKET_ID.")

# --- УПРАВЛЕНИЕ ТИКЕТОМ ---

@dp.callback_query(F.data == "user_close_ticket")
async def user_close_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤝 Обращение завершено. Главное меню:", reply_markup=main_keyboard())
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
            await message.answer(f"✅ Тикет [ID: {uid}] успешно закрыт.")
        except:
            await message.answer("❌ Ошибка при закрытии через команду.")
    else:
        await state.clear()
        await message.answer("🤝 Обращение завершено.", reply_markup=main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
