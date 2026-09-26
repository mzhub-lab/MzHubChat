import os
import sqlite3
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# --- Render Dummy Web Server ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is alive and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# Background me web server chalane ke liye
Thread(target=run_web).start()

# --- Bot Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_NAME = "users.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 Admin Panel Active\n\n"
            "• User ke message par reply karein direct baat karne ke liye.\n"
            "• Broadcast ke liye: `/broadcast <message>`"
        )
    else:
        await update.message.reply_text(
            f"Namaste {user.first_name}! 👋\nApni problem yahan likhein, hum jald hi reply karenge."
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args:
        return
    text = " ".join(context.args)
    users = get_all_users()
    for uid in users:
        if uid != ADMIN_ID:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                await asyncio.sleep(0.05)
            except Exception:
                pass
    await update.message.reply_text("✅ Broadcast complete!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    if user.id == ADMIN_ID:
        if update.message.reply_to_message:
            orig = update.message.reply_to_message
            target_id = None
            if orig.forward_from:
                target_id = orig.forward_from.id
            elif "forward_map" in context.bot_data and orig.message_id in context.bot_data["forward_map"]:
                target_id = context.bot_data["forward_map"][orig.message_id]

            if target_id:
                try:
                    await context.bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=ADMIN_ID,
                        message_id=update.message.message_id
                    )
                    await update.message.reply_text("✅ Reply sent.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("Reply karne ke liye user ke message ko quote/reply karein.")
    else:
        fwd = await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user.id,
            message_id=update.message.message_id
        )
        if "forward_map" not in context.bot_data:
            context.bot_data["forward_map"] = {}
        context.bot_data["forward_map"][fwd.message_id] = user.id
        await update.message.reply_text("Aapka message mil gaya hai, hum jald reply karenge.")

if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_message))
    app.run_polling()
          
