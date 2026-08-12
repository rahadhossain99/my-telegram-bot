import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 স্বাগতম! যেকোনো YouTube ভিডিওর লিংক এখানে পাঠান, আমি ভিডিওটি ডাউনলোড করে দেব।"
    )

async def download_youtube_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    if "youtube.com" in url or "youtu.be" in url:
        status_msg = await update.message.reply_text("⏳ ভিডিও ডাউনলোড হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...")
        
        ydl_opts = {
            'format': 'best[filesize<50M]/worst',
            'outtmpl': 'downloaded_video.%(ext)s',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
            
            await status_msg.edit_text("📤 ভিডিও আপলোড হচ্ছে...")
            
            with open(filename, 'rb') as video_file:
                await update.message.reply_video(video=video_file, caption=info.get('title', 'YouTube Video'))
            
            if os.path.exists(filename):
                os.remove(filename)
            await status_msg.delete()
            
        except Exception as e:
            await status_msg.edit_text(f"❌ ডাউনলোড করা সম্ভব হয়নি। (Telegram লিমিট ৫০MB বা প্রসেস ত্রুটি)\n\nError: {str(e)}")
    else:
        await update.message.reply_text("অনুগ্রহ করে একটি সঠিক YouTube লিংক পাঠান।")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_youtube_video))

    print("Bot is running...")
    app.run_polling()
  
