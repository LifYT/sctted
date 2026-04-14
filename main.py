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
from aiogram.fsm.storage.base import StorageKey

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- КОНФИГ ---
API_TOKEN = os.getenv("BOT_TOKEN") or '8311674459:AAG9Ac0Dmwk7HTW1jY7i1srxFawOMG73-Fg'
ADMIN_ID = 5822741823  
CHANNEL_ID = '@sacredvisuals' 
CHANNEL_URL = 'https://t.me/sacredvisuals'
# Прямая ссылка на файл для кнопки
FREE_VERSION_URL = "https://www.dropbox.com/scl/fi/fud621oa9imlxniv4vpx6/SacredVisuals-1.21.4-FREE.jar?rlkey=enae4vae8pszr96adcgewzf3c&st=hhgt0vqf&dl=1"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗЫ ---
promo_db = {"LIF": {"percent": 10, "desc": "Скидка 10%"}}
users_db = set()
keys_db = {}

PLANS = {"week": "Неделя", "month": "Месяц", "life": "Навсегда"}

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
    waiting_for_key_data = State()

# --- КЛАВИАТУРЫ ---

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

def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Добавить ключ", callback_data="adm_addkey")],
        [InlineKeyboardButton(text="📜 Список ключей", callback_data="adm_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")]
    ])

def plans_kb(discount_percent=0):
    plans = [("plan_week", "Неделя", 69), ("plan_month", "Месяц", 189), ("plan_life", "Навсегда", 369)]
    buttons = []
    for cb_data, name, price in plans:
        final_price = math.ceil(price * (1 - discount_percent / 100))
        text = f"{name} — {final_price}₽"
        if discount_percent > 0: text += f" (скидка {discount_percent}%)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ВСПОМОГАТЕЛЬНЫЕ ---

async def is_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    
    if await is_subscribed(message.from_user.id):
        await message.answer(
            f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"✨ Добро пожаловать в <b>SacredVisuals</b>.\n"
            f"Выберите действие в меню ниже:",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "⚠️ <b>Доступ ограничен!</b>\nДля использования бота необходимо подписаться на наш канал.",
            reply_markup=sub_keyboard(),
            parse_mode="HTML"
        )

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ <b>Подписка подтверждена!</b>", reply_markup=main_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("⚠️ Вы всё еще не подписаны!", show_alert=True)

# --- БЕСПЛАТНАЯ ВЕРСИЯ (КРАСИВАЯ КНОПКА) ---

@dp.callback_query(F.data == "free_version")
async def free_v(callback: types.CallbackQuery):
    download_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать .JAR", url=FREE_VERSION_URL)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        "🆓 <b>Бесплатная версия SacredVisuals</b>\n\n"
        "Вы можете скачать актуальную версию клиента по кнопке ниже.\n"
        "<i>Версия: 1.21.4-FREE</i>",
        reply_markup=download_kb,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"👋 <b>Привет!</b> Вы вернулись в главное меню.\nВыберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return 
    await state.clear()
    await message.answer("🛠 <b>Панель администратора</b>", reply_markup=admin_main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats", F.from_user.id == ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
    await callback.message.answer(f"📊 <b>Статистика:</b>\n\nЮзеров в базе: <code>{len(users_db)}</code>\nКлючей: <code>{len(keys_db)}</code>", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "adm_broadcast", F.from_user.id == ADMIN_ID)
async def adm_broadcast_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 <b>Отправьте сообщение для рассылки:</b>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    if not users_db:
        await message.answer("❌ База пуста.")
        return
    count = 0
    await message.answer("⏳ Рассылка запущена...")
    for uid in list(users_db):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Готово! Получили: <b>{count}</b>", parse_mode="HTML")

# --- ПОДДЕРЖКА / ТИКЕТЫ ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("🆘 <b>Чат с поддержкой открыт!</b>\nНапишите сообщение ниже:", parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"🆘 <b>НОВЫЙ ТИКЕТ</b>\n🆔 <code>{callback.from_user.id}</code>\n👤 @{callback.from_user.username}\n<i>[TICKET_ID: {callback.from_user.id}]</i>", parse_mode="HTML")
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    if message.text and message.text.startswith("/"): return
    header = f"📩 <b>Сообщение от юзера</b>\n🆔 <code>{message.from_user.id}</code>\n━━━━━━━━━━━━━━\n"
    footer = f"\n━━━━━━━━━━━━━━\n<i>[TICKET_ID: {message.from_user.id}]</i>"
    await bot.copy_message(ADMIN_ID, message.chat.id, message.message_id, caption=f"{header}{message.caption or ''}{footer}", parse_mode="HTML")

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(uid, message.chat.id, message.message_id)
    except: pass

# --- ПОКУПКА ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 <b>Введите промокод</b> (если есть):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Пропустить", callback_data="skip_promo")]]), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(discount=0)
    await state.set_state(BuyFlow.waiting_for_plan)
    await callback.message.edit_text("🛒 <b>Выберите тарифный план:</b>", reply_markup=plans_kb(0), parse_mode="HTML")

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    discount = promo_db[code]["percent"] if code in promo_db else 0
    await state.update_data(discount=discount)
    await state.set_state(BuyFlow.waiting_for_plan)
    await message.answer(f"✅ Скидка {discount}%" if discount > 0 else "❌ Код не найден", reply_markup=plans_kb(discount), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - data.get("discount", 0) / 100))
    
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(f"🧾 <b>Счёт сформирован</b>\n📦 Тариф: {name}\n💵 К оплате: <b>{final_price}₽</b>\n\nПрикрепите чек оплаты сообщением ниже:", parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"💰 <b>НОВЫЙ ЗАКАЗ</b>\n🆔 {callback.from_user.id}\n📦 {name}\n💵 {final_price}₽\n<i>[TICKET_ID: {callback.from_user.id}]</i>", parse_mode="HTML")
    await callback.answer()

# --- КЛЮЧИ ---

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ <b>Введите лицензионный ключ:</b>", parse_mode="HTML")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        await state.set_state(TicketFlow.in_ticket)
        await message.answer(f"✅ <b>Ключ активирован!</b>\n📦 Тариф: {PLANS[data['plan']]}\n\nНапишите в поддержку для получения инструкций:", parse_mode="HTML")
    else:
        await message.answer("❌ <b>Ключ недействителен!</b>", parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
