import os
import asyncio
import threading
import time
import sqlite3
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserAlreadyParticipant, UserNotParticipant
from flask import Flask

# --- 1. KEEP-ALIVE WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Ticari Bot Aktif!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR (Render Environment'tan çeker) ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
USERBOT_STRING = os.environ.get("USERBOT_STRING", "")
ADMINS = list(map(int, os.environ.get("ADMINS", "").split(","))) if os.environ.get("ADMINS") else []

# --- 3. İSTEMCİLER ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=USERBOT_STRING, in_memory=True) if USERBOT_STRING else None

# --- 4. VERİTABANI YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    # Tablo: ID, VIP Durumu (1/0), Günlük Hak, Son Reset Tarihi
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0, daily_limit INTEGER DEFAULT 3, last_reset TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Yeni Kullanıcı Kaydı
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
        conn.commit()
        conn.close()
        return (user_id, 0, 3, today) # Varsayılan: Normal Üye, 3 Hak
    
    # Günlük Limit Sıfırlama (Gece 00:00'dan sonra ilk mesajda)
    if user[3] != today and user[1] == 0:
        c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
        conn.commit()
        conn.close()
        return (user_id, 0, 3, today)
        
    conn.close()
    return user

def dusur_hak(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET daily_limit = daily_limit - 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def set_vip(user_id, status):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit()
    conn.close()

# --- 5. PROGRESS BAR (Profesyonel Görünüm) ---
async def progress(current, total, message, start_time, status_text):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        filled = int(percentage / 10)
        bar = '🟩' * filled + '⬜' * (10 - filled)
        try:
            await message.edit_text(
                f"**{status_text}**\n\n"
                f"{bar} **%{round(percentage, 1)}**\n"
                f"📦 **Boyut:** {round(total/1024/1024, 2)} MB\n"
                f"🚀 **Hız:** {round(speed/1024/1024, 2)} MB/s"
            )
        except: pass

# --- 6. KOMUTLAR ---

@bot.on_message(filters.command("start"))
async def start_handler(c, m):
    user_id = m.from_user.id
    data = get_user(user_id) # (id, vip, limit, date)
    is_vip = data[1] == 1
    
    if user_id in ADMINS:
        await m.reply_text("👑 **Admin Paneli**\n\n`/vip ID` - Sınırsız Yap\n`/unvip ID` - Normal Yap\n\nLink göndererek sistemi test edebilirsin.")
    elif is_vip:
        await m.reply_text("🌟 **PREMIUM ÜYELİK**\n\nSınırsız indirme hakkınız aktif. Gizli kanal linki veya mesaj linki gönderin.")
    else:
        await m.reply_text(f"👋 **Hoş Geldin**\n\nGünlük Hakkın: **{data[2]}/3**\n\nLimitsiz erişim için VIP satın almalısın.\nLink göndererek başla!")

# --- TİCARİ KOMUTLAR (Sadece Admin) ---
@bot.on_message(filters.command("vip") & filters.user(ADMINS))
async def vip_yap(c, m):
    try:
        target = int(m.text.split()[1])
        set_vip(target, 1)
        await m.reply_text(f"✅ {target} artık VIP!")
        await bot.send_message(target, "🌟 **Tebrikler!** Hesabınız VIP'ye yükseltildi. Sınırsız kullanabilirsiniz.")
    except: await m.reply_text("Hata: /vip ID")

@bot.on_message(filters.command("unvip") & filters.user(ADMINS))
async def vip_al(c, m):
    try:
        target = int(m.text.split()[1])
        set_vip(target, 0)
        await m.reply_text(f"❌ {target} artık Normal Üye.")
    except: await m.reply_text("Hata: /unvip ID")

# --- 7. MEDYA İŞLEYİCİ (Asıl Para Eden Kısım) ---
@bot.on_message(filters.text & filters.private)
async def downloader(client, message: Message):
    if message.text.startswith("/"): return
    if not userbot: await message.reply_text("❌ Sistem bakımda (Userbot yok)."); return

    user_id = message.from_user.id
    data = get_user(user_id)
    is_vip = data[1] == 1
    limit = data[2]
    
    # Kısıtlama Kontrolü
    if user_id not in ADMINS and not is_vip:
        if limit <= 0:
            await message.reply_text("⛔ **Günlük limitin doldu!**\nDevam etmek için VIP satın almalısın.\n\nSatın Al: @SeninKullaniciAdin")
            return
        await message.reply_text("⏳ **Sıraya alındı...** (Ücretsiz üyeler için bekleme süresi: 5sn)")
        await asyncio.sleep(5)

    text = message.text.strip()
    status_msg = await message.reply_text("🔄 **Bağlantı inceleniyor...**")

    try:
        # A) KATILMA LİNKİ (t.me/+...)
        if "t.me/+" in text or "joinchat" in text:
            try:
                await userbot.join_chat(text)
                await status_msg.edit_text("✅ **Kanala Sızıldı!**\nArtık bu kanaldan gelen 'İletim Kapalı' içerikleri bana atabilirsin.")
            except UserAlreadyParticipant:
                await status_msg.edit_text("ℹ️ Zaten bu kanalı dinliyorum. Mesaj linki atabilirsin.")
            except Exception as e:
                await status_msg.edit_text(f"❌ Kanala giremedim. Link bozuk veya banlıyım.\nHata: {e}")
            return

        # B) İÇERİK LİNKİ
        chat_id = None
        msg_id = None
        
        if "t.me/c/" in text: # Özel/Gizli Kanal
            parts = text.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        elif "t.me/" in text: # Public Kanal
            parts = text.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
        else:
            await status_msg.edit_text("❌ Geçersiz Link.")
            return

        # Mesajı Getir
        try:
            msg = await userbot.get_messages(chat_id, msg_id)
        except Exception as e:
            await status_msg.edit_text(f"❌ **Erişim Engellendi!**\nBot bu kanalda değil. Önce bana kanalın **Davet Linkini** (t.me/+...) atmalısın.")
            return

        if not msg or msg.empty: await status_msg.edit_text("❌ İçerik silinmiş."); return

        # Metinse direkt at
        if not msg.media:
            await message.reply_text(msg.text or "Metin yok.")
            await status_msg.delete()
            return

        # İndir - Yükle - Sil (Restricted Bypass)
        start = time.time()
        path = await userbot.download_media(msg, progress=progress, progress_args=(status_msg, start, "⬇️ Sunucuya İniyor"))
        
        start = time.time()
        if msg.video: await client.send_video(user_id, path, caption=msg.caption, progress=progress, progress_args=(status_msg, start, "⬆️ Size Gönderiliyor"))
        elif msg.document: await client.send_document(user_id, path, caption=msg.caption, progress=progress, progress_args=(status_msg, start, "⬆️ Size Gönderiliyor"))
        elif msg.photo: await client.send_photo(user_id, path, caption=msg.caption)
        elif msg.audio: await client.send_audio(user_id, path, caption=msg.caption)
        
        # Temizlik
        if os.path.exists(path): os.remove(path)
        
        # Hak Düşme
        if user_id not in ADMINS and not is_vip:
            dusur_hak(user_id)
        
        await status_msg.delete()
        await message.reply_text("✅ İşlem Tamam!")

    except Exception as e:
        await status_msg.edit_text(f"❌ Hata: {e}")
        if 'path' in locals() and path and os.path.exists(path): os.remove(path)

# --- 8. BAŞLATMA ---
async def start_services():
    init_db()
    await bot.start()
    if userbot: await userbot.start()
    print("Ticari Bot Başlatıldı!")
    await idle()
    await bot.stop()
    if userbot: await userbot.stop()

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
