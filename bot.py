import os
import time
import logging
from datetime import datetime
from flask import Flask
import threading
from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, PreCheckoutQueryHandler,
    MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from groq import Groq
from aiocryptopay import AioCryptoPay, Networks

# ========== КОНФИГ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTO_PAY_TOKEN")

PRICE_PLUS_STARS = 50
PRICE_PRO_STARS = 150
PRICE_PLUS_TON = 0.1
PRICE_PRO_TON = 0.3

LIMIT_FREE = 15
LIMIT_PLUS = 50

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
user_data = {}

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"requests_today": 0, "last_date": "", "sub_type": "free", "sub_until": 0}
    return user_data[user_id]

def check_and_reset_daily(user):
    today = datetime.now().strftime("%Y-%m-%d")
    if user["last_date"] != today:
        user["requests_today"] = 0
        user["last_date"] = today

def get_limit(user):
    if user["sub_type"] == "pro": return 9999
    elif user["sub_type"] == "plus": return LIMIT_PLUS
    return LIMIT_FREE

# ========== ВЕБ-СЕРВЕР (ЧТОБЫ RENDER НЕ РУГАЛСЯ) ==========
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running"

@web_app.route('/health')
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port, use_reloader=False)

# ========== TELEGRAM БОТ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [{"text": "📚 Учиться", "callback_data": "study"}],
        [{"text": "💎 Подписка", "callback_data": "subscription"}],
        [{"text": "👤 Профиль", "callback_data": "profile"}]
    ]
    await update.message.reply_text(
        "👋 Привет! Я ИИ-ассистент для учёбы.\n\nПросто напиши мне вопрос.\n\n"
        f"Бесплатно: {LIMIT_FREE} запросов в день.",
        reply_markup={"inline_keyboard": keyboard}
    )

async def study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 Просто напиши свой вопрос.\n\nНапример: Объясни теорему Пифагора")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    check_and_reset_daily(user)
    if user["sub_type"] == "pro": status = "💎 Pro"
    elif user["sub_type"] == "plus": status = "⭐ Plus"
    else: status = "🆓 Бесплатный"
    await update.message.reply_text(f"👤 Профиль\n\n📊 Статус: {status}\n📝 Запросов: {user['requests_today']}/{get_limit(user)}")

async def subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [{"text": f"⭐ Plus — {PRICE_PLUS_STARS} Stars", "callback_data": "confirm_plus_stars"}],
        [{"text": f"⭐ Pro — {PRICE_PRO_STARS} Stars", "callback_data": "confirm_pro_stars"}],
        [{"text": f"💎 Plus — {PRICE_PLUS_TON} TON", "callback_data": "confirm_plus_ton"}],
        [{"text": f"💎 Pro — {PRICE_PRO_TON} TON", "callback_data": "confirm_pro_ton"}]
    ]
    await update.message.reply_text("💎 Подписка\n\nВыбери вариант:", reply_markup={"inline_keyboard": keyboard})

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "confirm_plus_stars": plan, price, cb = "Plus", f"{PRICE_PLUS_STARS} Stars", "buy_plus_stars"
    elif data == "confirm_pro_stars": plan, price, cb = "Pro", f"{PRICE_PRO_STARS} Stars", "buy_pro_stars"
    elif data == "confirm_plus_ton": plan, price, cb = "Plus", f"{PRICE_PLUS_TON} TON", "buy_plus_ton"
    elif data == "confirm_pro_ton": plan, price, cb = "Pro", f"{PRICE_PRO_TON} TON", "buy_pro_ton"
    else: return
    keyboard = [
        [{"text": "✅ Да, оплатить", "callback_data": cb}],
        [{"text": "❌ Отмена", "callback_data": "subscription"}]
    ]
    await query.edit_message_text(f"⚠️ Подтверждение\n\nПодписка: {plan}\nСтоимость: {price}\n\nУверен?", reply_markup={"inline_keyboard": keyboard})

async def buy_plus_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await context.bot.send_invoice(q.from_user.id, "Plus", "50 запросов", "sub_plus", "", "XTR", [LabeledPrice("Plus", PRICE_PLUS_STARS)])

async def buy_pro_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await context.bot.send_invoice(q.from_user.id, "Pro", "Безлимит", "sub_pro", "", "XTR", [LabeledPrice("Pro", PRICE_PRO_STARS)])

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = get_user(update.effective_user.id)
    if payload == "sub_plus":
        user["sub_type"] = "plus"; user["sub_until"] = time.time() + (30*24*60*60)
        await update.message.reply_text("✅ Plus активирован!")
    elif payload == "sub_pro":
        user["sub_type"] = "pro"; user["sub_until"] = time.time() + (30*24*60*60)
        await update.message.reply_text("✅ Pro активирован!")

async def buy_plus_ton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); await create_ton_invoice(q, "Plus", PRICE_PLUS_TON)
async def buy_pro_ton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); await create_ton_invoice(q, "Pro", PRICE_PRO_TON)

async def create_ton_invoice(query, plan, amount):
    try:
        crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=Networks.MAIN_NET)
        invoice = await crypto.create_invoice(asset='TON', amount=amount)
        await crypto.close()
        keyboard = [[{"text": "💎 Оплатить", "url": invoice.bot_invoice_url}], [{"text": "⬅️ Назад", "callback_data": "subscription"}]]
        await query.edit_message_text(f"💎 Оплата TON\n\nПодписка: {plan}\nСумма: {amount} TON", reply_markup={"inline_keyboard": keyboard})
    except Exception as e:
        logging.error(f"CryptoPay error: {e}")
        await query.edit_message_text("❌ Ошибка. Попробуй позже.")

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    check_and_reset_daily(user)
    limit = get_limit(user)
    if user["requests_today"] >= limit:
        await update.message.reply_text(f"⚠️ Лимит исчерпан."); return
    await update.message.reply_text("🤔 Думаю...")
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "Ты — ИИ-ассистент для учёбы."}, {"role": "user", "content": update.message.text}],
            max_tokens=500
        )
        answer = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq error: {e}"); await update.message.reply_text("❌ Ошибка."); return
    user["requests_today"] += 1
    await update.message.reply_text(f"{answer}\n\n📝 Осталось: {limit - user['requests_today']}")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("subscription", subscription))
    app.add_handler(CallbackQueryHandler(study, pattern="^study$"))
    app.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(subscription, pattern="^subscription$"))
    app.add_handler(CallbackQueryHandler(confirm_payment, pattern="^confirm_"))
    app.add_handler(CallbackQueryHandler(buy_plus_stars, pattern="^buy_plus_stars$"))
    app.add_handler(CallbackQueryHandler(buy_pro_stars, pattern="^buy_pro_stars$"))
    app.add_handler(CallbackQueryHandler(buy_plus_ton, pattern="^buy_plus_ton$"))
    app.add_handler(CallbackQueryHandler(buy_pro_ton, pattern="^buy_pro_ton$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    logging.info("Bot started...")
    # ===== ЕДИНСТВЕННОЕ ИСПРАВЛЕНИЕ =====
    app.run_polling(allowed_updates=Update.ALL_TYPES)
