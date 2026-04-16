import os
import json
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
API_TOKEN = '8311674459:AAG9Ac0Dmwk7HTW1jY7i1srxFawOMG73-Fg'
ADMIN_IDS = {5822741823, 7113659622}  # 👈 Добавляй айди через запятую
CHANNEL_ID = '@sacredvisuals'
CHANNEL_URL = 'https://t.me/sacredvisuals'
FREE_VERSION_URL = "https://www.dropbox.com/scl/fi/fud621oa9imlxniv4vpx6/SacredVisuals-1.21.4-FREE.jar?rlkey=enae4vae8pszr96adcgewzf3c&st=hhgt0vqf&dl=1"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ФАЙЛЫ БАЗ ---
USERS_FILE = "users_db.json"
KEYS_FILE = "keys_db.json"
PROMO_FILE = "promo_db.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- БАЗЫ ---
promo_db = load_json(PROMO_FILE, {"LIF": {"percent": 10, "desc": "Скидка 10%"}})
users_db = set(load_json(USERS_FILE, []))
keys_db = load_json(KEYS_FILE, {})

PLANS = {"week": "Неделя", "month": "Месяц", "life": "Навсегда"}

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
    waiting_for_key_data = State()
    waiting_for_promo_data = State()

# --- ХЕЛПЕР: рассылка всем админам ---
async def notify_admins(text, reply_markup=None, parse_mode="HTML"):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение админу {admin_id}: {e}")

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

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)
    save_json(USERS_FILE, list(users_db))
    await message.answer(f"<b>👋 Привет, {message.from_user.first_name}!</b>\n\n✨ Добро пожаловать в <b>SacredVisuals</b>.", reply_markup=main_keyboard(), parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMIN_IDS:
        await state.clear()
        await message.answer("🛠 <b>Панель администратора</b>", reply_markup=admin_main_kb(), parse_mode="HTML")

# --- АДМИНКА (КЛЮЧИ / ПРОМО) ---
@dp.callback_query(F.data == "adm_addkey", F.from_user.id.in_(ADMIN_IDS))
async def adm_addkey_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите: <code>КЛЮЧ ТАРИФ ОПИСАНИЕ</code>\nДоступные тарифы: week, month, life", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_key_data)
    await callback.answer()

@dp.message(AdminStates.waiting_for_key_data, F.from_user.id.in_(ADMIN_IDS))
async def adm_addkey_step2(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(maxsplit=2)
        keys_db[parts[0]] = {"plan": parts[1], "desc": parts[2]}
        save_json(KEYS_FILE, keys_db)
        await message.answer(f"✅ Ключ <code>{parts[0]}</code> добавлен!", reply_markup=admin_main_kb(), parse_mode="HTML")
        await state.clear()
    except:
        await message.answer("❌ Ошибка. Формат: <code>KEY week MyDesc</code>")

@dp.callback_query(F.data == "adm_addpromo", F.from_user.id.in_(ADMIN_IDS))
async def adm_addpromo_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎟 Введите: <code>ПРОМО ПРОЦЕНТ</code>\nНапример: <code>SUMMER 20</code>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_promo_data)
    await callback.answer()

@dp.message(AdminStates.waiting_for_promo_data, F.from_user.id.in_(ADMIN_IDS))
async def adm_addpromo_step2(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        code = parts[0].upper()
        perc = int(parts[1])
        promo_db[code] = {"percent": perc, "desc": f"Скидка {perc}%"}
        save_json(PROMO_FILE, promo_db)
        await message.answer(f"✅ Промокод <code>{code}</code> на {perc}% добавлен!", reply_markup=admin_main_kb(), parse_mode="HTML")
        await state.clear()
    except:
        await message.answer("❌ Ошибка. Формат: <code>PROMO 15</code>")

@dp.callback_query(F.data == "adm_list", F.from_user.id.in_(ADMIN_IDS))
async def adm_list_keys(callback: types.CallbackQuery):
    if not keys_db:
        await callback.message.answer("📭 Список ключей пуст.", reply_markup=admin_main_kb())
    else:
        lines = ["📜 <b>Список активных ключей:</b>\n"]
        for key, data in keys_db.items():
            plan_name = PLANS.get(data['plan'], data['plan'])
            lines.append(f"🔑 <code>{key}</code> — {plan_name} | {data['desc']}")
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n\n...и ещё больше ключей."
        await callback.message.answer(text, parse_mode="HTML", reply_markup=admin_main_kb())
    await callback.answer()

# --- ТИКЕТЫ (ПОДДЕРЖКА) ---
@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    await callback.message.answer("🆘 <b>Чат открыт!</b> Напишите ваше сообщение прямо сюда:", reply_markup=user_close_ticket_kb(), parse_mode="HTML")

    username = f"@{callback.from_user.username}" if callback.from_user.username else "Скрыт"
    await notify_admins(
        f"📩 <b>НОВЫЙ ТИКЕТ ОТКРЫТ</b>\n👤 Юзер: {username}\n🆔 <code>{callback.from_user.id}</code>\n<i>[TICKET_ID: {callback.from_user.id}]</i>",
        reply_markup=admin_close_ticket_kb(callback.from_user.id)
    )
    await callback.answer()

@dp.message(TicketFlow.in_ticket)
async def ticket_relay(message: types.Message):
    if message.text and message.text.startswith("/"): return

    username = f"@{message.from_user.username}" if message.from_user.username else "Скрыт"
    user_text = message.text or "[Вложение: фото/файл/эмодзи]"

    report_text = (
        f"📨 <b>Сообщение от юзера</b>\n"
        f"👤 Юзер: {username}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📝 <b>Текст:</b> {user_text}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>[TICKET_ID: {message.from_user.id}]</i>"
    )

    for admin_id in ADMIN_IDS:
        try:
            if message.photo or message.document or message.video:
                await bot.copy_message(
                    admin_id,
                    message.chat.id,
                    message.message_id,
                    caption=report_text,
                    parse_mode="HTML",
                    reply_markup=admin_close_ticket_kb(message.from_user.id)
                )
            else:
                await bot.send_message(
                    admin_id,
                    report_text,
                    parse_mode="HTML",
                    reply_markup=admin_close_ticket_kb(message.from_user.id)
                )
        except Exception as e:
            logging.warning(f"Не удалось переслать тикет админу {admin_id}: {e}")

@dp.message(F.chat.id.in_(ADMIN_IDS), F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        uid = int(raw_text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(uid, message.chat.id, message.message_id)
        await message.answer(f"✅ Ответ доставлен пользователю <code>{uid}</code>", reply_markup=admin_close_ticket_kb(uid), parse_mode="HTML")
    except:
        await message.answer("❌ Ошибка: ответьте на сообщение с ID тикета.")

@dp.callback_query(F.data.startswith("adm_close_"))
async def admin_close_handler(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    try:
        user_state = dp.fsm.resolve_context(bot, uid, uid)
        await user_state.clear()
        await bot.send_message(uid, "✅ <b>Администратор закрыл тикет.</b>\nВы вернулись в меню.", reply_markup=main_keyboard(), parse_mode="HTML")
        raw_text = callback.message.text or callback.message.caption or ""
        try:
            username = raw_text.split("Юзер:")[1].split("\n")[0].strip()
        except:
            username = f"ID: {uid}"
        await callback.message.edit_text(f"🚫 Тикет закрыт.\n👤 Юзер: {username}", parse_mode="HTML")
    except:
        await callback.answer("Ошибка закрытия")

@dp.callback_query(F.data == "user_close_ticket")
async def user_close(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("🤝 Тикет закрыт. Вы вернулись в меню.", reply_markup=main_keyboard(), parse_mode="HTML")
    username = f"@{callback.from_user.username}" if callback.from_user.username else f"(без юзернейма, ID: {callback.from_user.id})"
    await notify_admins(f"🚫 Юзер {username} закрыл тикет сам.")
    await callback.answer()

# --- ПОКУПКА ---
@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer("🎟 <b>Введите промокод</b> (или нажмите пропустить):",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                      [InlineKeyboardButton(text="❌ Пропустить", callback_data="skip_promo")]
                                  ]), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(discount=0)
    await state.set_state(BuyFlow.waiting_for_plan)
    await callback.message.edit_text("🛒 <b>Выберите тариф:</b>", reply_markup=plans_kb(0), parse_mode="HTML")
    await callback.answer()

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper()
    discount = promo_db[code]["percent"] if code in promo_db else 0
    await state.update_data(discount=discount)
    await state.set_state(BuyFlow.waiting_for_plan)
    text = f"✅ Промокод на {discount}% применен!" if discount > 0 else "❌ Неверный промокод. Тарифы без скидки:"
    await message.answer(text, reply_markup=plans_kb(discount), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plans_map = {"plan_week": ("Неделя", 69), "plan_month": ("Месяц", 189), "plan_life": ("Навсегда", 369)}

    plan_data = plans_map.get(callback.data)
    if not plan_data:
        return await callback.answer("Ошибка выбора тарифа")

    name, price = plan_data
    discount = data.get("discount", 0)
    final_price = math.ceil(price * (1 - discount / 100))

    await state.set_state(TicketFlow.in_ticket)

    await callback.message.answer(
        f"🧾 К оплате: <b>{final_price}₽</b>\nЖдите подробной инструкции к оплате.",
        reply_markup=user_close_ticket_kb(),
        parse_mode="HTML"
    )

    username = f"@{callback.from_user.username}" if callback.from_user.username else "Скрыт"
    admin_text = (
        f"💰 <b>НОВЫЙ ЗАКАЗ</b>\n"
        f"👤 Юзер: {username}\n"
        f"🆔 <code>{callback.from_user.id}</code>\n"
        f"📦 Тариф: {name}\n"
        f"💵 Цена: {final_price}₽\n"
        f"<i>[TICKET_ID: {callback.from_user.id}]</i>"
    )
    await notify_admins(admin_text, reply_markup=admin_close_ticket_kb(callback.from_user.id))
    await callback.answer()

# --- РАССЫЛКА ---
@dp.callback_query(F.data == "adm_broadcast", F.from_user.id.in_(ADMIN_IDS))
async def adm_broadcast_step1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 Отправьте сообщение для рассылки:")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id.in_(ADMIN_IDS))
async def perform_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    count = 0
    for uid in list(users_db):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Готово! Получили {count} чел.")

@dp.callback_query(F.data == "free_version")
async def free_v(callback: types.CallbackQuery):
    download_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать SacredVisuals (JAR)", url=FREE_VERSION_URL)],
    ])
    instruction_text = (
        "🆓 <b>Бесплатная версия SacredVisuals</b>\n\n"
        "<b>Инструкция по установке:</b>\n"
        "1️⃣ Установите Minecraft <b>Fabric 1.21.4</b>\n"
        "2️⃣ Скачайте мод <a href='https://minecraft-inside.ru/mods/94725-fabric-api.html'>FabricAPI</a>\n"
        "3️⃣ Переместите файлы <code>FabricAPI</code> и <code>SacredVisuals-FREE</code> в папку <code>mods</code>\n\n"
        "✨ <b>Удачного использования!</b>"
    )
    await callback.message.edit_text(
        text=instruction_text,
        reply_markup=download_kb,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "adm_stats", F.from_user.id.in_(ADMIN_IDS))
async def adm_stats(callback: types.CallbackQuery):
    await callback.message.answer(f"📊 Статистика:\nЮзеров: {len(users_db)}\nКлючей: {len(keys_db)}")

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)
    await callback.answer()

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        save_json(KEYS_FILE, keys_db)
        plan_name = PLANS.get(data['plan'], data['plan'])

        await state.set_state(TicketFlow.in_ticket)
        await message.answer(
            f"✅ Ключ на <b>{plan_name}</b> активирован!\n"
            f"📝 {data['desc']}\n\nОжидайте — вам выдадут доступ.",
            reply_markup=user_close_ticket_kb(),
            parse_mode="HTML"
        )

        username = f"@{message.from_user.username}" if message.from_user.username else "Скрыт"
        admin_text = (
            f"🔑 <b>КЛЮЧ АКТИВИРОВАН</b>\n"
            f"👤 Юзер: {username}\n"
            f"🆔 <code>{message.from_user.id}</code>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🗝 Ключ: <code>{key}</code>\n"
            f"📦 Тариф: {plan_name}\n"
            f"📝 Описание: {data['desc']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"<i>[TICKET_ID: {message.from_user.id}]</i>"
        )
        await notify_admins(admin_text, reply_markup=admin_close_ticket_kb(message.from_user.id))
    else:
        await message.answer("❌ Ключ не найден или уже был использован.")
        await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
