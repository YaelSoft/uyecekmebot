import os
import asyncio
import threading
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from flask import Flask

# --- RENDER WEB SUNUCUSU (Uyumaması için) ---
app = Flask(__name__)
@app.route('/')
def home(): return "Restricted Content Bot Aktif!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- AYARLAR (Render Environment'tan çeker) ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
USERBOT_STRING = os.environ.get("USERBOT_STRING", "")
# İzinli kullanıcılar (Virgülle ayırarak Render'a gir: 12345,67890)
ADMINS = list(map(int, os.environ.get("ADMINS", "").split(","))) if os.environ.get("ADMINS") else []

# --- BOT İSTEMCİLERİ ---
# Bot (Sana dosyayı atacak olan)
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# Userbot (Gizli kanaldan veriyi çalacak olan)
if USERBOT_STRING:
    userbot = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=USERBOT_STRING, in_memory=True)
else:
    print("HATA: USERBOT_STRING girilmemiş!")
    userbot = None

# --- YARDIMCI: İLERLEME ÇUBUĞU ---
async def progress(current, total, message, start_time, action_type):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total: # Her 5 saniyede bir güncelle
        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000
        estimated_total_time = elapsed_time + time_to_completion
        
        # İlerleme Çubuğu Görseli
        filled = int(percentage / 10)
        bar = '▓' * filled + '░' * (10 - filled)
        
        try:
            await message.edit_text(
                f"**{action_type}...**\n\n"
                f"**Durum:** {bar} {round(percentage, 2)}%\n"
                f"**Boyut:** {humanbytes(current)} / {humanbytes(total)}\n"
                f"**Hız:** {humanbytes(speed)}/s"
            )
        except:
            pass

def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

# --- KOMUTLAR ---

@bot.on_message(filters.command("start"))
async def start_handler(c, m):
    await m.reply_text("👋 **Korumalı İçerik İndirici**\n\nLink gönder, 'İletim Kapalı' olsa bile indirip sana atayım.\n\nÖrnek: `https://t.me/c/123123123/500`")

@bot.on_message(filters.text & filters.private)
async def restricted_downloader(client, message: Message):
    if message.from_user.id not in ADMINS:
        await message.reply_text("⛔ Sadece Adminler kullanabilir.")
        return

    if not userbot:
        await message.reply_text("❌ Userbot aktif değil.")
        return

    text = message.text.strip()
    
    # 1. Link Analizi
    try:
        if "t.me/c/" in text:
            # Özel Kanal: t.me/c/123456789/100 -> ChatID: -100123456789
            parts = text.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        elif "t.me/" in text:
            # Public Kanal
            parts = text.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
        else:
            await message.reply_text("❌ Geçersiz Link.")
            return
    except:
        await message.reply_text("❌ Link formatı bozuk.")
        return

    status_msg = await message.reply_text("🔄 **Userbot bağlanıyor...**")
    start_time = time.time()

    # 2. Dosyayı Çekme (Userbot)
    try:
        # Mesajı bul
        try:
            target_msg = await userbot.get_messages(chat_id, msg_id)
        except Exception as e:
            await status_msg.edit_text(f"❌ Mesaja erişemedim. Userbot kanalda ekli mi?\nHata: {e}")
            return

        if not target_msg or target_msg.empty:
            await status_msg.edit_text("❌ Mesaj boş veya silinmiş.")
            return
        
        # Sadece medya varsa indir
        if not target_msg.media:
            # Sadece metinse kopyala geç
            await message.reply_text(target_msg.text or "Metin yok.")
            await status_msg.delete()
            return

        # 3. İNDİRME İŞLEMİ (Userbot -> Disk)
        await status_msg.edit_text("⬇️ **Sunucuya İndiriliyor...**")
        file_path = await userbot.download_media(
            message=target_msg,
            progress=progress,
            progress_args=(status_msg, start_time, "⬇️ İndiriliyor")
        )

        if not file_path:
            await status_msg.edit_text("❌ İndirme başarısız oldu.")
            return

        # 4. YÜKLEME İŞLEMİ (Disk -> Bot -> Sen)
        await status_msg.edit_text("⬆️ **Telegram'a Yükleniyor...**")
        start_time = time.time() # Süreyi sıfırla

        # Dosya türüne göre gönder
        if target_msg.video:
            await client.send_video(
                chat_id=message.chat.id,
                video=file_path,
                caption=target_msg.caption,
                supports_streaming=True,
                progress=progress,
                progress_args=(status_msg, start_time, "⬆️ Yükleniyor")
            )
        elif target_msg.document:
             await client.send_document(
                chat_id=message.chat.id,
                document=file_path,
                caption=target_msg.caption,
                progress=progress,
                progress_args=(status_msg, start_time, "⬆️ Yükleniyor")
            )
        elif target_msg.photo:
             await client.send_photo(
                chat_id=message.chat.id,
                photo=file_path,
                caption=target_msg.caption
            )
        elif target_msg.audio:
             await client.send_audio(
                chat_id=message.chat.id,
                audio=file_path,
                caption=target_msg.caption,
                progress=progress,
                progress_args=(status_msg, start_time, "⬆️ Yükleniyor")
            )
        
        await status_msg.delete()
        
        # 5. TEMİZLİK (ÇOK ÖNEMLİ)
        # Diski doldurmamak için dosyayı hemen sil
        if os.path.exists(file_path):
            os.remove(file_path)

    except FloodWait as e:
        await status_msg.edit_text(f"⏳ **FloodWait:** {e.value} saniye beklemem lazım.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Hata: {str(e)}")
        # Hata olsa bile dosyayı silmeyi dene
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)

# --- BAŞLATMA ---
async def start_services():
    await bot.start()
    if userbot: await userbot.start()
    print("✅ Sistem Tamam! İndir-Yükle-Sil Modu Aktif.")
    await idle()
    await bot.stop()
    if userbot: await userbot.stop()

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
