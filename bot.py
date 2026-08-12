import os
import random
import logging
import cv2
import numpy as np
from PIL import Image, ImageEnhance
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

# লগিং কনফিগারেশন
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')
COOKIE_FILES = ['cookie1.txt']

def get_valid_cookie():
    """ভ্যালিড কুকি ফাইল খুঁজে বের করার ফাংশন"""
    for cookie_file in COOKIE_FILES:
        if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
            return cookie_file
    return None

# --- সুপার ফাস্ট ও হাই-কোয়ালিটি ইমেজ এনহ্যান্সমেন্ট ---
def process_hd_image(input_path, output_path):
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError("ছবিটি সঠিকভাবে পড়া সম্ভব হয়নি।")

    # ১. রেজোলিউশন ২ গুণ বাড়ানো (CUBIC Interpolation)
    height, width = img.shape[:2]
    upscaled = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)

    # ২. আল্ট্রা ফাস্ট আনশার্প মাস্কিং (Unsharp Masking for Sharpness)
    gaussian = cv2.GaussianBlur(upscaled, (0, 0), 3)
    sharpened = cv2.addWeighted(upscaled, 1.6, gaussian, -0.6, 0)

    # ৩. অ্যাডাপ্টিভ কালার ও কন্ট্রাস্ট এনহ্যান্সমেন্ট (CLAHE)
    lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    final_bgr = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

    # হাই-কোয়ালিটি জিপ্যাগ ফাইলে সেভ করা
    cv2.imwrite(output_path, final_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

# --- স্টার্ট কমান্ড ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Advanced All-in-One Downloader & Enhancer Bot!**\n\n"
        "📥 **ভিডিও ও অডিও ডাউনলোড করতে লিংক পাঠান:**\n"
        "• YouTube (Videos, Shorts)\n"
        "• Facebook (Reels, Videos)\n"
        "• Instagram (Reels, Posts)\n\n"
        "🖼️ **Image Enhancer:**\n"
        "যেকোনো সাধারণ বা ঝাপসা ছবি পাঠালে ১ সেকেন্ডেই তার রেজোলিউশন ২x বাড়িয়ে ফুল HD বানিয়ে দেওয়া হবে।"
    )

# --- অল-ইন-ওয়ান সোশ্যাল মিডিয়া লিংক হ্যান্ডলার ---
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
    await update.message.reply_text("ফাইল ফরম্যাট বেছে নিন:", reply_markup=reply_markup)

# --- ভিডিও ও অডিও ডাউনলোড বাটনের কার্যক্রম ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('url')
    download_type = query.data

    if not url:
        await query.edit_message_text("❌ সেশন শেষ হয়ে গেছে। আবার লিংকটি পাঠান।")
        return

    await query.edit_message_text("⏳ ডাউনলোডের কাজ চলছে... অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন।")

    os.makedirs("downloads", exist_ok=True)
    filename_template = f"downloads/{query.from_user.id}_%(id)s.%(ext)s"

    cookie_file = get_valid_cookie()

    # ফরম্যাট ফিল্টার (FFmpeg ছাড়া নিশ্চিত ডাউনলোডের জন্য ফলব্যাক রুলস)
    if download_type == 'audio':
        # অডিও আলাদা না পেলে ভিডিও থেকেই সরাসরি ফাইলটি নামিয়ে টেলিগ্রামে অডিও আকারে পাঠাবে
        format_rule = 'bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best'
    else:
        # প্রি-মার্জড সিঙ্গল MP4 ফাইল পছন্দ করবে যেন FFmpeg ছাড়াই নিখুঁত ভিডিও পাওয়া যায়
        format_rule = 'best[ext=mp4]/bestvideo+bestaudio/best'

    ydl_opts = {
        'format': format_rule,
        'outtmpl': filename_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    }

    # ইউটিউব হলে কুকি এবং প্লেয়ার ক্লায়েন্ট যুক্ত করা
    if "youtube" in url.lower() or "youtu.be" in url.lower():
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        ydl_opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        await query.edit_message_text("📤 ফাইল টেলিগ্রামে পাঠানো হচ্ছে...")

        if os.path.exists(downloaded_file):
            title = info.get('title', 'Media')
            with open(downloaded_file, 'rb') as file_data:
                if download_type == 'audio':
                    await query.message.reply_audio(audio=file_data, title=title)
                else:
                    await query.message.reply_video(video=file_data, caption=title)

            # প্রসেস শেষে ফাইল ডিলিট
            os.remove(downloaded_file)
            await query.delete_message()
        else:
            await query.edit_message_text("❌ ফাইলটি খুঁজে পাওয়া যায়নি।")

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Download Error: {error_msg}")
        await query.edit_message_text(f"❌ ডাউনলোড করতে সমস্যা হয়েছে।\n\nকারণ: {error_msg[:200]}")

# --- সুপার-ফাস্ট ফটো ইনহ্যান্সমেন্ট হ্যান্ডলার ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⚡ ছবিটি প্রসেস করা হচ্ছে (Fast HD Enhancement)...")

    photo_file = await update.message.photo[-1].get_file()
    
    os.makedirs("downloads", exist_ok=True)
    input_path = f"downloads/input_{update.message.from_user.id}.jpg"
    output_path = f"downloads/enhanced_{update.message.from_user.id}.jpg"

    await photo_file.download_to_drive(input_path)

    try:
        # ইমেজ প্রসেস কল করা
        process_hd_image(input_path, output_path)

        await status_msg.edit_text("📤 এইচডি (HD) ছবি তৈরি হয়েছে, পাঠানো হচ্ছে...")

        with open(output_path, 'rb') as enhanced_file:
            await update.message.reply_document(
                document=enhanced_file,
                caption="✨ **আপনার ছবি সফলভাবে ২x রেজোলিউশন ও HD কোয়ালিটিতে উন্নত করা হয়েছে!**"
            )

        # ক্লিয়ারআপ
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা হয়েছে।\n\nকারণ: {str(e)}")

# --- প্রধান বট ড্রাইভার ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_link))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot starting successfully...")
    app.run_polling(drop_pending_updates=True)
