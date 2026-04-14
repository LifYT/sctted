import asyncio
import logging
import sys
import math
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ════════════════════════════════════════════
#                   КОНФИГ
# ════════════════════════════════════════════

# BotHost хранит ключи в переменных окружения. Обычно токен бота называется BOT_TOKEN.
# Вторым аргументом идет значение-заглушка для тестирования на домашнем ПК.
API_TOKEN   = os.getenv('BOT_TOKEN', 'ВАШ_ТОКЕН_ДЛЯ_ЛОКАЛЬНОГО_ТЕСТА')

if not API_TOKEN or API_TOKEN == 'ВАШ_ТОКЕН_ДЛЯ_ЛОКАЛЬНОГО_ТЕСТА':
    logging.warning("⚠️ Внимание: Токен не найден в BotHost, используется локальный или пустой токен!")

ADMIN_ID    = 0000000000          # Ваш Telegram ID
CHANNEL_ID  = '@sacredvisuals'
CHANNEL_URL = 'https://t.me/sacredvisuals'

# BotHost автоматически даёт домен и порт через переменные окружения.
# Если переменных нет — подставляются значения по умолчанию для локального теста.
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', 'https://ВАШ_ДОМЕН.bothost.io')
WEBHOOK_PATH = f'/webhook/{API_TOKEN}'
WEBHOOK_URL  = f'{WEBHOOK_HOST}{WEBHOOK_PATH}'
WEB_HOST     = '0.0.0.0'
WEB_PORT     = int(os.getenv('PORT', 8080))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

# ════════════════════════════════════════════
#                    БАЗЫ
# ════════════════════════════════════════════

promo_db: dict[str, dict] = {
    "LIF": {"percent": 10, "desc": "Скидка 10%"}
}
keys_db:  dict[str, dict] = {}
users_db: set[int]        = set()

# user_id → статус тикета  (открыт / закрыт)
tickets_db: dict[int, str] = {}

PLANS = {
    "week":  "Неделя",
    "month": "Месяц",
    "life":  "Навсегда"
}

# ════════════════════════════════════════════
#                   СТЕЙТЫ
# ════════════════════════════════════════════

class BuyFlow(StatesGroup):
    waiting_for_promo = State()
    waiting_for_plan  = State()

class KeyFlow(StatesGroup):
    waiting_for_key = State()

class TicketFlow(StatesGroup):
    in_ticket = State()

class AdminStates(StatesGroup):
    waiting_for_ad          = State()
    # Промокоды
    waiting_promo_code      = State()
    waiting_promo_percent   = State()
    # Ключи
    waiting_key_value       = State()
    waiting_key_plan        = State()
    waiting_key_desc        = State()

# ════════════════════════════════════════════
#              ВСПОМОГАТЕЛЬНЫЕ
# ════════════════════════════════════════════

async def is_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ('member', 'administrator', 'creator')
    except Exception:
        return False

# ─── Клавиатуры пользователя ────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить клиент",      callback_data="buy")],
        [InlineKeyboardButton(text="🆓 Бесплатная версия",  callback_data="free_version")],
        [InlineKeyboardButton(text="🔑 Активировать ключ",  callback_data="activate_key")],
        [InlineKeyboardButton(text="🆘 Поддержка",          callback_data="support")],
    ])

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="🔄 Проверить подписку",   callback_data="check_sub")],
    ])

def plans_kb(discount_percent: int = 0) -> InlineKeyboardMarkup:
    plans = [
        ("plan_week",  "Неделя",   69),
        ("plan_month", "Месяц",   189),
        ("plan_life",  "Навсегда",369),
    ]
    buttons = []
    for cb, name, price in plans:
        final = math.ceil(price * (1 - discount_percent / 100))
        text  = f"{name} — {final}₽"
        if discount_percent:
            text += f" (скидка {discount_percent}%)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ─── Клавиатуры администратора ───────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Промокоды",    callback_data="adm_promos")],
        [InlineKeyboardButton(text="🔑 Ключи",        callback_data="adm_keys")],
        [InlineKeyboardButton(text="🎫 Тикеты",       callback_data="adm_tickets")],
        [InlineKeyboardButton(text="📢 Рассылка",     callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика",   callback_data="adm_stats")],
    ])

def admin_promos_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить промокод", callback_data="adm_promo_add")],
        [InlineKeyboardButton(text="🗑 Удалить промокод",  callback_data="adm_promo_del")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="adm_promo_list")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="adm_back")],
    ])

def admin_keys_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ключ", callback_data="adm_key_add")],
        [InlineKeyboardButton(text="🗑 Удалить ключ",  callback_data="adm_key_del")],
        [InlineKeyboardButton(text="📋 Список ключей", callback_data="adm_key_list")],
        [InlineKeyboardButton(text="◀️ Назад",         callback_data="adm_back")],
    ])

def admin_tickets_kb() -> InlineKeyboardMarkup:
    rows = []
    for uid, status in tickets_db.items():
        icon = "🟢" if status == "open" else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{icon} ID {uid}",
            callback_data=f"adm_ticket_{uid}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def ticket_action_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Закрыть тикет",     callback_data=f"adm_close_{uid}")],
        [InlineKeyboardButton(text="💬 Написать клиенту",   callback_data=f"adm_msg_{uid}")],
        [InlineKeyboardButton(text="◀️ К тикетам",         callback_data="adm_tickets")],
    ])

def plan_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Неделя",   callback_data="kplan_week")],
        [InlineKeyboardButton(text="Месяц",    callback_data="kplan_month")],
        [InlineKeyboardButton(text="Навсегда", callback_data="kplan_life")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_keys")],
    ])

def promo_del_kb() -> InlineKeyboardMarkup:
    rows = []
    for code in promo_db:
        rows.append([InlineKeyboardButton(text=f"🗑 {code}", callback_data=f"dpromo_{code}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_promos")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def key_del_kb() -> InlineKeyboardMarkup:
    rows = []
    for key in keys_db:
        rows.append([InlineKeyboardButton(text=f"🗑 {key}", callback_data=f"dkey_{key}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_keys")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ════════════════════════════════════════════
#               КОМАНДА /start
# ════════════════════════════════════════════

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    users_db.add(message.from_user.id)

    if await is_subscribed(message.from_user.id):
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"✨ Добро пожаловать в SacredVisuals.\n"
            f"Выберите действие:",
            reply_markup=main_keyboard()
        )
    else:
        await message.answer(
            "❌ *Доступ ограничен!*\nПодпишитесь на канал:",
            reply_markup=sub_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена!", reply_markup=main_keyboard())
    else:
        await callback.answer("⚠️ Вы ещё не подписались!", show_alert=True)

# ════════════════════════════════════════════
#             ПОДДЕРЖКА (тикет)
# ════════════════════════════════════════════

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TicketFlow.in_ticket)
    tickets_db[callback.from_user.id] = "open"

    await callback.message.answer(
        "💬 *Вы открыли чат поддержки!*\n\n"
        "Напишите сообщение — администратор ответит здесь.",
        parse_mode="Markdown"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новый тикет</b>\n\n"
        f"[TICKET_ID: {callback.from_user.id}]\n"
        f"👤 @{callback.from_user.username}\n"
        f"🆔 <code>{callback.from_user.id}</code>",
        parse_mode="HTML",
        reply_markup=ticket_action_kb(callback.from_user.id)
    )

# ════════════════════════════════════════════
#                  ПОКУПКА
# ════════════════════════════════════════════

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_for_promo)
    await callback.message.answer(
        "🎟 *Введите промокод* или нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Нет промокода", callback_data="skip_promo")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "skip_promo", BuyFlow.waiting_for_promo)
async def buy_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo="Без промокода", discount=0)
    await callback.message.edit_text(
        "🛒 *Выберите тариф:*",
        reply_markup=plans_kb(0),
        parse_mode="Markdown"
    )
    await state.set_state(BuyFlow.waiting_for_plan)

@dp.message(BuyFlow.waiting_for_promo)
async def buy_promo(message: types.Message, state: FSMContext):
    code = message.text.upper().strip()
    if code in promo_db:
        discount = promo_db[code]["percent"]
        await state.update_data(promo=code, discount=discount)
        await message.answer(
            f"✅ Промокод `{code}` применён!\nВыберите тариф:",
            reply_markup=plans_kb(discount),
            parse_mode="Markdown"
        )
        await state.set_state(BuyFlow.waiting_for_plan)
    else:
        await message.answer("❌ Неверный промокод. Попробуйте ещё раз или нажмите «Нет промокода».")

@dp.callback_query(F.data.startswith("plan_"), BuyFlow.waiting_for_plan)
async def buy_final(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    promo    = data.get("promo", "Без промокода")
    discount = data.get("discount", 0)

    plan_map = {
        "plan_week":  ("Неделя",    69),
        "plan_month": ("Месяц",    189),
        "plan_life":  ("Навсегда", 369),
    }
    name, price = plan_map[callback.data]
    final_price = math.ceil(price * (1 - discount / 100))
    user = callback.from_user

    await state.set_state(TicketFlow.in_ticket)
    tickets_db[user.id] = "open"

    await callback.message.answer(
        f"🧾 *Заявка создана!*\n\n"
        f"📦 Тариф: *{name}*\n"
        f"🎟 Промокод: *{promo}*\n"
        f"💵 К оплате: *{final_price}₽*\n\n"
        f"💬 Напишите сообщение — админ ответит здесь:",
        parse_mode="Markdown"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новый заказ</b>\n\n"
        f"[TICKET_ID: {user.id}]\n"
        f"👤 @{user.username}\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"📦 Тариф: {name}\n"
        f"🎟 Промокод: {promo}\n"
        f"💵 Сумма: {final_price}₽",
        parse_mode="HTML",
        reply_markup=ticket_action_kb(user.id)
    )

# ════════════════════════════════════════════
#                   КЛЮЧИ
# ════════════════════════════════════════════

@dp.callback_query(F.data == "activate_key")
async def key_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите ключ:")
    await state.set_state(KeyFlow.waiting_for_key)

@dp.message(KeyFlow.waiting_for_key)
async def key_check(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key in keys_db:
        data = keys_db.pop(key)
        desc = data["desc"]
        plan = data["plan"]

        await state.set_state(TicketFlow.in_ticket)
        tickets_db[message.from_user.id] = "open"

        await message.answer(
            f"✅ *Ключ успешно активирован!*\n\n"
            f"📦 *Тариф:* *{PLANS.get(plan)}*\n"
            f"🎁 *Вы получили:* *{desc}*\n\n"
            f"💬 Напишите сообщение в поддержку:",
            parse_mode="Markdown"
        )
        await bot.send_message(
            ADMIN_ID,
            f"🟢 <b>Активирован ключ → тикет</b>\n\n"
            f"[TICKET_ID: {message.from_user.id}]\n"
            f"👤 @{message.from_user.username}\n"
            f"🆔 <code>{message.from_user.id}</code>\n"
            f"📦 {PLANS.get(plan)} | {desc}",
            parse_mode="HTML",
            reply_markup=ticket_action_kb(message.from_user.id)
        )
    else:
        await message.answer("❌ Неверный ключ. Попробуйте ещё раз.")

# ════════════════════════════════════════════
#                  ТИКЕТЫ
# ════════════════════════════════════════════

@dp.message(TicketFlow.in_ticket)
async def ticket_user_msg(message: types.Message):
    uid = message.from_user.id
    if tickets_db.get(uid) != "open":
        await message.answer("❌ Ваш тикет закрыт. Нажмите /start чтобы открыть новый.")
        return

    await bot.send_message(
        ADMIN_ID,
        f"[TICKET_ID: {uid}]\n👤 @{message.from_user.username}"
    )
    await bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

# Ответ администратора через reply
@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        text = message.reply_to_message.text or ""
        if "[TICKET_ID:" not in text:
            return
        uid = int(text.split("[TICKET_ID:")[1].split("]")[0])
        await bot.copy_message(
            chat_id=uid,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except Exception:
        await message.answer("❌ Не удалось отправить ответ.")

# ════════════════════════════════════════════
#              БЕСПЛАТНАЯ ВЕРСИЯ
# ════════════════════════════════════════════

@dp.callback_query(F.data == "free_version")
async def free_version(callback: types.CallbackQuery):
    await callback.message.answer(
        "🆓 *Бесплатная версия*\n\n"
        "Опишите здесь что даёт бесплатная версия.\n"
        "Можете добавить кнопку ссылки на скачивание.",
        parse_mode="Markdown"
    )

# ════════════════════════════════════════════
#              АДМИН — ПАНЕЛЬ
# ════════════════════════════════════════════

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🛠 *Панель администратора*\nВыберите раздел:",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )

# ── Навигация ─────────────────────────────

@dp.callback_query(F.data == "adm_back", F.from_user.id == ADMIN_ID)
async def adm_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 *Панель администратора*\nВыберите раздел:",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )

# ── Статистика ─────────────────────────────

@dp.callback_query(F.data == "adm_stats", F.from_user.id == ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
    open_t  = sum(1 for s in tickets_db.values() if s == "open")
    close_t = sum(1 for s in tickets_db.values() if s == "closed")
    await callback.message.edit_text(
        f"📊 *Статистика*\n\n"
        f"👤 Пользователей: *{len(users_db)}*\n"
        f"🎫 Открытых тикетов: *{open_t}*\n"
        f"✅ Закрытых тикетов: *{close_t}*\n"
        f"🎟 Промокодов: *{len(promo_db)}*\n"
        f"🔑 Ключей: *{len(keys_db)}*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
        ]),
        parse_mode="Markdown"
    )

# ════════════════════════════════════════════
#           АДМИН — ПРОМОКОДЫ
# ════════════════════════════════════════════

@dp.callback_query(F.data == "adm_promos", F.from_user.id == ADMIN_ID)
async def adm_promos(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🎟 *Управление промокодами*",
        reply_markup=admin_promos_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_promo_list", F.from_user.id == ADMIN_ID)
async def adm_promo_list(callback: types.CallbackQuery):
    if not promo_db:
        text = "📋 Промокодов нет."
    else:
        lines = [f"• `{k}` — {v['percent']}% | {v['desc']}" for k, v in promo_db.items()]
        text = "📋 *Промокоды:*\n\n" + "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_promos")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_promo_add", F.from_user.id == ADMIN_ID)
async def adm_promo_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_promo_code)
    await callback.message.answer("✏️ Введите код промокода (латиница, например: SALE20):")

@dp.message(AdminStates.waiting_promo_code, F.from_user.id == ADMIN_ID)
async def adm_promo_code(message: types.Message, state: FSMContext):
    await state.update_data(promo_code=message.text.upper().strip())
    await state.set_state(AdminStates.waiting_promo_percent)
    await message.answer("💯 Введите процент скидки (число от 1 до 99):")

@dp.message(AdminStates.waiting_promo_percent, F.from_user.id == ADMIN_ID)
async def adm_promo_percent(message: types.Message, state: FSMContext):
    try:
        percent = int(message.text.strip())
        if not (1 <= percent <= 99):
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 99.")
        return

    data = await state.get_data()
    code = data["promo_code"]
    promo_db[code] = {"percent": percent, "desc": f"Скидка {percent}%"}
    await state.clear()
    await message.answer(
        f"✅ Промокод `{code}` — {percent}% добавлен!",
        reply_markup=admin_promos_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_promo_del", F.from_user.id == ADMIN_ID)
async def adm_promo_del(callback: types.CallbackQuery):
    if not promo_db:
        await callback.answer("Промокодов нет!", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 Выберите промокод для удаления:",
        reply_markup=promo_del_kb()
    )

@dp.callback_query(F.data.startswith("dpromo_"), F.from_user.id == ADMIN_ID)
async def adm_promo_delete(callback: types.CallbackQuery):
    code = callback.data.split("dpromo_", 1)[1]
    if code in promo_db:
        del promo_db[code]
        await callback.answer(f"✅ Промокод {code} удалён.")
    await callback.message.edit_text(
        "🎟 *Управление промокодами*",
        reply_markup=admin_promos_kb(),
        parse_mode="Markdown"
    )

# ════════════════════════════════════════════
#             АДМИН — КЛЮЧИ
# ════════════════════════════════════════════

@dp.callback_query(F.data == "adm_keys", F.from_user.id == ADMIN_ID)
async def adm_keys(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🔑 *Управление ключами*",
        reply_markup=admin_keys_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_key_list", F.from_user.id == ADMIN_ID)
async def adm_key_list(callback: types.CallbackQuery):
    if not keys_db:
        text = "📋 Ключей нет."
    else:
        lines = [f"• `{k}` — {PLANS[v['plan']]} | {v['desc']}" for k, v in keys_db.items()]
        text = "📋 *Ключи:*\n\n" + "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_keys")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_key_add", F.from_user.id == ADMIN_ID)
async def adm_key_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_key_value)
    await callback.message.answer("✏️ Введите значение ключа (например: KEY-XXXX-YYYY):")

@dp.message(AdminStates.waiting_key_value, F.from_user.id == ADMIN_ID)
async def adm_key_value(message: types.Message, state: FSMContext):
    await state.update_data(key_value=message.text.strip())
    await state.set_state(AdminStates.waiting_key_plan)
    await message.answer("📦 Выберите тариф для ключа:", reply_markup=plan_select_kb())

@dp.callback_query(F.data.startswith("kplan_"), F.from_user.id == ADMIN_ID)
async def adm_key_plan(callback: types.CallbackQuery, state: FSMContext):
    plan = callback.data.split("kplan_", 1)[1]
    await state.update_data(key_plan=plan)
    await state.set_state(AdminStates.waiting_key_desc)
    await callback.message.answer(f"✏️ Тариф: *{PLANS[plan]}*\nВведите описание ключа:", parse_mode="Markdown")

@dp.message(AdminStates.waiting_key_desc, F.from_user.id == ADMIN_ID)
async def adm_key_desc(message: types.Message, state: FSMContext):
    data  = await state.get_data()
    key   = data["key_value"]
    plan  = data["key_plan"]
    desc  = message.text.strip()
    keys_db[key] = {"desc": desc, "plan": plan}
    await state.clear()
    await message.answer(
        f"✅ Ключ `{key}` ({PLANS[plan]}) добавлен!",
        reply_markup=admin_keys_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_key_del", F.from_user.id == ADMIN_ID)
async def adm_key_del(callback: types.CallbackQuery):
    if not keys_db:
        await callback.answer("Ключей нет!", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 Выберите ключ для удаления:",
        reply_markup=key_del_kb()
    )

@dp.callback_query(F.data.startswith("dkey_"), F.from_user.id == ADMIN_ID)
async def adm_key_delete(callback: types.CallbackQuery):
    key = callback.data.split("dkey_", 1)[1]
    if key in keys_db:
        del keys_db[key]
        await callback.answer(f"✅ Ключ {key} удалён.")
    await callback.message.edit_text(
        "🔑 *Управление ключами*",
        reply_markup=admin_keys_kb(),
        parse_mode="Markdown"
    )

# ════════════════════════════════════════════
#            АДМИН — ТИКЕТЫ
# ════════════════════════════════════════════

@dp.callback_query(F.data == "adm_tickets", F.from_user.id == ADMIN_ID)
async def adm_tickets(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if not tickets_db:
        await callback.message.edit_text(
            "🎫 Тикетов нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
            ])
        )
        return
    await callback.message.edit_text(
        "🎫 *Тикеты:*\n🟢 — открыт  |  🔴 — закрыт",
        reply_markup=admin_tickets_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("adm_ticket_"), F.from_user.id == ADMIN_ID)
async def adm_ticket_view(callback: types.CallbackQuery):
    uid    = int(callback.data.split("adm_ticket_")[1])
    status = tickets_db.get(uid, "unknown")
    icon   = "🟢 Открыт" if status == "open" else "🔴 Закрыт"
    await callback.message.edit_text(
        f"🎫 *Тикет пользователя*\n\n"
        f"🆔 `{uid}`\n"
        f"Статус: {icon}",
        reply_markup=ticket_action_kb(uid),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("adm_close_"), F.from_user.id == ADMIN_ID)
async def adm_close_ticket(callback: types.CallbackQuery):
    uid = int(callback.data.split("adm_close_")[1])
    tickets_db[uid] = "closed"
    try:
        await bot.send_message(
            uid,
            "✅ Ваш тикет был закрыт администратором.\n"
            "Нажмите /start чтобы вернуться в меню."
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f"✅ Тикет {uid} закрыт.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К тикетам", callback_data="adm_tickets")]
        ])
    )

# ════════════════════════════════════════════
#            АДМИН — РАССЫЛКА
# ════════════════════════════════════════════

@dp.callback_query(F.data == "adm_broadcast", F.from_user.id == ADMIN_ID)
async def adm_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.message.answer(
        "📢 Отправьте сообщение для рассылки.\n"
        "Поддерживаются текст и фото с подписью."
    )

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def adm_broadcast_send(message: types.Message, state: FSMContext):
    await message.answer("⏳ Рассылка запущена...")
    count = 0
    for uid in list(users_db):
        try:
            if message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "")
            else:
                await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    await message.answer(
        f"✅ Рассылка завершена!\nОтправлено: *{count}* из *{len(users_db)}*",
        parse_mode="Markdown"
    )
    await state.clear()

# ════════════════════════════════════════════
#        СТАРЫЕ ТЕКСТОВЫЕ КОМАНДЫ (БОНУС)
# ════════════════════════════════════════════

@dp.message(Command("addpromo"), F.from_user.id == ADMIN_ID)
async def cmd_addpromo(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) == 3:
        code    = parts[1].upper()
        percent = int(parts[2])
        promo_db[code] = {"percent": percent, "desc": f"Скидка {percent}%"}
        await message.answer(f"✅ Промокод `{code}` ({percent}%) добавлен.", parse_mode="Markdown")
    else:
        await message.answer("Формат: /addpromo КОД ПРОЦЕНТ")

@dp.message(Command("delpromo"), F.from_user.id == ADMIN_ID)
async def cmd_delpromo(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        code = parts[1].upper()
        if code in promo_db:
            del promo_db[code]
            await message.answer(f"✅ Промокод `{code}` удалён.", parse_mode="Markdown")
        else:
            await message.answer("❌ Промокод не найден.")
    else:
        await message.answer("Формат: /delpromo КОД")

@dp.message(Command("addkey"), F.from_user.id == ADMIN_ID)
async def cmd_addkey(message: types.Message):
    parts = message.text.split(maxsplit=3)
    if len(parts) == 4:
        key, plan, desc = parts[1], parts[2], parts[3]
        if plan not in PLANS:
            await message.answer("❌ Тариф: week / month / life")
            return
        keys_db[key] = {"desc": desc, "plan": plan}
        await message.answer(f"✅ Ключ `{key}` добавлен.", parse_mode="Markdown")
    else:
        await message.answer("Формат: /addkey КЛЮЧ ТАРИФ ОПИСАНИЕ")

@dp.message(Command("list"), F.from_user.id == ADMIN_ID)
async def cmd_list(message: types.Message):
    keys_text  = "\n".join(f"• `{k}` — {PLANS[v['plan']]} | {v['desc']}" for k, v in keys_db.items()) or "Пусто"
    promo_text = "\n".join(f"• `{k}` — {v['percent']}%" for k, v in promo_db.items()) or "Пусто"
    await message.answer(
        f"🔑 *Ключи:*\n{keys_text}\n\n🎟 *Промокоды:*\n{promo_text}",
        parse_mode="Markdown"
    )

@dp.message(Command("help"), F.from_user.id == ADMIN_ID)
async def cmd_help(message: types.Message):
    await message.answer(
        "🛠 *Команды администратора:*\n\n"
        "/admin — открыть панель управления\n"
        "/addpromo КОД ПРОЦЕНТ\n"
        "/delpromo КОД\n"
        "/addkey КЛЮЧ ТАРИФ ОПИСАНИЕ\n"
        "/list — список ключей и промокодов\n\n"
        "Или используйте /admin для удобного управления через кнопки.",
        parse_mode="Markdown"
    )

# ════════════════════════════════════════════
#                   ЗАПУСК
# ════════════════════════════════════════════

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    logging.info("Webhook удалён.")

def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host=WEB_HOST, port=WEB_PORT)

if __name__ == "__main__":
    main()
