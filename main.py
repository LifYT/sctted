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

# --- АДМИН КОМАНДЫ (ПРОМО И КЛЮЧИ) ---

@dp.message(Command("addpromo"), F.from_user.id == ADMIN_ID)
async def add_promo(message: types.Message):
    try:
        parts = message.text.split()
        code, percent = parts[1].upper(), int(parts[2])
        promo_db[code] = {"percent": percent, "desc": f"Скидка {percent}%"}
        await message.answer(f"✅ Промокод <b>{code}</b> на <b>{percent}%</b> добавлен!", parse_mode="HTML")
    except:
        await message.answer("❌ Формат: `/addpromo КОД ПРОЦЕНТ`", parse_mode="Markdown")

@dp.message(Command("delpromo"), F.from_user.id == ADMIN_ID)
async def del_promo(message: types.Message):
    try:
        code = message.text.split()[1].upper()
        if code in promo_db:
            del promo_db[code]
            await message.answer(f"✅ Промокод <b>{code}</b> удален.", parse_mode="HTML")
        else:
            await message.answer("❌ Промокод не найден.")
    except:
        await message.answer("❌ Формат: `/delpromo КОД`", parse_mode="Markdown")

@dp.message(Command("addkey"), F.from_user.id == ADMIN_ID)
async def add_key(message: types.Message):
    try:
        parts = message.text.split(maxsplit=3)
        key, plan, desc = parts[1], parts[2], parts[3]
        if plan not in PLANS:
            return await message.answer("❌ Тариф должен быть: week, month или life")
        keys_db[key] = {"plan": plan, "desc": desc}
        await message.answer(f"🔑 Ключ <code>{key}</code> на тариф <b>{PLANS[plan]}</b> добавлен!", parse_mode="HTML")
    except:
        await message.answer("❌ Формат: `/addkey КЛЮЧ week/month/life Описание`", parse_mode="Markdown")

@dp.message(Command("list"), F.from_user.id == ADMIN_ID)
async def list_keys_cmd(message: types.Message):
    text = "🔑 <b>Активные ключи:</b>\n\n"
    if not keys_db:
        text += "<i>Список пуст</i>"
    else:
        for k, v in keys_db.items():
            text += f"• <code>{k}</code> — {PLANS.get(v['plan'])} ({v['desc']})\n"
    await message.answer(text, parse_mode="HTML")

# --- ПОКУПКА ---

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ У меня нет промокода", callback_data="skip_promo")]])
    await callback.message.answer("🎟 <b>Введите ваш промокод:</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Нет", discount=0)
    await state.set_state(BuyFlow.waiting_for_plan)
    await callback.message.edit_text("🛒 <b>Выберите подходящий тариф:</b>", reply_markup=plans_kb(0), parse_mode="HTML")
    await callback.answer()

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    discount = promo_db[code]["percent"] if code in promo_db else 0
    await state.update_data(promo=code if discount > 0 else "Нет", discount=discount)
    await state.set_state(BuyFlow.waiting_for_plan)
    msg = f"✅ Промокод <b>{code}</b> активирован!" if discount > 0 else "❌ Промокод не найден. Тарифы без скидки:"
    await message.answer(msg, reply_markup=plans_kb(discount), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    discount, promo = data.get("discount", 0), data.get("promo", "Нет")
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans_map[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))

    # Уведомление админу
    await bot.send_message(
        ADMIN_ID, 
        f"💰 <b>НОВЫЙ ЗАКАЗ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>Юзер:</b> @{callback.from_user.username}\n"
        f"🆔 <b>ID:</b> <code>{callback.from_user.id}</code>\n"
        f"📦 <b>Тариф:</b> {name}\n"
        f"🎟 <b>Промо:</b> {promo}\n"
        f"💵 <b>К оплате:</b> {final_price}₽\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>[TICKET_ID: {callback.from_user.id}]</i>",
        reply_markup=admin_close_ticket_kb(callback.from_user.id),
        parse_mode="HTML"
    )

    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(
        f"🧾 <b>Заявка создана!</b>\nСумма к оплате: <b>{final_price}₽</b>\n\n"
        f"💬 Напишите администратору здесь или отправьте скриншот чека:", 
        reply_markup=user_close_ticket_kb(), 
        parse_mode="HTML"
    )
    await callback.answer()

# --- СИСТЕМА ТИКЕТОВ (RELAY) ---

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(
        "🆘 <b>Чат с поддержкой открыт!</b>\nНапишите ваше сообщение, и админ скоро ответит.", 
        reply_markup=user_close_ticket_kb(), 
        parse_mode="HTML"
    )
    await bot.send_message(
        ADMIN_ID, 
        f"🆘 <b>НОВЫЙ ТИКЕТ</b>\n"
        f"👤 <b>От:</b> @{callback.from_user.username}\n"
        f"🆔 <b>ID:</b> <code>{callback.from_user.id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>[TICKET_ID: {callback.from_user.id}]</i>",
        reply_markup=admin_close_ticket_kb(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    if message.text == "/close": return
    
    # Формируем единое сообщение для админа
    header = (
        f"📩 <b>Сообщение от юзера</b>\n"
        f"👤 @{message.from_user.username} | 🆔 <code>{message.from_user.id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
    )
    footer = f"\n━━━━━━━━━━━━━━\n<i>[TICKET_ID: {message.from_user.id}]</i>"
    
    if message.text:
        await bot.send_message(
            ADMIN_ID, 
            f"{header}{message.text}{footer}", 
            reply_markup=admin_close_ticket_kb(message.from_user.id),
            parse_mode="HTML"
        )
    else:
        # Для фото/файлов
        await bot.copy_message(
            chat_id=ADMIN_ID, 
            from_chat_id=message.chat.id, 
            message_id=message.message_id, 
            caption=f"{header}{message.caption or 'Файл'}{footer}",
            reply_markup=admin_close_ticket_kb(message.from_user.id),
            parse_mode="HTML"
        )

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text == "/close": return
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except:
        await message.answer("❌ Не удалось определить ID пользователя для ответа.")

# --- ЛОГИКА ЗАКРЫТИЯ ---

@dp.callback_query(F.data.startswith("adm_close_"))
async def admin_close_btn(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    user_key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
    await dp.storage.set_state(user_key, None)
    
    await bot.send_message(uid, "✅ <b>Ваш тикет был закрыт администратором.</b>", reply_markup=main_keyboard(), parse_mode="HTML")
    # Обновляем сообщение у админа, чтобы было видно, что закрыто
    new_text = callback.message.text + "\n\n🛑 <b>ТИКЕТ ЗАКРЫТ</b>"
    await callback.message.edit_text(new_text, parse_mode="HTML")
    await callback.answer("Тикет закрыт")

@dp.callback_query(F.data == "user_close_ticket")
async def user_close_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤝 <b>Обращение завершено.</b> Нажмите /start для главного меню.", parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"🚫 <b>Юзер закрыл тикет</b>\n[TICKET_ID: {callback.from_user.id}]", parse_mode="HTML")
    await callback.answer()

# --- РАССЫЛКА И ПРОЧЕЕ ---

@dp.message(Command("ad"), F.from_user.id == ADMIN_ID)
async def start_ad(message: types.Message, state: FSMContext):
    await message.answer("📢 <b>Отправьте сообщение для рассылки:</b>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_ad(message: types.Message, state: FSMContext):
    count = 0
    await message.answer("⏳ Рассылка запущена...")
    for uid in users_db:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Рассылка завершена! Получили: <b>{count}</b> чел.", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ <b>Введите ваш лицензионный ключ:</b>", parse_mode="HTML")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        await state.set_state(TicketFlow.in_ticket)
        await message.answer(
            f"✅ <b>Ключ активирован!</b>\nВаш тариф: <b>{PLANS.get(data['plan'])}</b>\n\n💬 Чат с поддержкой открыт:", 
            reply_markup=user_close_ticket_kb(), 
            parse_mode="HTML"
        )
        await bot.send_message(ADMIN_ID, f"🟢 <b>КЛЮЧ АКТИВИРОВАН</b>\nЮзер: @{message.from_user.username}\nКлюч: <code>{key}</code>\n[TICKET_ID: {message.from_user.id}]", parse_mode="HTML")
    else:
        await message.answer("❌ <b>Неверный ключ или он уже активирован.</b>", parse_mode="HTML")

@dp.callback_query(F.data == "free_version")
async def free_version_handler(callback: types.CallbackQuery):
    await callback.message.answer(
        "🆓 <b>Бесплатная версия SacredVisuals</b>\nНажмите кнопку ниже для скачивания:", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Скачать", url=FREE_VERSION_URL)]]), 
        parse_mode="HTML"
    )
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
