#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Super Fast Downloader Bot - Dotenv siz versiya
Telegram: @username
"""

import os
import sys
import logging
import uuid
import shutil
import re
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

# Kutubxonalarni tekshirish
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        filters, ContextTypes, CallbackQueryHandler
    )
except ImportError:
    print("❌ python-telegram-bot o'rnatilmagan.")
    print("📦 O'rnatish: pip install python-telegram-bot")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp o'rnatilmagan.")
    print("📦 O'rnatish: pip install yt-dlp")
    sys.exit(1)

# ==================== KONFIGURATSIYA ====================

# TOKENNI TO'G'RIDAN-TO'G'RI KODGA YOZAMIZ (dotenv ishlamasa)
BOT_TOKEN = "7999878066:AAHC-Kqe2rmcL3tutbQtFlzldgwoc9D-Rpc"  # Sizning tokeningiz

# Sozlamalar
MAX_FILE_SIZE = 50  # MB
MAX_VIDEO_DURATION = 600  # 10 daqiqa

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Papkalar
BASE_DIR = Path(__file__).parent
DOWNLOAD_PATH = BASE_DIR / "downloads"
TEMP_PATH = DOWNLOAD_PATH / "temp"
os.makedirs(TEMP_PATH, exist_ok=True)

# Thread pool for parallel downloads
executor = ThreadPoolExecutor(max_workers=4)

# Qo'llab-quvvatlanadigan saytlar
SUPPORTED_SITES: Dict[str, str] = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'instagram.com': 'Instagram',
    'tiktok.com': 'TikTok',
    'facebook.com': 'Facebook',
    'fb.watch': 'Facebook',
    'twitter.com': 'Twitter',
    'x.com': 'Twitter',
    'reddit.com': 'Reddit',
    'vm.tiktok.com': 'TikTok',
    'youtube.com/shorts': 'YouTube Shorts'
}


# ==================== YORDAMCHI FUNKSIYALAR ====================

def clean_filename(filename: str) -> str:
    """Fayl nomini tozalash"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    if len(filename) > 200:
        filename = filename[:200]
    return filename.strip()


def format_size(size_bytes: int) -> str:
    """Baytni o'qiladigan formatga o'tkazish"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_duration(seconds: int) -> str:
    """Sekundni vaqt formatiga o'tkazish"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def is_url(text: str) -> bool:
    """URL ni tekshirish"""
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return bool(url_pattern.match(text))


def get_site_name(url: str) -> str:
    """Sayt nomini qaytarish"""
    url_lower = url.lower()
    for domain, name in SUPPORTED_SITES.items():
        if domain in url_lower:
            return name
    return "Noma'lum sayt"


# ==================== YT-DLP SOZLAMALARI ====================

def get_ydl_opts(media_type: str = 'video', output_path: Optional[Path] = None) -> Dict[str, Any]:
    """yt-dlp sozlamalarini qaytarish"""

    base_opts: Dict[str, Any] = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'retries': 3,
        'fragment_retries': 3,
        'skip_unavailable_fragments': True,
        'socket_timeout': 30,
    }

    if output_path:
        base_opts['outtmpl'] = str(output_path / '%(title)s.%(ext)s')

    if media_type == 'video':
        base_opts.update({
            'format': 'best[height<=720][ext=mp4]/best[height<=480][ext=mp4]',
            'merge_output_format': 'mp4',
            'prefer_ffmpeg': True,
        })
    elif media_type == 'audio':
        base_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    elif media_type == 'search':
        base_opts.update({
            'extract_flat': True,
            'default_search': 'ytsearch10:',
            'playlistend': 10,
        })

    return base_opts


# ==================== YUKLASH FUNKSIYALARI ====================

async def download_media(url: str, media_type: str, file_id: str) -> Optional[Path]:
    """Mediani yuklash"""

    download_folder = TEMP_PATH / file_id
    os.makedirs(download_folder, exist_ok=True)

    ydl_opts = get_ydl_opts(media_type, download_folder)

    try:
        loop = asyncio.get_event_loop()

        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # Ma'lumot olish
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return None

                    # Hajm va davomiylikni tekshirish
                    if media_type == 'video':
                        duration = info.get('duration', 0)
                        if duration > MAX_VIDEO_DURATION:
                            logger.warning(f"Video juda uzun: {duration} sekund")
                            return None

                    # Yuklash
                    ydl.extract_info(url, download=True)

                    # Yuklangan faylni topish
                    if media_type == 'audio':
                        files = list(download_folder.glob('*.mp3'))
                    else:
                        files = list(download_folder.glob('*.mp4'))

                    return files[0] if files else None

                except Exception as e:
                    logger.error(f"Yuklash xatoligi: {e}")
                    return None

        return await loop.run_in_executor(executor, download_sync)

    except Exception as e:
        logger.error(f"Download media xatoligi: {e}")
        return None


async def search_audio(query: str) -> List[Dict[str, str]]:
    """Qo'shiq nomi bo'yicha qidirish"""
    try:
        ydl_opts = get_ydl_opts('search')

        loop = asyncio.get_event_loop()

        def search_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch10:{query}", download=False)

                    results = []
                    if info and 'entries' in info:
                        for entry in info['entries']:
                            if entry and entry.get('id'):
                                duration = entry.get('duration', 0)

                                results.append({
                                    'id': entry.get('id', ''),
                                    'title': entry.get('title', 'Unknown')[:100],
                                    'duration': format_duration(duration),
                                    'uploader': entry.get('uploader', 'Unknown')[:30],
                                    'url': f"https://youtube.com/watch?v={entry.get('id', '')}"
                                })
                    return results[:8]
                except Exception as e:
                    logger.error(f"Qidiruv xatoligi: {e}")
                    return []

        return await loop.run_in_executor(executor, search_sync)

    except Exception as e:
        logger.error(f"Search audio xatoligi: {e}")
        return []


# ==================== HANDLERLAR ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start komandasi"""
    user = update.effective_user
    first_name = user.first_name if user else "Foydalanuvchi"

    welcome_text = f"""
🎵 **Assalomu alaykum {first_name}!**

Men **Super Fast Downloader Bot**!

📥 **Ishlatish usullari:**

1️⃣ **VIDEO YUKLASH**
   • Video linkini yuboring
   • 720p gacha sifatda yuklayman
   • Video tagidagi "🎵 Audio" orqali musiqa oling

2️⃣ **AUDIO QIDIRISH**
   • Qo'shiq nomini yozing
   • Topilgan qo'shiqlardan birini tanlang

⚡ **Imkoniyatlar:**
• {MAX_FILE_SIZE}MB gacha video/audio
• {MAX_VIDEO_DURATION // 60} daqiqagacha video

🔍 **Hozir sinab ko'ring:**
• YouTube linki yuboring
• Yoki qo'shiq nomi yozing
    """

    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help komandasi"""
    help_text = f"""
📚 **Yordam:**

🎬 **Video yuklash:**
• Qo'llab-quvvatlanadigan saytlar:
  {', '.join(set(SUPPORTED_SITES.values()))}
• Video linkini yuboring
• Avtomatik yuklanadi

🎵 **Audio qidirish:**
• Qo'shiq nomini yozing
• 8 ta natija ko'rsatiladi
• Birini tanlang

⚙️ **Cheklovlar:**
• Hajm: {MAX_FILE_SIZE}MB dan kichik
• Davomiylik: {MAX_VIDEO_DURATION // 60} daqiqagacha

❌ **Muammo bo'lsa:**
• @BotFather
• /start - qayta ishga tushirish
    """

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha xabarlarni qabul qilish"""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if is_url(text):
        site_name = get_site_name(text)

        if site_name == "Noma'lum sayt":
            supported = ', '.join(set(SUPPORTED_SITES.values()))
            await update.message.reply_text(
                f"❌ Bu sayt qo'llab-quvvatlanmaydi.\n"
                f"✅ Qo'llab-quvvatlanadigan saytlar:\n{supported}"
            )
            return

        await download_video_handler(update, context, text, site_name)
    else:
        await search_handler(update, context, text)


async def download_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                 url: str, site_name: str) -> None:
    """Video yuklash handler"""

    status_msg = await update.message.reply_text(
        f"⏳ **{site_name}** dan video yuklanmoqda...",
        parse_mode='Markdown'
    )

    file_id = f"video_{uuid.uuid4().hex[:8]}"

    try:
        video_path = await download_media(url, 'video', file_id)

        if not video_path or not video_path.exists():
            await status_msg.edit_text(
                "❌ Video yuklanmadi.\n"
                f"• Video juda uzun (>{MAX_VIDEO_DURATION // 60} daqiqa)\n"
                "• Video topilmadi\n"
                "• Link noto'g'ri"
            )
            return

        file_size_mb = video_path.stat().st_size / (1024 * 1024)

        if file_size_mb > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Video hajmi {file_size_mb:.1f}MB\n"
                f"Limit: {MAX_FILE_SIZE}MB"
            )
            video_path.unlink(missing_ok=True)
            return

        keyboard = [[
            InlineKeyboardButton(
                "🎵 Audiosini yuklab olish",
                callback_data=f"audio|{url}|{video_path.stem}"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            f"📤 Telegramga yuklanmoqda...\n"
            f"📊 Hajm: {file_size_mb:.1f}MB"
        )

        with open(video_path, 'rb') as f:
            await update.message.reply_video(
                video=f,
                caption=f"✅ **Video tayyor!**\n\n"
                        f"📹 {video_path.stem[:100]}\n"
                        f"📊 {file_size_mb:.1f}MB\n"
                        f"🌐 {site_name}",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                read_timeout=60,
                write_timeout=60
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Video yuklash xatoligi: {e}")
        await status_msg.edit_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    finally:
        shutil.rmtree(TEMP_PATH / file_id, ignore_errors=True)


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Qidiruv handler"""

    status_msg = await update.message.reply_text(f"🔍 **{query}** bo'yicha qidirilmoqda...")

    results = await search_audio(query)

    if not results:
        await status_msg.edit_text(
            f"❌ **{query}** bo'yicha hech narsa topilmadi.\n"
            f"Boshqa so'z bilan urinib ko'ring."
        )
        return

    keyboard = []
    for i, result in enumerate(results, 1):
        button_text = f"{i}. {result['title'][:35]}... | {result['duration']}"
        callback_data = f"select|{result['url']}|{result['title']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await status_msg.edit_text(
        f"🔍 **{query}** bo'yicha {len(results)} ta natija:\n\n"
        f"🎵 Kerakli qo'shiqni tanlang:",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tugmalarni boshqarish"""
    query = update.callback_query
    await query.answer()

    if not query.data:
        return

    if query.data == "cancel":
        await query.edit_message_text("❌ Bekor qilindi")
        return

    parts = query.data.split('|')
    action = parts[0]

    if action == "select" and len(parts) >= 3:
        url = parts[1]
        title = parts[2]

        await query.edit_message_text(f"⏳ **{title[:50]}...** yuklanmoqda...")

        file_id = f"audio_{uuid.uuid4().hex[:8]}"
        audio_path = await download_media(url, 'audio', file_id)

        if audio_path and audio_path.exists():
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)

            if file_size_mb > MAX_FILE_SIZE:
                await query.message.reply_text(
                    f"❌ Audio hajmi {file_size_mb:.1f}MB\n"
                    f"Limit: {MAX_FILE_SIZE}MB"
                )
            else:
                with open(audio_path, 'rb') as f:
                    await query.message.reply_audio(
                        audio=f,
                        title=title[:100],
                        performer="YouTube",
                        caption=f"✅ **Audio tayyor!**\n📊 {file_size_mb:.1f}MB",
                        read_timeout=60,
                        write_timeout=60
                    )
                await query.message.delete()

            shutil.rmtree(TEMP_PATH / file_id, ignore_errors=True)
        else:
            await query.message.reply_text("❌ Audio yuklanmadi")

    elif action == "audio" and len(parts) >= 3:
        url = parts[1]
        title = parts[2]

        status_msg = await query.message.reply_text(f"⏳ **Video audiosi yuklanmoqda...**")

        file_id = f"audio_{uuid.uuid4().hex[:8]}"
        audio_path = await download_media(url, 'audio', file_id)

        if audio_path and audio_path.exists():
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)

            with open(audio_path, 'rb') as f:
                await query.message.reply_audio(
                    audio=f,
                    title=title[:100],
                    performer="Video audiosi",
                    caption=f"✅ **Video audiosi tayyor!**\n📊 {file_size_mb:.1f}MB"
                )

            await status_msg.delete()
            shutil.rmtree(TEMP_PATH / file_id, ignore_errors=True)
        else:
            await status_msg.edit_text("❌ Audio yuklanmadi")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global xatolarni ushlash"""
    logger.error(f"Xatolik yuz berdi: {context.error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Texnik xatolik yuz berdi.\n"
            "Iltimos, keyinroq urinib ko'ring."
        )


# ==================== ASOSIY FUNKSIYA ====================

def main() -> None:
    """Botni ishga tushirish"""

    print("=" * 60)
    print("🚀 SUPER FAST DOWNLOADER BOT")
    print("=" * 60)
    print(f"📁 Yuklash papkasi: {DOWNLOAD_PATH}")
    print(f"📊 Maksimal hajm: {MAX_FILE_SIZE}MB")
    print(f"⏱ Maksimal davomiylik: {MAX_VIDEO_DURATION // 60} daqiqa")
    print(f"🤖 Bot token: {BOT_TOKEN[:10]}... (qisqartirilgan)")
    print("=" * 60)

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_error_handler(error_handler)

        print("\n✅ Bot ishga tushdi!")
        print("📱 Telegramda @testing uchun yozing...")
        print("\n⏸ To'xtatish uchun Ctrl+C bosing")
        print("=" * 60)

        application.run_polling(allowed_updates=['message', 'callback_query'])

    except KeyboardInterrupt:
        print("\n\n👋 Bot to'xtatildi")
    except Exception as e:
        print(f"\n❌ Xatolik: {e}")
        logger.error(f"Bot ishga tushmadi: {e}")
    finally:
        executor.shutdown(wait=False)


if __name__ == '__main__':
    main()