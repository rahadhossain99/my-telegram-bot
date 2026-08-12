import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')

# /start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **উন্নত YouTube ডাউনলোডার বটে স্বাগতম!**\n\n"
        "যেকোনো YouTube ভিডিও বা Shorts-এর লিংক এখানে পাঠান। "
        "আমি আপনাকে বিভিন্ন কোয়ালিটি ও MP3 অডিও অপশন তৈরি করে দেব।"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# YouTube Link Handler
async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ অনুগ্রহ করে একটি সঠিক YouTube ভিডিও বা Shorts লিংক পাঠান।")
        return

    status_msg = await update.message.reply_text("🔎 ভিডিওর তথ্য তথ্য সংগ্রহ করা হচ্ছে...")

    # Options to extract video info without downloading
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        title = info.get('title', 'YouTube Video')
        duration = info.get('duration', 0)
        minutes, seconds = divmod(duration, 60)
        
        # Save info in context for callback
        context.user_data['video_url'] = url
        context.user_data['video_title'] = title

        # Quality Selection Buttons
        keyboard = [
            [
                InlineKeyboardButton("🎬 Best Quality (Max 50MB)", callback_data='dl_best'),
                InlineKeyboardButton("📱 Mobile (480p/720p)", callback_data='dl_medium')
            ],
            [
                InlineKeyboardButton("🎵 Audio MP3", callback_data='dl_audio')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = f"📌 **{title}**\n⏱ **দৈর্ঘ্য:** {minutes} মি. {seconds} সে."
        await status_msg.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        await status_msg.edit_text(f"❌ তথ্য পেতে ত্রুটি ঘটেছে!\n\nError: {str(e)}")

# Button Click Handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('video_url')
    title = context.user_data.get('video_title', 'Video')
    choice = query.data

    if not url:
        await query.edit_message_text("❌ সেশন মেয়াদোত্তীর্ণ হয়ে গেছে। অনুগ্রহ করে আবার লিংক পাঠান।")
        return

    await query.edit_message_text("⏳ ডাউনলোড শুরু হচ্ছে... অনুগ্রহ করে কিছুটা সময় দিন।")

    # Dynamic options based on user choice
    if choice == 'dl_best':
        fmt = 'best[filesize<50M]/bestvideo[filesize<35M]+bestaudio/best'
        is_audio = False
    elif choice == 'dl_medium':
        fmt = 'bestvideo[height<=720][filesize<40M]+bestaudio/best[height<=720]/worst'
        is_audio = False
    elif choice == 'dl_audio':
        fmt = 'bestaudio/best'
        is_audio = True

    output_filename = "downloaded_media.%(ext)s"

    ydl_opts = {
        'format': fmt,
        'outtmpl': output_filename,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android_vr']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await query.edit_message_text("📤 ফাইল টেলিগ্রামে আপলোড হচ্ছে...")

        with open(filename, 'rb') as file_data:
            if is_audio:
                await query.message.reply_audio(audio=file_data, caption=f"🎵 {title}")
            else:
                await query.message.reply_video(video=file_data, caption=f"🎬 {title}")

        # Delete local temporary file
        if os.path.exists(filename):
            os.remove(filename)
        await query.delete_message()

    except Exception as e:
        await query.edit_message_text(
            f"❌ ফাইল পাঠানো সম্ভব হয়নি।\n"
            f"কারণ: ৫০MB লিমিট অতিক্রম করতে পারে অথবা ইউটিউব প্রসেস ত্রুটি।\n\nError: {str(e)}"
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("উন্নত বটের কাজ শুরু হয়েছে...")
    app.run_polling()
    
