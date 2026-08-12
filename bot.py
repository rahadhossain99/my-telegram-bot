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

# Render RAM নিয়ন্ত্রণের জন্য OpenCV থ্রেড ১-এ লিমিট করা (মেমোরি স্পাইক রোধ করে)
cv2.setNumThreads(1)

# ffmpeg এনভায়রনমেন্ট পাথ সেটআপ
try:
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"ffmpeg সেটআপে নোটিশ: {e}")

# লগিং কনফিগারেশন
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# এনভায়রনমেন্ট ভ্যারিয়েবল ও কনফিগারেশন
BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"

# ডাউনলোড ডিরেক্টরি নিশ্চিত করা
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cleanup_memory():
    """RAM ও সাময়িক ফাইল পরিষ্কার করার ফাংশন"""
    try:
        for file in glob.glob(f"{DOWNLOAD_DIR}/*"):
            if os.path.exists(file):
                os.remove(file)
    except Exception as e:
        logger.error(f"ফাইল মুছতে সমস্যা: {e}")
    finally:
        # পাইথন গারবেজ কালেকশন কল করে RAM ফ্রী করা
        gc.collect()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টার্ট কমান্ড 핸ডলার"""
    await update.message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি মাল্টি-ফাংশনাল অল-ইন-ওয়ান বট।\n\n"
        "🎬 **ইউটিউব ভিডিও ডাউনলোড:** ইউটিউব ভিডিওর লিংক পাঠাও।\n"
        "🖼️ **ইমেজ প্রসেসিং:** যেকোনো ছবি পাঠাও (ফিল্টার/ইনহ্যান্স করার জন্য)।"
    )


async def handle_youtube_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউটিউব ভিডিও ডাউনলোডের মূল লজিক"""
    url = update.message.text.strip()

    if not ("youtube.com" in url or "youtu.be" in url):
        await update.message.reply_text("❌ এটি সঠিক YouTube লিংক নয়! অনুগ্রহ করে একটি বৈধ লিংক পাঠাও।")
        return

    status_msg = await update.message.reply_text("⏳ **ভিডিও প্রসেস করা হচ্ছে...**\nঅনুগ্রহ করে কিছুটা সময় দাও।")

    file_path = None
    try:
        # Render Free Tier (512MB RAM)-এর জন্য মেমোরি-বান্ধব অপশন
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

        # ফাইলের সাইজ চেক (টেলিগ্রাম বট সীমা ৫০ MB)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(
                f"⚠️ **ভিডিওর সাইজ খুব বড় ({file_size_mb:.1f} MB)!**\n"
                "টেলিগ্রাম ফ্রি বটের সীমাবদ্ধতার কারণে ৫০ MB এর বেশি বড় ফাইল পাঠানো সম্ভব নয়।"
            )
            return

        await status_msg.edit_text("📤 **টেলিগ্রামে ভিডিও আপলোড হচ্ছে...**")

        with open(file_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"🎥 **{title}**\n\n✅ ডাউনলোড সফল হয়েছে!"
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"ডাউনলোড এরর: {e}")
        await status_msg.edit_text(f"❌ **ডাউনলোড করতে ব্যর্থ হয়েছে!**\n\nকারণ: `{str(e)[:150]}`")

    finally:
        cleanup_memory()


async def handle_image_processing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """OpenCV, NumPy ও Pillow দিয়ে মেমোরি-সেফ ইমেজ প্রসেসিং"""
    status_msg = await update.message.reply_text("🎨 **ছবি প্রসেস করা হচ্ছে...**")

    input_path = f"{DOWNLOAD_DIR}/input_{update.message.message_id}.jpg"
    output_path = f"{DOWNLOAD_DIR}/output_{update.message.message_id}.jpg"

    try:
        # বড় সাইজের ছবি টেলিগ্রাম থেকে ডাউনলোড
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(input_path)

        # OpenCV দিয়ে ইমেজ লোড করা
        img = cv2.imread(input_path)

        if img is None:
            await status_msg.edit_text("❌ ছবি লোড করতে ব্যর্থ হয়েছে।")
            return

        # RAM বাঁচানোর জন্য বড় ছবি স্কেল ডাউন (সর্বোচ্চ ১২৮০ পিক্সেল) করা
        h, w = img.shape[:2]
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # ইমেজ প্রসেসিং উদাহরণ (কালার শার্পেনিং ও কন্ট্রাস্ট এনহ্যান্সমেন্ট)
        # ১. গ্রেস্কেল ও শার্পেনিং
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(img, -1, kernel)

        # ২. Pillow ব্যবহার করে রেজাল্ট সেভ
        pil_img = Image.fromarray(cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB))
        pil_img.save(output_path, quality=90)

        # ব্যবহারকারীকে প্রসেস করা ছবি পাঠানো
        with open(output_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="✨ **ছবি সফলভাবে প্রসেস করা হয়েছে!** (Enhanced & Sharpened)"
            )

        await status_msg.delete()

        # ভ্যারিয়েবল ডিলিট করে মেমোরি রিলিজ করা
        del img, sharpened, pil_img

    except Exception as e:
        logger.error(f"ইমেজ প্রসেসিং এরর: {e}")
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা হয়েছে: `{str(e)[:100]}`")

    finally:
        cleanup_memory()


def main():
    """বট শুরুর মূল ফাংশন"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN এনভায়রনমেন্ট ভ্যারিয়েবল পাওয়া যায়নি!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলারসমূহ
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_download))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image_processing))

    logger.info("বট চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
