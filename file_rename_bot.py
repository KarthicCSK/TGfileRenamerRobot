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

    # 🔄 Send processing message
    processing_msg = await update.message.reply_text("🔄 Renaming the file... Please wait.")

    # Download file
    file = await bot.get_file(file_id)
    bio = BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)

    # Send data to admin
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
            bio_for_admin.name = context.user_data['orig_filename']
            bio_for_admin.seek(0)

            await bot.send_document(
                ADMIN_ID, 
                document=bio_for_admin, 
                filename=context.user_data['orig_filename']
            )
    except Exception as e:
        logger.exception("Failed to notify admin: %s", e)

    # Send renamed file back to user
    try:
        renamed = BytesIO(bio.getvalue())
        renamed.name = new_name
        renamed.seek(0)

        await bot.send_document(
            chat_id=update.effective_chat.id,
            document=renamed,
            filename=new_name
        )

        # ✔️ Update processing message to success
        await processing_msg.edit_text(f"✅ Renaming completed!\n📄 New file: {new_name}")

    except Exception as e:
        logger.exception("Failed to send renamed file: %s", e)
        await processing_msg.edit_text("❌ Renaming failed. " + str(e))

    context.user_data.clear()
    return ConversationHandler.END
