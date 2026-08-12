import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

# লগিং কনফিগারেশন
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')

# আপলোড করা কুকি ফাইলের নাম
COOKIE_FILES = ['cookie1.txt']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **YouTube Downloader Bot-এ স্বাগতম!**\n\n"
        "যেকোনো YouTube ভিডিও বা Shorts-এর লিংক পাঠালে আমি ডাউনলোড করে দেব।"
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
            InlineKeyboardButton("🎵 Download Audio (MP3)", callback_data='audio')
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

    output_filename = "downloaded_media.%(ext)s"

    selected_cookie = random.choice(COOKIE_FILES)

    # yt-dlp কনফিগারেশন
    ydl_opts = {
        'cookiefile': selected_cookie,
        'format': 'bestaudio/best' if download_type == 'audio' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_filename,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android_vr', 'mweb']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await query.edit_message_text("📤 ফাইল টেলিগ্রামে পাঠানো হচ্ছে...")

        with open(filename, 'rb') as file_data:
            if download_type == 'audio':
                await query.message.reply_audio(audio=file_data)
            else:
                await query.message.reply_video(video=file_data)

        if os.path.exists(filename):
            os.remove(filename)
        await query.delete_message()

    except Exception as e:
        await query.edit_message_text(f"❌ ডাউনলোড করতে সমস্যা হয়েছে।\n\nকারণ: {str(e)}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot starting...")
    # drop_pending_updates=True এর মাধ্যমে আগের আটকে থাকা কনফ্লিক্টিং রিকোয়েস্টগুলো ক্লিয়ার হয়ে যাবে
    app.run_polling(drop_pending_updates=True)
