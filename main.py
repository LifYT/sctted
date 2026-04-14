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
    sys.exit("❌ ОШИБКА: Переменная BOT_TOKEN не установлена в настройках хостинга!")

ADMIN_ID = 5822741823
CHANNEL_ID = '@sacredvisuals'
CHANNEL_URL = 'https://t.me/sacredvisuals'
# Ссылка на бесплатную версию (замени на свою актуальную ссылку)
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

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Список ключей", callback_data="adm_list_keys")],
        [InlineKeyboardButton(text="❌ Закрыть меню", callback_data="adm_close_menu")]
    ])

# --- START ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    if await is_subscribed(message.from_user.id):
        await message.answer(f"👋 Привет, {message.from_user.first_name}!\n\n✨ Добро пожаловать в SacredVisuals.\nВыберите действие:", reply_markup=main_keyboard())
    else:
        await message.answer("❌ **Доступ ограничен!**\nПодпишитесь на канал:", reply_markup=sub_keyboard(), parse_mode="Markdown")

# --- КНОПКА БЕСПЛАТНОЙ ВЕРСИИ (ИСПРАВЛЕНО) ---

@dp.callback_query(F.data == "free_version")
async def free_version_cmd(callback: types.CallbackQuery):
    await callback.message.answer(
        "🆓 **Бесплатная версия SacredVisuals**\n\n"
        f"Скачать можно по ссылке ниже:\n{FREE_VERSION_URL}",
        parse_mode="Markdown",
        disable_web_page_preview=False
    )
    await callback.answer()

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    stats = (f"🛠 **Админ-панель**\n\n👤 Юзеров: `{len(users_db)}`\n🔑 Ключей: `{len(keys_db)}` \n\nЗакрыть тикет: ответьте на сообщение юзера командой `/close`")
    await message.answer(stats, reply_markup=admin_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_close_menu", F.from_user.id == ADMIN_ID)
async def adm_close_menu(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data == "adm_list_keys", F.from_user.id == ADMIN_ID)
async def adm_keys(callback: types.CallbackQuery):
    text = "🗝 **Список ключей:**\n\n"
    text += "\n".join([f"`{k}` — {PLANS[v['plan']]}" for k, v in keys_db.items()]) or "Ключей нет."
    await callback.message.edit_text(text, reply_markup=admin_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_broadcast", F.from_user.id == ADMIN_ID)
async def adm_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 Отправь текст или фото для рассылки:")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

# --- ТИКЕТЫ И ЗАКРЫТИЕ ---

@dp.message(Command("close"), F.chat.id == ADMIN_ID, F.reply_to_message)
async def close_ticket(message: types.Message):
    try:
        text = message.reply_to_message.text or message.reply_to_message.caption
        if "[TICKET_ID:" not in text:
            return await message.answer("❌ Это не сообщение из тикета")
        
        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
        user_state = FSMContext(storage=dp.storage, key=types.StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
        await user_state.clear()
        
        await bot.send_message(uid, "✅ **Ваше обращение закрыто администратором.**\nТеперь вы можете снова использовать меню.", parse_mode="Markdown", reply_markup=main_keyboard())
        await message.answer(f"✅ Тикет [ID: {uid}] закрыт.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при закрытии: {e}")

# --- КЛИЕНТСКАЯ ЧАСТЬ ---

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена!", reply_markup=main_keyboard())
    else:
        await callback.answer("⚠️ Вы не подписались!", show_alert=True)

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("💬 **Вы открыли поддержку!**\nПишите сообщение — админ ответит здесь.", parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"🆕 <b>Новый тикет</b>\n\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}", parse_mode="HTML")

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 **Введите промокод**:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Нету", callback_data="skip_promo")]]), parse_mode="Markdown")

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
        await message.answer(f"✅ Промокод `{code}` применён!\nВыберите тариф:", reply_markup=plans_kb(discount), parse_mode="Markdown")
        await state.set_state(BuyFlow.waiting_for_plan)
    else:
        await message.answer("❌ Неверный промокод")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    promo, discount = data.get("promo", "Без промокода"), data.get("discount", 0)
    plans = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}
    name, price = plans[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer(f"🧾 **Заявка создана!**\n\n📦 Тариф: *{name}*\n💵 К оплате: *{final_price}₽*\n\n💬 Напишите сообщение — админ ответит здесь:", parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"🆕 <b>Новый заказ</b>\n\n[TICKET_ID: {callback.from_user.id}]\n👤 @{callback.from_user.username}\n📦 Тариф: {name}\n💵 Сумма: {final_price}₽", parse_mode="HTML")

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        plan = keys_db[key]["plan"]
        del keys_db[key]
        await state.set_state(TicketFlow.in_ticket)
        await message.answer(f"✅ **Ключ активирован!**\n📦 Тариф: *{PLANS.get(plan)}*\n\n💬 Напишите сообщение в поддержку:", parse_mode="Markdown")
        await bot.send_message(ADMIN_ID, f"🟢 <b>Ключ активирован</b>\n\n[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}\n📦 {PLANS.get(plan)}", parse_mode="HTML")
    else:
        await message.answer("❌ Неверный ключ")

@dp.message(TicketFlow.in_ticket)
async def ticket_msg(message: types.Message):
    await bot.send_message(ADMIN_ID, f"[TICKET_ID: {message.from_user.id}]\n👤 @{message.from_user.username}")
    await bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    if message.text and message.text.startswith("/"): return 
    try:
        text = message.reply_to_message.text or message.reply_to_message.caption
        if "[TICKET_ID:" not in text: return
        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
    except:
        await message.answer("❌ Ошибка доставки")

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def perform_broadcast(message: types.Message, state: FSMContext):
    count = 0
    await message.answer("⏳ Рассылка...")
    for uid in users_db:
        try:
            if message.photo: await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "")
            else: await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Отправлено: {count}")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
