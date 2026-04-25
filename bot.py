"""
Togetherty Bot — @togetherty_bot
================================
Команды:
  /start   — главное меню
  /status  — статус анкеты и ужина
  /edit    — изменить анкету
  /cancel  — отменить текущее действие
  /admin   — панель администратора (только для ADMIN_ID)
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Конфигурация ──────────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))        # твой Telegram ID
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://togetherty.ru/miniapp.html")
CHANNEL    = "https://t.me/togetherty"
SUPPORT    = "@VF746"

# ─── Состояния разговора (ConversationHandler) ─────────────────────────────────
(
    Q_NAME, Q_AGE, Q_CITY, Q_JOB, Q_GOAL,
    Q_TEMP, Q_INTERESTS, Q_BOOK, Q_PROUD,
    Q_CHANGE, Q_PLACE, Q_TABLE, Q_FOOD,
    Q_TG, Q_ABOUT,
) = range(15)

# ─── In-memory база данных ─────────────────────────────────────────────────────
# Структура: { user_id: { profile: {...}, status: str, dinner_date: str, ... } }
DB: dict = {}

def db_get(uid: int) -> dict:
    return DB.get(uid, {})

def db_set(uid: int, **kwargs):
    if uid not in DB:
        DB[uid] = {}
    DB[uid].update(kwargs)

def db_update_profile(uid: int, key: str, value):
    if uid not in DB:
        DB[uid] = {}
    if "profile" not in DB[uid]:
        DB[uid]["profile"] = {}
    DB[uid]["profile"][key] = value

# ─── Вспомогательные функции ───────────────────────────────────────────────────
def next_wednesday() -> datetime:
    """Возвращает дату ближайшей среды в 19:30."""
    now = datetime.now()
    days_ahead = (2 - now.weekday() + 7) % 7 or 7
    return (now + timedelta(days=days_ahead)).replace(
        hour=19, minute=30, second=0, microsecond=0
    )

def format_wed(dt: datetime) -> str:
    months = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    return f"{dt.day} {months[dt.month]} в {dt.strftime('%H:%M')}"

def status_text(status: str) -> str:
    return {
        "pending":    "⏳ Анкета на проверке (1–2 часа)",
        "approved":   "✅ Одобрен — можешь записаться на ужин",
        "rejected":   f"❌ Анкета отклонена. Напиши {SUPPORT}",
        "registered": "🍽 Записан на ужин",
    }.get(status, "—")


# ═══════════════════════════════════════════════════════════════════════════════
# /start — главное меню
# ═══════════════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name
    user = db_get(uid)
    status = user.get("status", "")

    # Блок статуса (если анкета уже есть)
    status_block = ""
    extra_buttons = []

    if status == "pending":
        status_block = "\n\n⏳ *Анкета на проверке.* Ожидай — пришлём ответ."
    elif status == "approved":
        status_block = "\n\n✅ *Анкета одобрена!* Записаться на ужин?"
        extra_buttons.append([InlineKeyboardButton("🍽 Записаться на ужин", callback_data="register")])
    elif status == "registered":
        wed = user.get("dinner_date", format_wed(next_wednesday()))
        status_block = f"\n\n🍽 *Ты записан* на ужин {wed}"
    elif status == "rejected":
        status_block = f"\n\n❌ *Анкета отклонена.* Напиши {SUPPORT}"

    keyboard = [
        [InlineKeyboardButton("🚀 Мини-апп", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("📋 Заполнить анкету в чате", callback_data="fill_chat")],
        *extra_buttons,
        [
            InlineKeyboardButton("📊 Мой статус", callback_data="my_status"),
            InlineKeyboardButton("❓ FAQ",          callback_data="faq"),
        ],
        [InlineKeyboardButton("📣 Наш канал", url=CHANNEL)],
    ]

    text = (
        f"👋 Привет, *{name}*!\n\n"
        f"Я бот *Togetherty* — ужины с незнакомцами в Рязани.\n\n"
        f"🎁 *Первая встреча — бесплатно*\n"
        f"📅 Каждую среду в 19:30\n"
        f"👥 6 человек, подобранных по интересам"
        f"{status_block}"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FAQ
# ═══════════════════════════════════════════════════════════════════════════════
async def cb_faq(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "❓ *Частые вопросы*\n\n"
        "🎁 *Первый ужин правда бесплатный?*\n"
        "Да. Приходи, убедись сам. Следующие — 499 ₽.\n\n"
        "👥 *Кто будет за столом?*\n"
        "6 человек, подобранных алгоритмом по интересам, возрасту и темпераменту.\n\n"
        "📍 *Где проходят ужины?*\n"
        "В уютных ресторанах Рязани. Адрес пришлём за 24 часа до встречи.\n\n"
        "📅 *Когда?*\n"
        "Каждую среду в 19:30.\n\n"
        "🛡 *Как проходит проверка?*\n"
        "Модератор смотрит анкету и одобряет. Обычно 1–2 часа.\n\n"
        "❌ *Можно отменить?*\n"
        "Да — предупреди за 24 часа: @VF746\n\n"
        f"💬 *Ещё вопросы:* {SUPPORT}",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# /status — статус участника
# ═══════════════════════════════════════════════════════════════════════════════
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = db_get(uid)

    if not user:
        kb = [[InlineKeyboardButton("📋 Заполнить анкету", callback_data="fill_chat")]]
        await update.message.reply_text(
            "Ты ещё не заполнял анкету.\nНажми /start чтобы начать.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    profile = user.get("profile", {})
    status  = user.get("status", "—")
    name    = profile.get("name", update.effective_user.first_name)

    kb = [[InlineKeyboardButton("✏️ Изменить анкету", callback_data="fill_chat")]]
    if status == "approved":
        kb.insert(0, [InlineKeyboardButton("🍽 Записаться на ужин", callback_data="register")])

    await update.message.reply_text(
        f"👤 *{name}*\n\n"
        f"📊 *Статус:* {status_text(status)}\n"
        f"🎂 *Возраст:* {profile.get('age', '—')}\n"
        f"🎯 *Цель:* {profile.get('goal', '—')}\n"
        f"🧠 *Темперамент:* {profile.get('temperament', '—')}\n"
        f"🎬 *Интересы:* {profile.get('interests', '—')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def cb_my_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    # Переиспользуем логику cmd_status, создавая псевдо-update
    uid  = update.callback_query.from_user.id
    user = db_get(uid)

    if not user:
        kb = [[InlineKeyboardButton("📋 Заполнить анкету", callback_data="fill_chat")]]
        await update.callback_query.message.reply_text(
            "Ты ещё не заполнял анкету.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    profile = user.get("profile", {})
    status  = user.get("status", "—")
    name    = profile.get("name", update.callback_query.from_user.first_name)

    kb = [[InlineKeyboardButton("✏️ Изменить анкету", callback_data="fill_chat")]]
    if status == "approved":
        kb.insert(0, [InlineKeyboardButton("🍽 Записаться на ужин", callback_data="register")])

    await update.callback_query.message.reply_text(
        f"👤 *{name}*\n\n"
        f"📊 *Статус:* {status_text(status)}\n"
        f"🎂 *Возраст:* {profile.get('age', '—')}\n"
        f"🎯 *Цель:* {profile.get('goal', '—')}\n"
        f"🧠 *Темперамент:* {profile.get('temperament', '—')}\n"
        f"🎬 *Интересы:* {profile.get('interests', '—')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Запись на ужин
# ═══════════════════════════════════════════════════════════════════════════════
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = db_get(uid)
    if user.get("status") != "approved":
        await q.answer("Сначала нужно пройти модерацию!", show_alert=True)
        return

    wed  = next_wednesday()
    date = format_wed(wed)
    db_set(uid, status="registered", dinner_date=date)

    name = user.get("profile", {}).get("name", q.from_user.first_name)

    await q.edit_message_text(
        f"🎉 *{name}, ты записан!*\n\n"
        f"📅 *{date}*\n"
        f"📍 Адрес ресторана пришлём за 24 часа\n\n"
        f"🎁 Это твой *первый бесплатный ужин*\n\n"
        f"Если не сможешь прийти — обязательно предупреди\n"
        f"за 24 часа: {SUPPORT}",
        parse_mode="Markdown",
    )

    # Уведомляем админа
    await ctx.bot.send_message(
        ADMIN_ID,
        f"🍽 *{name}* (@{q.from_user.username}) записался на ужин {date}",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# АНКЕТА В ЧАТЕ — ConversationHandler
# ═══════════════════════════════════════════════════════════════════════════════

def choice_kb(options: list[str]) -> ReplyKeyboardMarkup:
    """Создаёт клавиатуру из списка вариантов."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(o)] for o in options],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

async def cb_fill_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запуск анкеты через кнопку."""
    await update.callback_query.answer()
    ctx.user_data.clear()
    await update.callback_query.message.reply_text(
        "📋 *Анкета Togetherty*\n\n"
        "15 вопросов — займёт ~3 минуты.\n"
        "Для отмены напиши /cancel\n\n"
        "▶️ Начинаем!",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await ask_q1(update.callback_query.message, ctx)
    return Q_NAME

async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Повторное прохождение анкеты через /edit."""
    ctx.user_data.clear()
    await update.message.reply_text(
        "✏️ *Изменение анкеты*\n\nПройдём заново — займёт ~3 минуты.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await ask_q1(update.message, ctx)
    return Q_NAME

# ── Вопрос 1: Имя ──
async def ask_q1(msg, ctx):
    await msg.reply_text(
        "*Вопрос 1 из 15*\n\n👋 Как тебя зовут?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

async def handle_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 2 из 15*\n\n🎂 Сколько тебе лет?",
        parse_mode="Markdown",
        reply_markup=choice_kb(["18–24", "25–34", "35–44", "45+"]),
    )
    return Q_AGE

# ── Вопрос 2: Возраст ──
async def handle_age(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["age"] = update.message.text
    await update.message.reply_text(
        "*Вопрос 3 из 15*\n\n🌍 Откуда ты?\n"
        "_Район Рязани или другой город_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_CITY

# ── Вопрос 3: Город ──
async def handle_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["city"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 4 из 15*\n\n💼 Кем работаешь или чем занимаешься?\n"
        "_Профессия, учёба, бизнес — что угодно_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_JOB

# ── Вопрос 4: Работа ──
async def handle_job(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["job"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 5 из 15*\n\n🎯 Что тебя привело?\n"
        "_Выбери главную цель_",
        parse_mode="Markdown",
        reply_markup=choice_kb([
            "👥 Новые друзья",
            "💼 Нетворкинг",
            "🎉 Провести вечер",
            "💫 Романтика",
        ]),
    )
    return Q_GOAL

# ── Вопрос 5: Цель ──
async def handle_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["goal"] = update.message.text
    await update.message.reply_text(
        "*Вопрос 6 из 15*\n\n🧠 Как ты обычно себя ведёшь в компании?\n"
        "_Честный ответ поможет подобрать группу_",
        parse_mode="Markdown",
        reply_markup=choice_kb([
            "🌙 Интроверт — слушаю больше",
            "☀️ Экстраверт — легко завожу разговор",
            "⚖️ Амбиверт — по настроению",
            "🔥 Душа компании",
        ]),
    )
    return Q_TEMP

# ── Вопрос 6: Темперамент ──
async def handle_temp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["temperament"] = update.message.text
    await update.message.reply_text(
        "*Вопрос 7 из 15*\n\n🎬 Напиши 3–5 своих интересов через запятую\n\n"
        "_Примеры: кино, путешествия, технологии, книги, спорт, еда, искусство, музыка, игры, бизнес, фото, зож, наука_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_INTERESTS

# ── Вопрос 7: Интересы ──
async def handle_interests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["interests"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 8 из 15*\n\n📚 Последняя книга или фильм, которые тебя впечатлили?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_BOOK

# ── Вопрос 8: Книга/фильм ──
async def handle_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["book"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 9 из 15*\n\n🌟 Чем ты гордишься больше всего?\n"
        "_Любое достижение — большое или маленькое_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_PROUD

# ── Вопрос 9: Гордость ──
async def handle_proud(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["proud"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 10 из 15*\n\n🌱 Что хочешь изменить в своей жизни в этом году?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_CHANGE

# ── Вопрос 10: Изменить ──
async def handle_change(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["change"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 11 из 15*\n\n✈️ Какое место в мире мечтаешь посетить?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_PLACE

# ── Вопрос 11: Место мечты ──
async def handle_place(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["dream_place"] = update.message.text.strip()
    await update.message.reply_text(
        "*Вопрос 12 из 15*\n\n🗣 Как ты ведёшь себя за столом с новыми людьми?",
        parse_mode="Markdown",
        reply_markup=choice_kb([
            "🎧 Слушаю больше, чем говорю",
            "🗣 Говорю много, рассказываю истории",
            "🌊 По настроению",
            "🤝 Всё зависит от компании",
        ]),
    )
    return Q_TABLE

# ── Вопрос 12: Поведение за столом ──
async def handle_table(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["table_style"] = update.message.text
    await update.message.reply_text(
        "*Вопрос 13 из 15*\n\n🍕 Есть ли у тебя пищевые ограничения?\n"
        "_Нужно для подбора ресторана_",
        parse_mode="Markdown",
        reply_markup=choice_kb([
            "✅ Нет ограничений",
            "🥦 Вегетарианец",
            "🌱 Веган",
            "☪️ Халяль",
            "✏️ Другое — напишу в следующем шаге",
        ]),
    )
    return Q_FOOD

# ── Вопрос 13: Еда ──
async def handle_food(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["food"] = update.message.text
    await update.message.reply_text(
        "*Вопрос 14 из 15*\n\n📱 Твой Telegram-никнейм?\n"
        "_Для связи с командой и участниками_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_TG

# ── Вопрос 14: Telegram ──
async def handle_tg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["tg_username"] = update.message.text.strip().lstrip("@")
    await update.message.reply_text(
        "*Вопрос 15 из 15*\n\n💬 Одно предложение о себе.\n"
        "_Что важно знать другим участникам?_\n\n"
        "Например: _«Люблю котиков, коллекционирую пластинки и однажды проехал автостопом пол-России»_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return Q_ABOUT

# ── Вопрос 15: О себе → Финал ──
async def handle_about(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["about"] = update.message.text.strip()
    uid  = update.effective_user.id
    name = ctx.user_data.get("name", update.effective_user.first_name)

    # Сохраняем анкету
    db_set(uid,
        profile=dict(ctx.user_data),
        status="pending",
        tg_user=update.effective_user.username,
        submitted_at=datetime.now().isoformat(),
    )

    await update.message.reply_text(
        f"🎉 *Отлично, {name}!* Анкета отправлена.\n\n"
        f"⏳ Модератор проверит её в течение *1–2 часов* и пришлёт ответ.\n\n"
        f"Пока можешь подписаться на канал:\n{CHANNEL}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Уведомляем админа
    p = ctx.user_data
    await ctx.bot.send_message(
        ADMIN_ID,
        f"🆕 *Новая анкета!*\n\n"
        f"👤 {p.get('name')} (@{update.effective_user.username}, ID: {uid})\n"
        f"🎂 {p.get('age')} · {p.get('city')}\n"
        f"💼 {p.get('job')}\n"
        f"🎯 {p.get('goal')}\n"
        f"🧠 {p.get('temperament')}\n"
        f"🎬 {p.get('interests')}\n"
        f"💬 {p.get('about')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{uid}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{uid}"),
            ]
        ]),
    )

    return ConversationHandler.END

# ── /cancel ──
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "Анкета отменена. Напиши /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# WEBAPP DATA — данные из мини-аппа
# ═══════════════════════════════════════════════════════════════════════════════
async def handle_webapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import json
    uid = update.effective_user.id
    try:
        data = json.loads(update.message.web_app_data.data)
    except Exception as e:
        logger.error(f"Webapp data parse error: {e}")
        return

    name = data.get("q1", update.effective_user.first_name)
    profile = {
        "name":        data.get("q1", ""),
        "age":         data.get("q2", ""),
        "city":        data.get("q3", ""),
        "job":         data.get("q4", ""),
        "goal":        data.get("q5", ""),
        "temperament": data.get("q6", ""),
        "interests":   data.get("q7", ""),
        "book":        data.get("q8", ""),
        "proud":       data.get("q9", ""),
        "change":      data.get("q10", ""),
        "dream_place": data.get("q11", ""),
        "table_style": data.get("q12", ""),
        "food":        data.get("q13", ""),
        "tg_username": data.get("q14", ""),
        "about":       data.get("q15", ""),
    }

    db_set(uid,
        profile=profile,
        status="pending",
        tg_user=update.effective_user.username,
        submitted_at=datetime.now().isoformat(),
    )

    await update.message.reply_text(
        f"🎉 *{name}, анкета получена!*\n\n"
        f"⏳ Ожидай одобрения — обычно 1–2 часа.",
        parse_mode="Markdown",
    )

    # Уведомляем админа
    await ctx.bot.send_message(
        ADMIN_ID,
        f"🆕 *Новая анкета (мини-апп)!*\n\n"
        f"👤 {name} (@{update.effective_user.username}, ID: {uid})\n"
        f"🎂 {profile['age']} · {profile['city']}\n"
        f"🎯 {profile['goal']} · {profile['temperament']}\n"
        f"🎬 {profile['interests']}\n"
        f"💬 {profile['about']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{uid}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{uid}"),
            ]
        ]),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# МОДЕРАЦИЯ — одобрить/отклонить
# ═══════════════════════════════════════════════════════════════════════════════
async def cb_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = int(q.data.split("_")[1])
    await q.answer("Одобрено ✅")

    if q.from_user.id != ADMIN_ID:
        return

    user = db_get(uid)
    name = user.get("profile", {}).get("name", "Участник")
    db_set(uid, status="approved")

    wed = format_wed(next_wednesday())
    await ctx.bot.send_message(
        uid,
        f"✅ *{name}, анкета одобрена!*\n\n"
        f"🎁 Первый ужин — *бесплатно*\n"
        f"📅 Ближайший: *{wed}*\n\n"
        f"Записаться?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍽 Записаться на ужин", callback_data="register")],
            [InlineKeyboardButton("📊 Мой статус",         callback_data="my_status")],
        ]),
    )

    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Одобрено — {name}", callback_data="noop")]
        ])
    )


async def cb_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = int(q.data.split("_")[1])
    await q.answer("Отклонено ❌")

    if q.from_user.id != ADMIN_ID:
        return

    user = db_get(uid)
    name = user.get("profile", {}).get("name", "Участник")
    db_set(uid, status="rejected")

    await ctx.bot.send_message(
        uid,
        f"❌ К сожалению, анкета не прошла модерацию.\n\n"
        f"Если считаешь, что это ошибка — напиши {SUPPORT}",
    )

    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"❌ Отклонено — {name}", callback_data="noop")]
        ])
    )


# ═══════════════════════════════════════════════════════════════════════════════
# /admin — панель в боте
# ═══════════════════════════════════════════════════════════════════════════════
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return

    total      = len(DB)
    pending    = sum(1 for u in DB.values() if u.get("status") == "pending")
    approved   = sum(1 for u in DB.values() if u.get("status") == "approved")
    registered = sum(1 for u in DB.values() if u.get("status") == "registered")

    kb = [
        [InlineKeyboardButton("⏳ Ожидают проверки",    callback_data="adm_pending")],
        [InlineKeyboardButton("✅ Одобренные участники", callback_data="adm_approved")],
        [InlineKeyboardButton("🍽 Записаны на ужин",    callback_data="adm_registered")],
        [InlineKeyboardButton("📋 Все анкеты",          callback_data="adm_all")],
        [InlineKeyboardButton("📣 Рассылка всем",       callback_data="adm_broadcast")],
    ]

    await update.message.reply_text(
        f"🔧 *Панель Togetherty*\n\n"
        f"👥 Всего анкет: *{total}*\n"
        f"⏳ На проверке: *{pending}*\n"
        f"✅ Одобрено: *{approved}*\n"
        f"🍽 Записаны: *{registered}*\n\n"
        f"📅 Следующий ужин: *{format_wed(next_wednesday())}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Нет доступа", show_alert=True)
        return
    await q.answer()

    action = q.data

    if action == "adm_pending":
        users = [(uid, u) for uid, u in DB.items() if u.get("status") == "pending"]
        if not users:
            await q.message.reply_text("Нет анкет на проверке ✅")
            return
        for uid, u in users:
            p = u.get("profile", {})
            await q.message.reply_text(
                f"👤 *{p.get('name', '?')}* (@{u.get('tg_user', '?')})\n"
                f"🎂 {p.get('age')} · {p.get('city')}\n"
                f"🎯 {p.get('goal')}\n"
                f"🧠 {p.get('temperament')}\n"
                f"🎬 {p.get('interests')}\n"
                f"💬 {p.get('about')}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Одобрить",  callback_data=f"approve_{uid}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{uid}"),
                    ]
                ]),
            )

    elif action in ("adm_approved", "adm_registered", "adm_all"):
        filter_map = {
            "adm_approved":   "approved",
            "adm_registered": "registered",
            "adm_all":        None,
        }
        f = filter_map[action]
        users = [
            (uid, u) for uid, u in DB.items()
            if f is None or u.get("status") == f
        ]
        if not users:
            await q.message.reply_text("Список пуст.")
            return
        lines = []
        for uid, u in users:
            p    = u.get("profile", {})
            name = p.get("name", "?")
            tg   = u.get("tg_user", "?")
            s    = u.get("status", "?")
            emoji = {"pending":"⏳","approved":"✅","rejected":"❌","registered":"🍽"}.get(s, "•")
            lines.append(f"{emoji} {name} (@{tg})")
        await q.message.reply_text("\n".join(lines))

    elif action == "adm_broadcast":
        await q.message.reply_text(
            "Напиши сообщение для рассылки всем участникам.\n"
            "Формат: /broadcast <текст>"
        )


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Рассылка всем участникам со статусом approved/registered."""
    if update.effective_user.id != ADMIN_ID:
        return

    text = " ".join(ctx.args)
    if not text:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return

    sent = 0
    for uid, u in DB.items():
        if u.get("status") in ("approved", "registered", "pending"):
            try:
                await ctx.bot.send_message(uid, text)
                sent += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {uid}: {e}")

    await update.message.reply_text(f"✅ Рассылка отправлена: {sent} участникам")


# ═══════════════════════════════════════════════════════════════════════════════
# НАПОМИНАНИЯ — фоновая задача
# ═══════════════════════════════════════════════════════════════════════════════
async def reminder_loop(app: Application):
    """Проверяет каждый час — нужно ли отправить напоминание за 24ч."""
    while True:
        await asyncio.sleep(3600)
        now = datetime.now()
        wed = next_wednesday()
        diff_hours = (wed - now).total_seconds() / 3600

        if 23 <= diff_hours <= 25:
            for uid, u in DB.items():
                if u.get("status") == "registered" and not u.get("notified_24h"):
                    name = u.get("profile", {}).get("name", "Участник")
                    rest = u.get("restaurant", "— адрес пришлём скоро")
                    try:
                        await app.bot.send_message(
                            uid,
                            f"⏰ *{name}, завтра ужин!*\n\n"
                            f"📍 {rest}\n"
                            f"🕢 19:30\n\n"
                            f"Увидимся за столом! 🍽",
                            parse_mode="Markdown",
                        )
                        db_set(uid, notified_24h=True)
                    except Exception as e:
                        logger.warning(f"Reminder failed for {uid}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler — анкета в чате
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_fill_chat, pattern="^fill_chat$"),
            CommandHandler("edit", cmd_edit),
        ],
        states={
            Q_NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            Q_AGE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
            Q_CITY:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city)],
            Q_JOB:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_job)],
            Q_GOAL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal)],
            Q_TEMP:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_temp)],
            Q_INTERESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_interests)],
            Q_BOOK:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_book)],
            Q_PROUD:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_proud)],
            Q_CHANGE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_change)],
            Q_PLACE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_place)],
            Q_TABLE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_table)],
            Q_FOOD:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_food)],
            Q_TG:        [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tg)],
            Q_ABOUT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_about)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("admin",     cmd_admin))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(conv)

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp))

    app.add_handler(CallbackQueryHandler(cb_faq,        pattern="^faq$"))
    app.add_handler(CallbackQueryHandler(cb_my_status,  pattern="^my_status$"))
    app.add_handler(CallbackQueryHandler(cb_register,   pattern="^register$"))
    app.add_handler(CallbackQueryHandler(cb_approve,    pattern=r"^approve_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_reject,     pattern=r"^reject_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_admin,      pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern="^noop$"))

    # Запуск напоминаний
    async def post_init(app):
        asyncio.create_task(reminder_loop(app))
    app.post_init = post_init

    logger.info("🚀 Togetherty bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
