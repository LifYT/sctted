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

def admin_close_ticket_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть обращение", callback_data=f"adm_close_{user_id}")]
    ])

def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Список ключей", callback_data="adm_list_keys")],
        [InlineKeyboardButton(text="❌ Закрыть меню", callback_data="adm_close_menu")]
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

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    await message.answer(f"👋 Привет, {message.from_user.first_name}!", reply_markup=main_keyboard())

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    await message.answer(f"🛠 **Админ-панель**\nЮзеров в базе: {len(users_db)}", reply_markup=admin_main_kb(), parse_mode="Markdown")

@dp.message(Command("addkey"), F.from_user.id == ADMIN_ID)
async def add_key(message: types.Message):
    try:
        parts = message.text.split(maxsplit=3)
        key, plan, desc = parts[1], parts[2], parts[3]
        keys_db[key] = {"plan": plan, "desc": desc}
        await message.answer(f"✅ Ключ `{key}` на {plan} добавлен.")
    except:
        await message.answer("Формат: `/addkey КЛЮЧ week/month/life Описание`", parse_mode="Markdown")

@dp.message(Command("list"), F.from_user.id == ADMIN_ID)
async def list_keys_cmd(message: types.Message):
    text = "\n".join([f"`{k}` — {PLANS.get(v['plan'])} ({v['desc']})" for k, v in keys_db.items()]) or "Ключей нет."
    await message.answer(f"🔑 **Список ключей:**\n{text}", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_list_keys")
async def adm_list_keys_cb(c: types.CallbackQuery):
    text = "\n".join([f"`{k}` — {PLANS.get(v['plan'])} ({v['desc']})" for k, v in keys_db.items()]) or "Ключей нет."
    await c.message.answer(f"🔑 **Ключи:**\n{text}", parse_mode="Markdown")
    await c.answer()

# --- РАССЫЛКА ---

@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Отправьте сообщение для рассылки (текст, фото или пост):")
    await state.set_state(AdminStates.waiting_for_ad)
    await c.answer()

@dp.message(Command("ad"), F.from_user.id == ADMIN_ID)
async def cmd_ad(message: types.Message, state: FSMContext):
    await message.answer("📢 Отправьте сообщение для рассылки:")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_broadcast(message: types.Message, state: FSMContext):
    count = 0
    for uid in users_db:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            count += 1
        except: continue
    await message.answer(f"✅ Рассылка завершена! Получили: {count} чел.")
    await state.clear()

# --- ПОКУПКА И ТИКЕТЫ ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]])
    await callback.message.answer("🎟 **Введите промокод:**", reply_markup=kb, parse_mode="Markdown")
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
    discount = promo_db[code]["percent"] if code in promo_db else 0
    await state.update_data(promo=code if discount > 0 else "Нет", discount=discount)
    await state.set_state(BuyFlow.waiting_for_plan)
    msg = f"✅ Промокод `{code}` применён!" if discount > 0 else "❌ Код не найден, тарифы без скидки:"
    await message.answer(msg, reply_markup=plans_kb(discount), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    discount, promo = data.get("discount", 0), data.get("promo", "Нет")
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))

    await bot.send_message(ADMIN_ID, f"💰 **НОВЫЙ ЗАКАЗ**\n[TICKET_ID: {callback.from_user.id}]\n👤 Юзер: @{callback.from_user.username}\n📦 Тариф: {name}\n💵 К оплате: {final_price}₽\n🎟 Промо: {promo}", reply_markup=admin_close_ticket_kb(callback.from_user.id))
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(f"🧾 **Заявка принята!**\nСумма: {final_price}₽\n\n💬 Напишите админу или скиньте чек:", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 **Чат открыт.**", reply_markup=user_close_ticket_kb(), parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"🆘 **НОВЫЙ ТИКЕТ**\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}", reply_markup=admin_close_ticket_kb(callback.from_user.id))
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    if message.text == "/close": return
    caption = f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}\n\n💬 Сообщение:"
    if message.text:
        await bot.send_message(ADMIN_ID, f"{caption}\n{message.text}", reply_markup=admin_close_ticket_kb(message.from_user.id))
    else:
        await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id, caption=caption, reply_markup=admin_close_ticket_kb(message.from_user.id))

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text == "/close": return
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# --- ЗАКРЫТИЕ ---

@dp.callback_query(F.data.startswith("adm_close_"))
async def admin_close_btn(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    user_key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
    await dp.storage.set_state(user_key, None)
    await bot.send_message(uid, "✅ **Ваш тикет был закрыт администратором.**", reply_markup=main_keyboard())
    await callback.message.edit_text(callback.message.text + "\n\n✅ **ЗАКРЫТО**")
    await callback.answer("Закрыто")

@dp.callback_query(F.data == "user_close_ticket")
async def user_close_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤝 Обращение завершено.", reply_markup=main_keyboard())
    await bot.send_message(ADMIN_ID, f"🚫 **Тикет закрыт пользователем**\n[TICKET_ID: {callback.from_user.id}]")
    await callback.answer()

@dp.message(Command("close"))
async def close_ticket_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID and message.reply_to_message:
        try:
            raw_text = message.reply_to_message.text or message.reply_to_message.caption
            uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
            user_key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
            await dp.storage.set_state(user_key, None)
            await bot.send_message(uid, "✅ **Ваш тикет закрыт админом.**", reply_markup=main_keyboard())
            await message.answer(f"✅ Тикет {uid} закрыт.")
        except: pass
    else:
        await state.clear()
        await message.answer("🤝 Обращение завершено.", reply_markup=main_keyboard())

# --- ПРОЧЕЕ ---

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
        await message.answer(f"✅ Ключ активирован ({PLANS.get(data['plan'])}).", reply_markup=user_close_ticket_kb())
        await bot.send_message(ADMIN_ID, f"🟢 **КЛЮЧ АКТИВИРОВАН**\n[TICKET_ID: {message.from_user.id}]\n🔑 {key}", reply_markup=admin_close_ticket_kb(message.from_user.id))
    else:
        await message.answer("❌ Неверный ключ.")

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer("🆓 **Бесплатная версия**", reply_markup=download_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "adm_close_menu")
async def adm_close_menu_cb(c: types.CallbackQuery):
    await c.message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
