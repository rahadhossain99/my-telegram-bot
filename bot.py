import os
import gc
import glob
import logging
import requests
import numpy as np
import cv2
from PIL import Image
import static_ffmpeg
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# Render-এর 512MB RAM রক্ষা করতে OpenCV থ্রেড লিমিট ১ রাখা হলো
cv2.setNumThreads(1)

# ffmpeg এনভায়রনমেন্ট পাথ নিশ্চিত করা
try:
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"ffmpeg নোটিশ: {e}")

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# বটের কনফিগারেশন
BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"

# ডাউনলোড ডিরেক্টরি না থাকলে তৈরি করবে
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cleanup_memory():
    """মেমোরি (RAM) ও অপ্রয়োজনীয় ফাইল ক্লিনআপের ফাংশন"""
    try:
        for file in glob.glob(f"{DOWNLOAD_DIR}/*"):
            if os.path.exists(file):
                os.remove(file)
    except Exception as e:
        logger.error(f"ক্লিনআপ এরর: {e}")
    finally:
        # পাইথন গারবেজ কালেকশন দিয়ে সাথে সাথেই RAM খালি করা
        gc.collect()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টার্ট কমান্ড হ্যান্ডলার"""
    await update.message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি মাল্টি-ফাংশনাল অল-ইন-ওয়ান বট।\n\n"
        "🎬 **ইউটিউব ডাউনলোড:** যেকোনো YouTube লিংক পাঠাও।\n"
        "🖼️ **ইমেজ প্রসেসিং:** যেকোনো ছবি পাঠাও ফিল্টার করার জন্য।"
    )


async def handle_youtube_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউটিউব ভিডিও ডাউনলোডের মূল লজিক"""
    url = update.message.text.strip()

    if not ("youtube.com" in url or "youtu.be" in url):
        await update.message.reply_text("❌ এটি সঠিক YouTube লিংক নয়! অনুগ্রহ করে সঠিক লিংক পাঠাও।")
        return

    status_msg = await update.message.reply_text("⏳ **ভিডিও প্রসেস করা হচ্ছে...**\nঅনুগ্রহ করে অপেক্ষা করো।")

    file_path = None
    try:
        # Render RAM বাঁচানোর জন্য অপটিমাইজড yt-dlp সেটিংস (সর্বোচ্চ 720p)
        ydl_opts = {
            'format': 'best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            base_name = os.path.splitext(filename)[0]
            if os.path.exists(f"{base_name}.mp4"):
                file_path = f"{base_name}.mp4"
            else:
                file_path = filename

            title = info.get('title', 'YouTube Video')

        # ভিডিও সাইজ চেক (টেলিগ্রামের ফ্রি সীমা: ৫০ MB)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(
                f"⚠️ **ভিডিওটির সাইজ বড় ({file_size_mb:.1f} MB)!**\n"
                "টেলিগ্রাম ফ্রি বটের সীমাবদ্ধতার কারণে ৫০ MB-এর চেয়ে বড় ফাইল পাঠানো যায় না।"
            )
            return

        await status_msg.edit_text("📤 **টেলিগ্রামে ভিডিও আপলোড হচ্ছে...**")

        with open(file_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"🎥 **{title}**\n\n✅ ডাউনলোড সম্পন্ন!"
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"ডাউনলোড এরর: {e}")
        await status_msg.edit_text(f"❌ **ডাউনলোড হতে সমস্যা হয়েছে!**\n\nকারণ: `{str(e)[:150]}`")

    finally:
        cleanup_memory()


async def handle_image_processing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেমোরি সেফ ইমেজ প্রসেসিং (OpenCV, Pillow ও NumPy সহ)"""
    status_msg = await update.message.reply_text("🎨 **ছবি প্রসেস করা হচ্ছে...**")

    input_path = f"{DOWNLOAD_DIR}/input_{update.message.message_id}.jpg"
    output_path = f"{DOWNLOAD_DIR}/output_{update.message.message_id}.jpg"

    try:
        # ছবি ডাউনলোড
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(input_path)

        img = cv2.imread(input_path)
        if img is None:
            await status_msg.edit_text("❌ ছবি রিড করতে ব্যর্থ হয়েছে।")
            return

        # RAM বাঁচানোর জন্য ছবি বড় হলে স্কেলিং করে ছোট করা
        h, w = img.shape[:2]
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # ইমেজ প্রসেসিং (শার্পেনিং ও ফিল্টারিং)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(img, -1, kernel)

        pil_img = Image.fromarray(cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB))
        pil_img.save(output_path, quality=90)

        # প্রসেস করা ছবি ইউজারকে পাঠানো
        with open(output_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="✨ **ছবি প্রসেস করা হয়েছে!** (Sharpened & Enhanced)"
            )

        await status_msg.delete()

        del img, sharpened, pil_img

    except Exception as e:
        logger.error(f"ইমেজ এরর: {e}")
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা: `{str(e)[:100]}`")

    finally:
        cleanup_memory()


def main():
    """বট চালুর প্রধান ফাংশন"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN সেট করা হয়নি!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_download))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image_processing))

    logger.info("বট চালু হচ্ছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
