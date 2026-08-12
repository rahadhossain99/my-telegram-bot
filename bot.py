import os
import random
import logging
import cv2
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
import yt_dlp
import static_ffmpeg

# অটোমেটিক FFmpeg ইনভায়রনমেন্টে যুক্ত করা
try:
    static_ffmpeg.add_paths()
except Exception as e:
    logging.warning(f"FFmpeg Initialization Warning: {e}")

# লগিং কনফিগারেশন
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')
COOKIE_FILES = ['cookie1.txt']

def get_valid_cookie():
    """ভ্যালিড কুকি ফাইল পাওয়ার ফাংশন"""
    for cookie_file in COOKIE_FILES:
        if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
            return cookie_file
    return None

# --- সুপার ফাস্ট ও হাই-কোয়ালিটি ইমেজ এনহ্যান্সমেন্ট (Ultra Fast HD) ---
def fast_hd_enhance(input_path, output_path):
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError("ছবিটি পড়া সম্ভব হয়নি।")

    # ১. ২x রেজোলিউশন আপস্কেলিং (High quality CUBIC Interpolation)
    h, w = img.shape[:2]
    upscaled = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    # ২. ফাস্ট বাইল্যাটেরাল ফিল্টারিং (নয়েজ রিমুভাল কিন্তু এজ শার্প রাখে)
    denoised = cv2.bilateralFilter(upscaled, d=5, sigmaColor=35, sigmaSpace=35)

    # ৩. অ্যাডাপ্টিভ কালার ও ব্রাইটনেস এনহ্যান্সমেন্ট (CLAHE)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    enhanced_lab = cv2.merge((cl, a, b))
    enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    # ৪. আনশার্প মাস্কিং (ছবি ক্রিস্প ও ক্লিয়ার করার জন্য)
    blur = cv2.GaussianBlur(enhanced_bgr, (0, 0), 2.0)
    sharpened = cv2.addWeighted(enhanced_bgr, 1.4, blur, -0.4, 0)

    # ৯৫% জিপ্যাগ কোয়ালিটিতে আউটপুট সেভ
    cv2.imwrite(output_path, sharpened, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

# --- কমান্ড হ্যান্ডলার ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Multi-Utility Ultra Bot-এ স্বাগতম!**\n\n"
        "📥 **ভিডিও ও অডিও ডাউনলোড করতে লিংক পাঠান:**\n"
        "• YouTube (Videos, Shorts)\n"
        "• Facebook (Reels, Videos)\n"
        "• Instagram (Reels, Posts)\n\n"
        "🖼️ **Fast HD Image Enhancer:**\n"
        "যেকোনো ছবি পাঠালে ১ সেকেন্ডে রেজোলিউশন ২x বাড়িয়ে ফুল HD বানিয়ে দেওয়া হবে।"
    )

# --- অল-ইন-ওয়ান মিডিয়া লিংক হ্যান্ডলার ---
async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    valid_domains = ["youtube.com", "youtu.be", "facebook.com", "fb.watch", "fb.gg", "instagram.com", "instagr.am"]
    
    if not any(domain in url.lower() for domain in valid_domains):
        await update.message.reply_text("❌ এটি সমর্থিত YouTube, Facebook বা Instagram লিংক নয়।")
        return

    context.user_data['url'] = url

    keyboard = [
        [
            InlineKeyboardButton("🎬 Download Video", callback_data='video'),
            InlineKeyboardButton("🎵 Download Audio (MP3)", callback_data='audio')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ফাইল ফরম্যাট নির্বাচন করুন:", reply_markup=reply_markup)

# --- বাটন কলব্যাক ও ডাউনলোড প্রসেস ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('url')
    download_type = query.data

    if not url:
        await query.edit_message_text("❌ সেশন শেষ হয়ে গেছে। আবার লিংক পাঠান।")
        return

    await query.edit_message_text("⏳ ডাউনলোডের কাজ চলছে... অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন।")

    os.makedirs("downloads", exist_ok=True)
    filename_template = f"downloads/{query.from_user.id}_%(id)s.%(ext)s"
    cookie_file = get_valid_cookie()

    # yt-dlp কনফিগারেশন
    ydl_opts = {
        'outtmpl': filename_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 49 * 1024 * 1024,  # টেলিগ্রাম বটের ৫০MB ফাইল লিমিটের কারণে
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    }

    # অডিও ও ভিডিও প্রসেসিং
    if download_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'

    # ইউটিউব লিংক হলে কুকি ও ক্লায়েন্ট ব্যবহার
    if "youtube" in url.lower() or "youtu.be" in url.lower():
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        ydl_opts['extractor_args'] = {'youtube': {'player_client': ['android', 'ios', 'web']}}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        # অডিও কনভার্সন হলে এক্সটেনশন অ্যাডজাস্ট করা
        if download_type == 'audio':
            base, _ = os.path.splitext(downloaded_file)
            if os.path.exists(f"{base}.mp3"):
                downloaded_file = f"{base}.mp3"

        await query.edit_message_text("📤 ফাইল টেলিগ্রামে পাঠানো হচ্ছে...")

        if os.path.exists(downloaded_file):
            title = info.get('title', 'Media File')
            with open(downloaded_file, 'rb') as file_data:
                if download_type == 'audio':
                    await query.message.reply_audio(audio=file_data, title=title)
                else:
                    await query.message.reply_video(video=file_data, caption=title)

            os.remove(downloaded_file)
            await query.delete_message()
        else:
            await query.edit_message_text("❌ ফাইল প্রসেসিং সম্পন্ন হলেও পাওয়া যায়নি।")

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Download Error: {error_msg}")
        if "File is larger than max_filesize" in error_msg:
            await query.edit_message_text("❌ ভিডিওটি ৫০ মেগাবাইটের চেয়ে বড়, তাই টেলিগ্রাম বট এপিআইয়ের সীমাবদ্ধতার কারণে পাঠানো যাচ্ছে না।")
        else:
            await query.edit_message_text(f"❌ ডাউনলোড করতে সমস্যা হয়েছে।\n\nকারণ: {error_msg[:250]}")

# --- ফটো ইনহ্যান্সমেন্ট হ্যান্ডলার ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⚡ ছবিটি প্রসেস ও HD ইনহ্যান্স করা হচ্ছে...")

    photo_file = await update.message.photo[-1].get_file()
    
    os.makedirs("downloads", exist_ok=True)
    input_path = f"downloads/input_{update.message.from_user.id}.jpg"
    output_path = f"downloads/enhanced_{update.message.from_user.id}.jpg"

    await photo_file.download_to_drive(input_path)

    try:
        fast_hd_enhance(input_path, output_path)

        await status_msg.edit_text("📤 ক্লিয়ার করা এইচডি ছবি পাঠানো হচ্ছে...")

        with open(output_path, 'rb') as enhanced_file:
            await update.message.reply_document(
                document=enhanced_file,
                caption="✨ **আপনার ছবি সফলভাবে ২x রেজোলিউশন ও HD কোয়ালিটিতে উন্নত করা হয়েছে!**"
            )

        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা হয়েছে।\n\nকারণ: {str(e)}")

# --- ড্রাইভার প্রোগ্রাম ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_link))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot starting successfully...")
    app.run_polling(drop_pending_updates=True)
