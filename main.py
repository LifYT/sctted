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
    waiting_for_promo_data = State()

# --- КЛАВИАТУРЫ ---

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить клиент", callback_data="buy")],
        [InlineKeyboardButton(text="🆓 Бесплатная версия", callback_data="free_version")],
        [InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ])

def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Добавить ключ", callback_data="adm_addkey")],
        [InlineKeyboardButton(text="🎟 Добавить промо", callback_data="adm_addpromo")],
        [InlineKeyboardButton(text="📜 Список ключей", callback_data="adm_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")]
    ])

def user_close_ticket_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть обращение", callback_data="user_close_ticket")]
    ])

def admin_close_ticket_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть тикет юзера", callback_data=f"adm_close_{user_id}")]
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

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    await message.answer(
        f"<b>👋 Привет, {message.from_user.first_name}!</b>\n\n✨ Добро пожаловать в <b>SacredVisuals</b>.\nВыберите нужное действие ниже:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# --- АДМИН ПАНЕЛЬ (/admin) ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 <b>Панель администратора</b>\nВыберите действие:", reply_markup=admin_main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats", F.from_user.id == ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
    await callback.message.answer(f"📊 <b>Статистика:</b>\n\nЮзеров в базе: <code>{len(users_db)}</code>\nАктивных ключей: <code>{len(keys_db)}</code>", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "adm_list", F.from_user.id == ADMIN_ID)
async def adm_list_keys(callback: types.CallbackQuery):
    text = "🔑 <b>Активные ключи:</b>\n\n"
    if not keys_db:
        text += "<i>Список пуст</i>"
    else:
        for k, v in keys_db.items():
            text += f"• <code>{k}</code> — {PLANS.get(v['plan'])} ({v['desc']})\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "adm_addkey", F.from_user.id == ADMIN_ID)
async def adm_addkey_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите данные ключа в формате:\n<code>КЛЮЧ ТАРИФ ОПИСАНИЕ</code>\n\nТарифы: week, month, life", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_key_data)
    await callback.answer()

@dp.message(AdminStates.waiting_for_key_data, F.from_user.id == ADMIN_ID)
async def adm_addkey_step2(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(maxsplit=2)
        key, plan, desc = parts[0], parts[1], parts[2]
        if plan not in PLANS:
            return await message.answer("❌ Ошибка в тарифе. Используйте: week, month или life")
        keys_db[key] = {"plan": plan, "desc": desc}
        await message.answer(f"✅ Ключ <code>{key}</code> успешно добавлен!", parse_mode="HTML", reply_markup=admin_main_kb())
        await state.clear()
    except:
        await message.answer("❌ Ошибка формата! Пример: <code>GOLD-123 week Для теста</code>")

@dp.callback_query(F.data == "adm_addpromo", F.from_user.id == ADMIN_ID)
async def adm_addpromo_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎟 Введите промокод в формате:\n<code>КОД ПРОЦЕНТ</code>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_promo_data)
    await callback.answer()

@dp.message(AdminStates.waiting_for_promo_data, F.from_user.id == ADMIN_ID)
async def adm_addpromo_step2(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        code, percent = parts[0].upper(), int(parts[1])
        promo_db[code] = {"percent": percent, "desc": f"Скидка {percent}%"}
        await message.answer(f"✅ Промокод <b>{code}</b> на {percent}% добавлен!", parse_mode="HTML", reply_markup=admin_main_kb())
        await state.clear()
    except:
        await message.answer("❌ Ошибка формата! Пример: <code>SALE50 50</code>")

@dp.callback_query(F.data == "adm_broadcast", F.from_user.id == ADMIN_ID)
async def adm_broadcast_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 <b>Отправьте сообщение для рассылки:</b>\n(Текст, фото или файл)", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

# --- ЛОГИКА ТИКЕТОВ И РАССЫЛКИ ---

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_broadcast(message: types.Message, state: FSMContext):
    count = 0
    await message.answer("⏳ Рассылка запущена...")
    for uid in list(users_db):
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Рассылка завершена! Получили: <b>{count}</b> чел.", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("🆘 <b>Чат с поддержкой открыт!</b>\nНапишите ваше сообщение:", reply_markup=user_close_ticket_kb(), parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"🆘 <b>НОВЫЙ ТИКЕТ</b>\n👤 @{callback.from_user.username}\n🆔 <code>{callback.from_user.id}</code>\n<i>[TICKET_ID: {callback.from_user.id}]</i>", reply_markup=admin_close_ticket_kb(callback.from_user.id), parse_mode="HTML")
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    header = f"📩 <b>Сообщение от юзера</b>\n👤 @{message.from_user.username} | 🆔 <code>{message.from_user.id}</code>\n━━━━━━━━━━━━━━\n"
    footer = f"\n━━━━━━━━━━━━━━\n<i>[TICKET_ID: {message.from_user.id}]</i>"
    await bot.copy_message(ADMIN_ID, message.chat.id, message.message_id, caption=f"{header}{message.caption or ''}{footer}", parse_mode="HTML")

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(uid, message.chat.id, message.message_id)
    except:
        await message.answer("❌ Ошибка: ответьте на сообщение с TICKET_ID.")

@dp.callback_query(F.data.startswith("adm_close_"))
async def admin_close_btn(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    await dp.storage.set_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid), None)
    await bot.send_message(uid, "✅ <b>Тикет закрыт администратором.</b>", reply_markup=main_keyboard(), parse_mode="HTML")
    await callback.message.edit_text(callback.message.text + "\n\n🛑 <b>ЗАКРЫТО</b>", parse_mode="HTML")
    await callback.answer("Закрыто")

# --- ЛОГИКА КЛИЕНТА ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 <b>Введите промокод:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Пропустить", callback_data="skip_promo")]]), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Нет", discount=0)
    await state.set_state(BuyFlow.waiting_for_plan)
    await callback.message.edit_text("🛒 <b>Выберите тариф:</b>", reply_markup=plans_kb(0), parse_mode="HTML")

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    discount = promo_db[code]["percent"] if code in promo_db else 0
    await state.update_data(promo=code if discount > 0 else "Нет", discount=discount)
    await state.set_state(BuyFlow.waiting_for_plan)
    await message.answer(f"✅ Скидка {discount}%" if discount > 0 else "❌ Без скидки", reply_markup=plans_kb(discount), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - data.get("discount", 0) / 100))
    await bot.send_message(ADMIN_ID, f"💰 <b>ЗАКАЗ</b>\n👤 @{callback.from_user.username}\n📦 {name}\n💵 {final_price}₽\n<i>[TICKET_ID: {callback.from_user.id}]</i>", parse_mode="HTML")
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(f"🧾 К оплате: <b>{final_price}₽</b>\nОтправьте чек сюда:", reply_markup=user_close_ticket_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ <b>Введите ключ:</b>", parse_mode="HTML")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        await state.set_state(TicketFlow.in_ticket)
        await message.answer(f"✅ Ключ на <b>{PLANS[data['plan']]}</b> активен!", reply_markup=user_close_ticket_kb(), parse_mode="HTML")
        await bot.send_message(ADMIN_ID, f"🟢 Активирован ключ: <code>{key}</code>\nЮзер: @{message.from_user.username} [TICKET_ID: {message.from_user.id}]", parse_mode="HTML")
    else:
        await message.answer("❌ Неверный ключ.")

@dp.callback_query(F.data == "free_version")
async def free_v(callback: types.CallbackQuery):
    await callback.message.answer("📥 <a href='" + FREE_VERSION_URL + "'>Скачать бесплатную версию</a>", parse_mode="HTML")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
