import os
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **YouTube Downloader Bot-এ স্বাগতম!**\n\n"
        "যেকোনো YouTube বা Shorts লিংক পাঠালে আমি প্রক্সি ঝামেলা ছাড়াই ডাউনলোড করে দেব।"
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ সঠিক YouTube লিংক পাঠান।")
        return

    context.user_data['url'] = url

    keyboard = [
        [
            InlineKeyboardButton("🎬 Video (HD)", callback_data='video'),
            InlineKeyboardButton("🎵 Audio MP3", callback_data='audio')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("কী ফরম্যাটে ডাউনলোড করতে চান বেছে নিন:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('url')
    download_type = query.data

    if not url:
        await query.edit_message_text("❌ সেশন মেয়াদ শেষ। আবার লিংক পাঠান।")
        return

    await query.edit_message_text("⏳ প্রসেস করা হচ্ছে, অপেক্ষা করুন...")

    # Cobalt API দিয়ে ইউটিউব প্রক্সি ব্লক বাইপাস
    cobalt_api = "https://api.cobalt.tools/api/json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "isAudioOnly": True if download_type == 'audio' else False
    }

    try:
        response = requests.post(cobalt_api, json=payload, headers=headers)
        data = response.json()

        if data.get("status") in ["tunnel", "redirect"]:
            download_url = data.get("url")
            
            await query.edit_message_text("📤 ফাইল ডাউনলোড হয়ে টেলিগ্রামে পাঠানো হচ্ছে...")

            # ফাইল ডাউনলোড করা
            media_bytes = requests.get(download_url).content
            file_name = "audio.mp3" if download_type == 'audio' else "video.mp4"

            with open(file_name, "wb") as f:
                f.write(media_bytes)

            with open(file_name, "rb") as f:
                if download_type == 'audio':
                    await query.message.reply_audio(audio=f)
                else:
                    await query.message.reply_video(video=f)

            if os.path.exists(file_name):
                os.remove(file_name)
            await query.delete_message()

        else:
            await query.edit_message_text("❌ ডাউনলোড করতে সমস্যা হয়েছে বা লিঙ্কটি কাজ করছে না।")

    except Exception as e:
        await query.edit_message_text(f"❌ এরর ঘটেছে: {str(e)}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot starting...")
    app.run_polling()
    
