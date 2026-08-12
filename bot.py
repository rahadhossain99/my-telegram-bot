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
        "যেকোনো YouTube ভিডিও বা Shorts-এর লিংক পাঠালে আমি তা ডাউনলোড করে দেব।"
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ অনুগ্রহ করে সঠিক YouTube লিংক পাঠান।")
        return

    context.user_data['url'] = url

    keyboard = [
        [
            InlineKeyboardButton("🎬 Download Video", callback_data='video'),
            InlineKeyboardButton("🎵 Download Audio", callback_data='audio')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ফরম্যাট নির্বাচন করুন:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('url')
    download_type = query.data

    if not url:
        await query.edit_message_text("❌ সেশন মেয়াদ শেষ। আবার লিংক পাঠান।")
        return

    await query.edit_message_text("⏳ প্রসেস করা হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")

    # Cobalt API চেষ্টা করা
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
        response = requests.post(cobalt_api, json=payload, headers=headers, timeout=15)
        data = response.json()

        download_url = None
        if data.get("status") in ["tunnel", "redirect", "picker"]:
            download_url = data.get("url")
            if not download_url and data.get("picker"):
                download_url = data["picker"][0].get("url")

        if download_url:
            await query.edit_message_text("📤 ফাইল ডাউনলোড হয়ে টেলিগ্রামে পাঠানো হচ্ছে...")

            media_res = requests.get(download_url, stream=True, timeout=30)
            file_name = "audio.mp3" if download_type == 'audio' else "video.mp4"

            with open(file_name, "wb") as f:
                for chunk in media_res.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)

            with open(file_name, "rb") as f:
                if download_type == 'audio':
                    await query.message.reply_audio(audio=f)
                else:
                    await query.message.reply_video(video=f)

            if os.path.exists(file_name):
                os.remove(file_name)
            await query.delete_message()
        else:
            await query.edit_message_text("❌ সার্ভার থেকে ফাইল পাওয়া যায়নি। অন্য ভিডিওর লিংক চেষ্টা করুন।")

    except Exception as e:
        await query.edit_message_text(f"❌ ডাউনলোড প্রসেসে সমস্যা হয়েছে: {str(e)}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is running...")
    app.run_polling()
    
