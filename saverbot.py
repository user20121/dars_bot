"""
Super Fast Downloader Bot - To'liq ishlaydigan versiya
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

# Telegram kutubxonasi
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        filters, ContextTypes, CallbackQueryHandler
    )
    print("✅ Telegram kutubxonasi yuklandi")
except ImportError as e:
    print(f"❌ Telegram kutubxonasi xatosi: {e}")
    print("📦 O'rnatish: pip install python-telegram-bot==20.7")
    sys.exit(1)

# yt-dlp
try:
    import yt_dlp
    print("✅ yt-dlp yuklandi")
except ImportError as e:
    print(f"❌ yt-dlp xatosi: {e}")
    print("📦 O'rnatish: pip install yt-dlp")
    sys.exit(1)

# ==================== KONFIGURATSIYA ====================

# TOKEN - o'zingizning tokeningizni qo'ying
BOT_TOKEN = "8573877333:AAHK3tsbA42TA3KGadeUbdqDXVnIKtF6q8g"

# Sozlamalar
MAX_FILE_SIZE = 50  # MB
MAX_VIDEO_DURATION = 600  # 10 daqiqa

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Papkalar
BASE_DIR = Path(__file__).parent
DOWNLOAD_PATH = BASE_DIR / "downloads"
TEMP_PATH = DOWNLOAD_PATH / "temp"
DOWNLOAD_PATH.mkdir(exist_ok=True)
TEMP_PATH.mkdir(exist_ok=True)

# Qo'llab-quvvatlanadigan saytlar
SUPPORTED_SITES = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'instagram.com': 'Instagram',
    'tiktok.com': 'TikTok',
    'facebook.com': 'Facebook',
    'twitter.com': 'Twitter',
    'x.com': 'Twitter',
}


def is_url(text: str) -> bool:
    """URL tekshirish"""
    return text.startswith(('http://', 'https://'))


def get_site_name(url: str) -> str:
    """Sayt nomi"""
    for domain, name in SUPPORTED_SITES.items():
        if domain in url.lower():
            return name
    return "Noma'lum"


def format_size(bytes: int) -> str:
    """Hajm format"""
    mb = bytes / (1024 * 1024)
    return f"{mb:.1f}MB"


async def download_video(url: str, file_id: str) -> Optional[Path]:
    """Video yuklash"""
    download_folder = TEMP_PATH / file_id
    download_folder.mkdir(exist_ok=True)
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best[height<=720][ext=mp4]/best',
        'outtmpl': str(download_folder / '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                files = list(download_folder.glob('*.mp4'))
                return files[0] if files else None
        
        return await loop.run_in_executor(None, download)
    except Exception as e:
        logger.error(f"Video yuklash xatosi: {e}")
        return None


async def download_audio(url: str, file_id: str) -> Optional[Path]:
    """Audio yuklash"""
    download_folder = TEMP_PATH / file_id
    download_folder.mkdir(exist_ok=True)
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'outtmpl': str(download_folder / '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                files = list(download_folder.glob('*.mp3'))
                return files[0] if files else None
        
        return await loop.run_in_executor(None, download)
    except Exception as e:
        logger.error(f"Audio yuklash xatosi: {e}")
        return None


async def search_audio(query: str) -> List[Dict]:
    """Audio qidirish"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': f'ytsearch8:{query}',
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        def search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                results = []
                
                if info and 'entries' in info:
                    for entry in info['entries'][:8]:
                        if entry:
                            duration = entry.get('duration', 0)
                            minutes = duration // 60
                            seconds = duration % 60
                            
                            results.append({
                                'title': entry.get('title', 'Unknown')[:50],
                                'duration': f"{minutes}:{seconds:02d}",
                                'url': f"https://youtube.com/watch?v={entry.get('id', '')}",
                                'uploader': entry.get('uploader', 'Unknown')[:20]
                            })
                return results
        
        return await loop.run_in_executor(None, search)
    except Exception as e:
        logger.error(f"Qidiruv xatosi: {e}")
        return []


# ==================== HANDLERLAR ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komandasi"""
    await update.message.reply_text(
        f"🎵 **Assalomu alaykum!**\n\n"
        f"📥 **Ishlatish:**\n"
        f"• Video link yuboring\n"
        f"• Qo'shiq nomi yozing\n\n"
        f"⚡ **Imkoniyatlar:**\n"
        f"• {MAX_FILE_SIZE}MB gacha\n"
        f"• {MAX_VIDEO_DURATION//60} daqiqagacha",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabarlarni qabul qilish"""
    text = update.message.text.strip()
    
    if is_url(text):
        # Video yuklash
        msg = await update.message.reply_text("⏳ Video yuklanmoqda...")
        
        file_id = uuid.uuid4().hex[:8]
        video_path = await download_video(text, file_id)
        
        if video_path and video_path.exists():
            file_size = video_path.stat().st_size / (1024 * 1024)
            
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text(f"❌ Video hajmi {file_size:.1f}MB (limit {MAX_FILE_SIZE}MB)")
                return
            
            # Tugma
            keyboard = [[
                InlineKeyboardButton(
                    "🎵 Audio yuklash",
                    callback_data=f"audio|{text}|{video_path.stem}"
                )
            ]]
            
            with open(video_path, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ Video tayyor!\n📊 {file_size:.1f}MB",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            await msg.delete()
        else:
            await msg.edit_text("❌ Video yuklanmadi")
        
        # Tozalash
        shutil.rmtree(TEMP_PATH / file_id, ignore_errors=True)
        
    else:
        # Audio qidirish
        msg = await update.message.reply_text(f"🔍 Qidirilmoqda: {text}")
        results = await search_audio(text)
        
        if not results:
            await msg.edit_text("❌ Hech narsa topilmadi")
            return
        
        keyboard = []
        for res in results:
            btn_text = f"{res['title'][:30]}... | {res['duration']}"
            keyboard.append([InlineKeyboardButton(
                btn_text,
                callback_data=f"select|{res['url']}|{res['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")])
        
        await msg.edit_text(
            f"🔍 {len(results)} ta natija:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalar"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Bekor qilindi")
        return
    
    parts = query.data.split('|')
    action = parts[0]
    url = parts[1]
    title = parts[2] if len(parts) > 2 else "Audio"
    
    if action in ["select", "audio"]:
        await query.edit_message_text("⏳ Audio yuklanmoqda...")
        
        file_id = uuid.uuid4().hex[:8]
        audio_path = await download_audio(url, file_id)
        
        if audio_path and audio_path.exists():
            file_size = audio_path.stat().st_size / (1024 * 1024)
            
            with open(audio_path, 'rb') as f:
                await query.message.reply_audio(
                    audio=f,
                    title=title[:50],
                    performer="Downloader Bot",
                    caption=f"✅ Audio tayyor!\n📊 {file_size:.1f}MB"
                )
            
            await query.message.delete()
        else:
            await query.message.reply_text("❌ Audio yuklanmadi")
        
        shutil.rmtree(TEMP_PATH / file_id, ignore_errors=True)


def main():
    """Botni ishga tushirish"""
    print("=" * 50)
    print("🚀 SUPER FAST DOWNLOADER")
    print("=" * 50)
    print(f"📁 Papka: {BASE_DIR}")
    print(f"🤖 Token: {BOT_TOKEN[:10]}...")
    print("=" * 50)
    
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(CallbackQueryHandler(button_callback))
        
        print("✅ Bot ishga tushdi!")
        app.run_polling()
        
    except Exception as e:
        print(f"❌ Xatolik: {e}")


if __name__ == "__main__":
    main()