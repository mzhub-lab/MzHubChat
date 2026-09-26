import os
import re
import html
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

# Background me dummy web server start karein
Thread(target=run_web, daemon=True).start()

# --- Bot Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_NAME = "users.db"

# --- Database Setup (SQLite) ---
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

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    safe_first_name = html.escape(user.first_name)
    user_link = f'<a href="tg://user?id={user.id}">{safe_first_name}</a>'

    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 <b>Admin Panel Active</b>\n\n"
            "• Users ke message par <b>Reply</b> karke direct chat karein.\n"
            "• Broadcast ke liye: <code>/broadcast &lt;message&gt;</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"Namaste {user_link}! 👋\n\n"
            "Apni problem ya sawal yahan likhkar bhejein, humari team jald se jald aapse sampark karegi.",
            parse_mode="HTML"
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format galat hai! Use karein: `/broadcast <Aapka Message>`")
        return

    broadcast_text = " ".join(context.args)
    users = get_all_users()

    sent_count = 0
    failed_count = 0

    status_msg = await update.message.reply_text("Broadcast shuru ho raha hai...")

    for uid in users:
        if uid == ADMIN_ID:
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_text)
            sent_count += 1
            await asyncio.sleep(0.05)  # Telegram rate limit prevention
        except Exception:
            failed_count += 1

    await status_msg.edit_text(
        f"✅ <b>Broadcast Pura Hua!</b>\n\n"
        f"• Success: {sent_count}\n"
        f"• Failed/Blocked: {failed_count}",
        parse_mode="HTML"
    )

# --- Message & Two-way Chat Handling ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    # 1. ADMIN REPLY LOGIC
    if user.id == ADMIN_ID:
        if update.message.reply_to_message:
            orig = update.message.reply_to_message
            target_id = None

            # Check 1: Forward source
            if orig.forward_from:
                target_id = orig.forward_from.id

            # Check 2: Header tag se user id nikalna [ID: xxxxx]
            if not target_id:
                header_text = orig.text or orig.caption or ""
                match = re.search(r"\[ID:\s*(\d+)\]", header_text)
                if match:
                    target_id = int(match.group(1))

            # Check 3: Bot memory tracking map
            if not target_id and "forward_map" in context.bot_data:
                target_id = context.bot_data["forward_map"].get(orig.message_id)

            if target_id:
                try:
                    await context.bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=ADMIN_ID,
                        message_id=update.message.message_id
                    )
                    await update.message.reply_text("✅ Reply user tak pahunch gaya!")
                except Exception as e:
                    await update.message.reply_text(f"❌ Reply bhejne me error aaya: {e}")
            else:
                await update.message.reply_text("⚠️ User identify nahi ho saka. Kripya user ke message par hi swipe/reply karein.")
        else:
            await update.message.reply_text("ℹ️ Reply bhejne ke liye user ke forwarded message par swipe/reply karein.")

    # 2. NORMAL USER MESSAGE LOGIC
    else:
        safe_name = html.escape(user.first_name)
        user_link = f'<a href="tg://user?id={user.id}">{safe_name}</a>'

        user_header = (
            f"📩 <b>Naya Message</b>\n"
            f"👤 User: {user_link}\n"
            f"🆔 [ID: {user.id}]\n"
            f"--------------------\n\n"
        )

        try:
            # Text message forward
            if update.message.text:
                sent = await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=user_header + html.escape(update.message.text),
                    parse_mode="HTML"
                )
            # Photo, Video, File ya Document forward
            else:
                existing_caption = html.escape(update.message.caption) if update.message.caption else ""
                sent = await context.bot.copy_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=user.id,
                    message_id=update.message.message_id,
                    caption=user_header + existing_caption,
                    parse_mode="HTML"
                )

            # Context mapping memory me store karein
            if "forward_map" not in context.bot_data:
                context.bot_data["forward_map"] = {}
            context.bot_data["forward_map"][sent.message_id] = user.id

            await update.message.reply_text("Aapka message mil gaya hai, hum jald reply karenge.")

        except Exception as e:
            print(f"Forward error to admin: {e}")
            await update.message.reply_text("Khed hai, abhi message admin tak nahi pahunch saka.")

# --- Main Entrypoint ---
if __name__ == "__main__":
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Sabhi updates (Text, Photos, Documents) handle karne ke liye
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_message))

    print("Support & Broadcast Bot shuru ho gaya hai...")
    app.run_polling()
  
