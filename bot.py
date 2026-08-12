import os
import glob
import gc
import logging
import re
import requests
import numpy as np
import cv2
from PIL import Image
import static_ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import yt_dlp

# Render-এর 512MB RAM রক্ষা করতে OpenCV থ্রেড লিমিট ১ রাখা হলো
cv2.setNumThreads(1)

# ffmpeg এনভায়রনমেন্ট পাথ নিশ্চিত করা
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
COOKIES_FILE = "cookies.txt"

# যদি Environment Variable-এ Cookies থাকে, তবে cookies.txt তৈরি করা
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")
if YOUTUBE_COOKIES and not os.path.exists(COOKIES_FILE):
    with open(COOKIES_FILE, "w") as f:
        f.write(YOUTUBE_COOKIES)

# ডাউনলোড ডিরেক্টরি না থাকলে তৈরি করা
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cleanup_memory():
    """মেমোরি (RAM) ও অপ্রয়োজনীয় ফাইল ক্লিনআপের ফাংশন"""
    try:
        for file in glob.glob(f"{DOWNLOAD_DIR}/*"):
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"ক্লিনআপ এরর: {e}")
    finally:
        gc.collect()


def is_terabox_url(url: str) -> bool:
    """টেরাবক্সের সমস্ত ডোমেইন ও অল্টারনেটিভ লিংক শনাক্ত করার ফাংশন"""
    terabox_keywords = [
        'terabox', '1024tera', 'freeterabox', 'mirrobox', 
        'neptunebox', 'momerybox', 'terasharefile', 'tibbox', 
        'teraboxlink', '4shared'
    ]
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in terabox_keywords)


def get_terabox_download_link(url: str):
    """TeraBox API থেকে ভিডিওর ডিরেক্ট ডাউনলোড লিংক বের করার ফাংশন"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }

    # শর্ট কোড বের করা (যেমন: terasharefile.com/s/1Q41XDdeAOQZJqDiWMBqq6A)
    match = re.search(r'/(?:s/|surl=)?([a-zA-Z0-9_-]+)', url)
    shortcode = match.group(1) if match else url.split('/')[-1]

    # Multiple Fallback APIs for TeraBox
    api_endpoints = [
        f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={shortcode}",
        f"https://terabox.videodownloader.workers.dev/?url={url}",
        f"https://api.freeterabox.com/api/get-info?url={url}"
    ]

    for endpoint in api_endpoints:
        try:
            res = requests.get(endpoint, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if "downloadLink" in data and data["downloadLink"]:
                    return data["downloadLink"], data.get("fileName", "Terabox_Video.mp4")
                elif "url" in data and data["url"]:
                    return data["url"], data.get("title", "Terabox_Video.mp4")
                elif "list" in data and len(data["list"]) > 0:
                    item = data["list"][0]
                    return item.get("dlink"), item.get("filename", "Terabox_Video.mp4")
        except Exception as e:
            logger.warning(f"TeraBox API Error ({endpoint}): {e}")
            continue

    return None, None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টার্ট কমান্ড হ্যান্ডলার"""
    keyboard = [
        [
            InlineKeyboardButton("🌐 যেকোনো লিংক পাঠাও", callback_data="help_link"),
            InlineKeyboardButton("🖼️ ছবি ফিল্টার", callback_data="help_img")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি অল-ইন-ওয়ান মিডিয়া ডাউনলোডার বট।\n\n"
        "🎬 **সমর্থিত প্ল্যাটফর্ম:** YouTube, TeraBox (terasharefile), Facebook, Instagram, TikTok ইত্যাদি।\n"
        "🖼️ **ছবি প্রসেসিং:** যেকোনো ছবি পাঠাও এনহ্যান্স করার জন্য।",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার লিংক পাঠালে অপশন দেখানোর ফাংশন"""
    url = update.message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ এটি সঠিক কোনো লিংক নয়! অনুগ্রহ করে সঠিক URL পাঠাও।")
        return

    msg_id = str(update.message.message_id)
    context.user_data[msg_id] = url

    # TeraBox ডিটেক্ট করা
    if is_terabox_url(url):
        keyboard = [
            [
                InlineKeyboardButton("📦 TeraBox ভিডিও ডাউনলোড", callback_data=f"dl|terabox|{msg_id}")
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("🎬 ভিডিও (MP4)", callback_data=f"dl|video|{msg_id}"),
                InlineKeyboardButton("🎵 অডিও (MP3)", callback_data=f"dl|audio|{msg_id}"),
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📥 **তুমি কোনটি ডাউনলোড করতে চাও?**\nনিচের বাটন থেকে নির্বাচন করো:",
        reply_markup=reply_markup,
        reply_to_message_id=update.message.message_id,
        parse_mode="Markdown"
    )


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাটনে ক্লিক করলে ডাউনলোডার এক্সিকিউট হবে"""
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]

    if action == "help_link":
        await query.message.reply_text("💡 আমাকে YouTube বা TeraBox-এর ভিডিও লিংক পাঠাও, আমি ডাউনলোড করে দেব।")
        return
    elif action == "help_img":
        await query.message.reply_text("💡 আমাকে যেকোনো ছবি পাঠাও, আমি শার্পেন ও কালার এনহ্যান্স করে দেব।")
        return

    if action != "dl":
        return

    format_type = data[1]  # 'video', 'audio', or 'terabox'
    msg_id = data[2]
    url = context.user_data.get(msg_id)

    if not url:
        await query.edit_message_text("❌ লিংকের মেয়াদ শেষ হয়ে গেছে। অনুগ্রহ করে লিংকটি পুনরায় পাঠাও।")
        return

    await query.edit_message_text(f"⏳ **{format_type.upper()} প্রসেস করা হচ্ছে...**\nঅনুগ্রহ করে কিছুক্ষণ অপেক্ষা করো।", parse_mode="Markdown")

    file_path = None
    try:
        # TeraBox ডাউনলোড লজিক
        if format_type == "terabox":
            direct_link, file_name = get_terabox_download_link(url)
            if not direct_link:
                await query.edit_message_text("❌ TeraBox লিংকটি থেকে ভিডিও এক্সট্র্যাক্ট করা সম্ভব হয়নি। ফাইলটি প্রাইভেট হতে পারে অথবা মেয়াদ শেষ হয়ে গেছে।")
                return

            file_path = os.path.join(DOWNLOAD_DIR, file_name or "terabox_video.mp4")
            
            # স্ট্রিম ডাউনলোড (র‍্যাম বাঁচানোর জন্য চাঙ্ক আকারে)
            with requests.get(direct_link, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            title = file_name or "TeraBox Video"

        # YouTube এবং অন্যান্য ভিডিও ডাউনলোড লজিক
        else:
            ydl_opts = {
                'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'mweb', 'web'],
                    }
                },
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best',
                'merge_output_format': 'mp4',
            }

            if os.path.exists(COOKIES_FILE):
                ydl_opts['cookiefile'] = COOKIES_FILE

            if format_type == 'audio':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception("ভিডিওর তথ্য পাওয়া যায়নি। লিংকটি ভুল হতে পারে।")

                filename = ydl.prepare_filename(info)
                base_name = os.path.splitext(filename)[0]

                if format_type == 'audio':
                    file_path = f"{base_name}.mp3"
                else:
                    file_path = f"{base_name}.mp4"
                    if not os.path.exists(file_path):
                        possible_files = glob.glob(f"{base_name}.*")
                        if possible_files:
                            file_path = possible_files[0]

                title = info.get('title', 'Downloaded Media')

        if not file_path or not os.path.exists(file_path):
            await query.edit_message_text("❌ ফাইল ডাউনলোড করতে ব্যর্থ হয়েছে।")
            return

        # ৫০ MB চেক (টেলিগ্রাম ফ্রি লিমিট)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            await query.edit_message_text(
                f"⚠️ **ফাইলের সাইজ অনেক বড় ({file_size_mb:.1f} MB)!**\n\n"
                "টেলিগ্রাম ফ্রি বটের সীমাবদ্ধতার কারণে ৫০ MB-এর চেয়ে বড় ফাইল সরাসরি পাঠানো যায় না।",
                parse_mode="Markdown"
            )
            return

        await query.edit_message_text("📤 **টেলিগ্রামে আপলোড হচ্ছে...**", parse_mode="Markdown")

        with open(file_path, 'rb') as media_file:
            if format_type == 'audio':
                await query.message.reply_audio(
                    audio=media_file,
                    caption=f"🎵 **{title}**\n\n✅ ডাউনলোড সম্পন্ন!",
                    parse_mode="Markdown"
                )
            else:
                await query.message.reply_video(
                    video=media_file,
                    caption=f"🎥 **{title}**\n\n✅ ডাউনলোড সম্পন্ন!",
                    parse_mode="Markdown"
                )

        await query.delete_message()

    except Exception as e:
        logger.error(f"ডাউনলোড এরর: {e}")
        error_msg = str(e)
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            await query.edit_message_text(
                "❌ **YouTube সিকিউরিটি ব্লক করেছে!**\n\n"
                "বটটি কুকিজ আপডেট করতে বলছে। অনুগ্রহ করে আপনার `cookies.txt` ফাইলটি রিনিউ করুন।"
            )
        else:
            await query.edit_message_text(f"❌ **ডাউনলোডে সমস্যা হয়েছে!**\n\nকারণ: `{error_msg[:150]}`", parse_mode="Markdown")

    finally:
        cleanup_memory()


async def handle_image_processing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইমেজ প্রসেস করার ফাংশন"""
    status_msg = await update.message.reply_text("🎨 **ছবি প্রসেস করা হচ্ছে...**", parse_mode="Markdown")

    input_path = f"{DOWNLOAD_DIR}/input_{update.message.message_id}.jpg"
    output_path = f"{DOWNLOAD_DIR}/output_{update.message.message_id}.jpg"

    try:
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(input_path)

        img = cv2.imread(input_path)
        if img is None:
            await status_msg.edit_text("❌ ছবি পড়া সম্ভব হয়নি।")
            return

        h, w = img.shape[:2]
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(img, -1, kernel)

        pil_img = Image.fromarray(cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB))
        pil_img.save(output_path, quality=90)

        with open(output_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="✨ **ছবি প্রসেস সম্পন্ন!** (Sharpened & Enhanced)",
                parse_mode="Markdown"
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"ইমেজ এরর: {e}")
        await status_msg.edit_text(f"❌ ছবি প্রসেস করতে সমস্যা: `{str(e)[:100]}`", parse_mode="Markdown")

    finally:
        cleanup_memory()


def main():
    """প্রধান রানার ফাংশন"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN সেট করা হয়নি!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলারসমূহ
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image_processing))

    logger.info("বট চালু হচ্ছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
