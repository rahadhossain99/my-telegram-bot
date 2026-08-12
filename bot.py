import os
import random
import logging
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('BOT_TOKEN')
COOKIE_FILES = ['cookie1.txt']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Multi-Utility Bot-এ স্বাগতম!**\n\n"
        "📹 **ভিডিও ডাউনলোড:** যেকোনো YouTube, Facebook, বা Instagram ভিডিও/Reels-এর লিংক পাঠান।\n"
        "🖼️ **Image Enhance:** যেকোনো ঝাপসা বা সাধারণ ছবি পাঠালে সেটি অটোমেটিক ক্লিয়ার ও এইচডি (HD) কোয়ালিটি বানিয়ে দেওয়া হবে।"
    )

# --- ইমেজ প্রসেসিং ও কোয়ালিটি ইনহ্যান্স ফাংশন ---
def enhance_image(input_path, output_path):
    # ১. OpenCV দিয়ে ছবি লোড করা
    img = cv2.imread(input_path)
    
    # ২. ছবির রেজোলিউশন দ্বিগুণ (2x Up-scaling) করা
    height, width = img.shape[:2]
    img_resized = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
    
    # ৩. ডেনয়েজিং (Denoising - ঝাপসা কমানো)
    denoised = cv2.fastNlMeansDenoisingColored(img_resized, None, 10, 10, 7, 21)
    
    # ৪. শার্পনিং (Sharpening Filter)
    kernel = np.array([[0, -1, 0], 
                       [-1, 5,-1], 
                       [0, -1, 0]])
    sharpened = cv2.filter2D(denoised, -1, kernel)
    
    # BGR to RGB তে রূপান্তর করা Pillow এর জন্য
    sharpened_rgb = cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(sharpened_rgb)
    
    # ৫. কন্ট্রাস্ট এবং কালার অটো এনহ্যান্সমেন্ট
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.2)
    
    enhancer_sharpness = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharpness.enhance(1.3)
    
    enhancer_color = ImageEnhance.Color(pil_img)
    pil_img = enhancer_color.enhance(1.1)
    
    # আউটপুট ছবি সেভ করা
    pil_img.save(output_path, quality=95)

# --- লিংক হ্যান্ডলার (YouTube, Facebook, Instagram) ---
async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # সাপোর্ট করা লিংক চেক
    valid_platforms = ["youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com"]
    if not any(domain in url for domain in valid_platforms):
        await update.message.reply_text("❌ এটি সঠিক YouTube, Facebook বা Instagram লিংক নয়।")
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

# --- বাটন কলব্যাক হ্যান্ডলার ---
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
    selected_cookie = random.choice(COOKIE_FILES) if os.path.exists(COOKIE_FILES[0]) else None

    ydl_opts = {
        'format': 'best',
        'outtmpl': output_filename,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    # ইউটিউবের ক্ষেত্রে কুকি ও ক্লায়েন্ট কনফিগ
    if "youtube" in url or "youtu.be" in url:
        if selected_cookie:
            ydl_opts['cookiefile'] = selected_cookie
        ydl_opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}

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

# --- ফটো এনহ্যান্সমেন্ট হ্যান্ডলার ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⚡ ছবিটি ডাউনলোড ও এইচডি এনহ্যান্স করা হচ্ছে, একটু অপেক্ষা করুন...")

    # ইউজার থেকে উচ্চ রেজোলিউশনের ছবি নেওয়া
    photo_file = await update.message.photo[-1].get_file()
    input_path = "input_image.jpg"
    output_path = "enhanced_image.jpg"

    await photo_file.download_to_drive(input_path)

    try:
        # ইমেজ প্রসেসিং রান করা
        enhance_image(input_path, output_path)

        await status_msg.edit_text("📤 ক্লিয়ার করা ছবি পাঠানো হচ্ছে...")

        # এনহ্যান্স করা ছবি ডকুমেন্ট হিসেবে (ফুল কোয়ালিটি বজায় রাখার জন্য) এবং ফটো হিসেবে পাঠানো
        with open(output_path, 'rb') as enhanced_file:
            await update.message.reply_document(
                document=enhanced_file, 
                caption="✨ আপনার ছবির রেজোলিউশন ও কোয়ালিটি ইনহ্যান্স করা হয়েছে!"
            )

        # আবর্জনা ফাইল ডিলিট
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা হয়েছে।\n\nকারণ: {str(e)}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_link))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot starting...")
    app.run_polling(drop_pending_updates=True)
