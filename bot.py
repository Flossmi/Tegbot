import os
import time
import logging
from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, PreCheckoutQueryHandler,
    MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========== ХРАНИЛИЩЕ ==========
user_data = {}

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "posts_this_month": 0,
            "last_month": "",
            "sub_until": 0,
            "posts_count": 0
        }
    return user_data[user_id]

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [{"text": "📝 Публикация поста", "callback_data": "post_menu"}],
        [{"text": "👤 Профиль", "callback_data": "menu_profile"}],
        [{"text": "💎 Подписка", "callback_data": "menu_subscription"}]
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот-планировщик. Выбери раздел:",
        reply_markup={"inline_keyboard": keyboard}
    )

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_invoice(
        chat_id=user_id,
        title="Подписка на 30 дней",
        description="Доступ к планировщику (150 постов в месяц)",
        payload=f"sub_{user_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Подписка", 10)]
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["sub_until"] = time.time() + (30 * 24 * 60 * 60)
    await update.message.reply_text("✅ Оплата прошла! Подписка активирована на 30 дней. Лимит: 150 постов/мес.")

async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    is_sub = user["sub_until"] > time.time()
    limit = 150 if is_sub else 30

    current_month = time.strftime("%m", time.localtime())
    if user["last_month"] != current_month:
        user["posts_this_month"] = 0
        user["last_month"] = current_month

    if user["posts_this_month"] >= limit:
        await update.message.reply_text(
            f"⚠️ Лимит постов исчерпан! ({limit} в месяц)\n\n"
            "Оформи подписку в разделе «💎 Подписка», чтобы получить 150 постов."
        )
        return

    topic = " ".join(context.args) if context.args else None
    if not topic:
        await update.message.reply_text("📝 Напиши тему: /post новости игровой индустрии")
        return

    await update.message.reply_text("🤖 Генерирую пост...")

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты — SMM-редактор. Пиши короткие посты (до 500 символов) с эмодзи и хештегами."},
                {"role": "user", "content": f"Напиши пост на тему: {topic}"}
            ],
            max_tokens=300
        )
        post_text = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq error: {e}")
        await update.message.reply_text("❌ Ошибка генерации. Попробуй позже.")
        return

    user["posts_this_month"] += 1
    user["posts_count"] += 1
    await update.message.reply_text(
        f"📝 Черновик:\n\n{post_text}\n\n"
        f"Осталось постов: {limit - user['posts_this_month']}"
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "post_menu":
        await query.edit_message_text("📝 Отправь команду: /post <тема>\n\nПример: /post новости игр")
    elif data == "menu_profile":
        user = get_user(query.from_user.id)
        await query.edit_message_text(
            f"👤 Профиль\n\n🆔 ID: {query.from_user.id}\n"
            f"📝 Постов создано: {user['posts_count']}"
        )
    elif data == "menu_subscription":
        user = get_user(query.from_user.id)
        is_sub = user["sub_until"] > time.time()
        if is_sub:
            await query.edit_message_text("💎 Подписка активна! Лимит: 150 постов/мес.")
        else:
            await query.edit_message_text(
                "💎 Подписка\n\n"
                "Бесплатно: 30 постов/мес\n"
                "С подпиской: 150 постов/мес\n\n"
                "Стоимость: 10 Stars/мес\n\n"
                "Нажми /buy для оплаты."
            )

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful))
    app.add_handler(CallbackQueryHandler(button_handler))

    logging.info("Бот запущен...")
    app.run_polling()
