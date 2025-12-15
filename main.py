import os
import asyncio
import threading
import time
import sqlite3
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU (Uyumaması için) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot 7/24 Aktif! UptimeRobot burayı pingle."

def run_web():
    # Render'ın verdiği portu dinle
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- 2. AYARLAR (Render Environment'tan çeker) ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
USERBOT_STRING = os.environ.get("USERBOT_STRING", "")
# Admin ID'lerini virgülle ayırarak al (Örn: 123456,789012)
ADMINS = list(map(int, os.environ.get("ADMINS", "").split(","))) if os.environ.get("ADMINS") else []

# --- 3. BOT İSTEMCİLERİ ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

if USERBOT_STRING:
    userbot = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=USERBOT_STRING, in_memory=True)
else:
    userbot = None

# --- 4. VERİTABANI İŞLEMLERİ ---
def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, 
                  is_vip INTEGER DEFAULT 0, 
                  daily_limit INTEGER DEFAULT 3, 
                  last_reset TEXT,
                  total_downloads INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    
    # Kullanıcı yoksa oluştur
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
        conn.commit()
        return (user_id, 0, 3, today, 0)
    
    # Günlük limit sıfırlama (VIP değilse)
    if user[3] != today and user[1] == 0:
        c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
        conn.commit()
        return (user_id, 0, 3, today, user[4])
        
    conn.close()
    return user

def use_right(user_id):
    conn = sqlite3.connect('users.db', check_same_thread=False)
    conn.execute("UPDATE users SET daily_limit = daily_limit - 1, total_downloads = total_downloads + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def set_vip_status(user_id, status): # 1 VIP, 0 Normal
    conn = sqlite3.connect('users.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit()
    conn.close()

# --- 5. İLERLEME ÇUBUĞU ---
async def progress(current, total, message, start_time, action_type):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        filled = int(percentage / 10)
        bar = '▓' * filled + '░' * (10 - filled)
        try:
            await message.edit_text(
                f"**{action_type}...**\n\n"
                f"**Durum:** {bar} {round(percentage, 1)}%\n"
                f"**Hız:** {round(speed/1024/1024, 2)} MB/s"
            )
        except: pass

# --- 6. KOMUTLAR VE PANELLER ---

@bot.on_message(filters.command("start"))
async def start_handler(c, m):
    user_id = m.from_user.id
    user_data = get_user_data(user_id) # (id, is_vip, limit, date, total)
    is_vip = user_data[1] == 1
    daily_limit = user_data[2]
    
    # --- PANEL 1: ADMİN PANELİ ---
    if user_id in ADMINS:
        txt = (
            "👑 **YÖNETİCİ PANELİ**\n\n"
            "Sistem Emrinde Patron. İletim kapalı içerikleri söküp alabilirsin.\n\n"
            "🛠 **Admin Komutları:**\n"
            "• `/vip ID` -> Kullanıcıyı VIP yap (Sınırsız)\n"
            "• `/unvip ID` -> Kullanıcıyı Normal yap\n"
            "• `/stats` -> Toplam kullanım verisi\n\n"
            "Link gönder, gerisini bana bırak."
        )
        await m.reply_text(txt)
        return

    # --- PANEL 2: VIP KULLANICI ---
    if is_vip:
        txt = (
            "🌟 **VIP PANELİ**\n\n"
            "Hoş geldin! Hesabın **SINIRSIZ** moda yükseltilmiş.\n"
            "Hiçbir bekleme süresi veya günlük limit olmadan dilediğin kadar içerik indirebilirsin.\n\n"
            "🚀 **Link Gönder Gelsin!**"
        )
        await m.reply_text(txt)
        return

    # --- PANEL 3: NORMAL (DENEME) KULLANICI ---
    txt = (
        f"👋 **Hoş Geldin {m.from_user.first_name}**\n\n"
        f"Şu an **Deneme Sürümü** kullanıyorsun.\n\n"
        f"📝 **Bugünkü Hakkın:** {daily_limit}/3 İçerik\n"
        f"⏳ **Yenilenme:** Gece 00:00\n\n"
        "Limitsiz indirme ve bekleme süresini kaldırmak için VIP satın alabilirsin.\n"
        "Link göndererek başla!"
    )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("💎 VIP Satın Al", url="https://t.me/SeninKullaniciAdin")]])
    await m.reply_text(txt, reply_markup=buttons)

# Admin: VIP Yapma
@bot.on_message(filters.command("vip") & filters.user(ADMINS))
async def make_vip(c, m):
    try:
        target = int(m.text.split()[1])
        set_vip_status(target, 1)
        await m.reply_text(f"✅ {target} ID'li kullanıcı artık VIP!")
        try: await bot.send_message(target, "🌟 **Tebrikler!** Hesabınız VIP yapıldı. Sınırsız kullanabilirsiniz.")
        except: pass
    except: await m.reply_text("Kullanım: /vip ID")

# Admin: VIP Alma
@bot.on_message(filters.command("unvip") & filters.user(ADMINS))
async def remove_vip(c, m):
    try:
        target = int(m.text.split()[1])
        set_vip_status(target, 0)
        await m.reply_text(f"❌ {target} ID'li kullanıcı Normal üye oldu.")
    except: await m.reply_text("Kullanım: /unvip ID")

# --- 7. İÇERİK İNDİRİCİ (Userbot -> Disk -> Bot) ---
@bot.on_message(filters.text & filters.private)
async def downloader(client, message: Message):
    if message.text.startswith("/"): return # Komutsa işleme
    
    if not userbot:
        await message.reply_text("❌ Sistem Hatası: Userbot aktif değil.")
        return

    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    is_vip = user_data[1] == 1
    daily_limit = user_data[2]
    
    # Admin değilse ve VIP değilse limit kontrolü
    if user_id not in ADMINS and not is_vip:
        if daily_limit <= 0:
            await message.reply_text("⛔ **Bugünkü limitin doldu!**\nYarın gel veya VIP al.")
            return
        await message.reply_text("⏳ **Sıraya alındı...** (Normal üyeler 5sn bekler)")
        await asyncio.sleep(5)

    text = message.text.strip()
    status_msg = await message.reply_text("🔍 **Link İnceleniyor...**")
    
    try:
        # Link Analizi
        if "t.me/c/" in text:
            parts = text.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        elif "t.me/" in text:
            parts = text.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
        else:
            await status_msg.edit_text("❌ Geçersiz Link.")
            return

        # Userbot Mesajı Alır
        try:
            msg = await userbot.get_messages(chat_id, msg_id)
        except:
            await status_msg.edit_text("❌ Mesaja erişemedim. Userbot kanalda değil veya link yanlış.")
            return

        if not msg or msg.empty:
            await status_msg.edit_text("❌ Mesaj silinmiş veya bulunamadı.")
            return

        # Sadece Metinse
        if not msg.media:
            await message.reply_text(msg.text or "İçerik yok.")
            await status_msg.delete()
            return

        # İNDİRME (Userbot -> Render Diski)
        start_time = time.time()
        file_path = await userbot.download_media(
            message=msg,
            progress=progress,
            progress_args=(status_msg, start_time, "⬇️ Sunucuya İniyor")
        )
        
        # GÖNDERME (Render Diski -> Kullanıcı)
        start_time = time.time()
        
        if msg.video:
            await client.send_video(user_id, video=file_path, caption=msg.caption, progress=progress, progress_args=(status_msg, start_time, "⬆️ Size Yükleniyor"))
        elif msg.document:
            await client.send_document(user_id, document=file_path, caption=msg.caption, progress=progress, progress_args=(status_msg, start_time, "⬆️ Size Yükleniyor"))
        elif msg.photo:
            await client.send_photo(user_id, photo=file_path, caption=msg.caption)
        elif msg.audio:
            await client.send_audio(user_id, audio=file_path, caption=msg.caption)

        # Hak düşme (VIP ve Admin değilse)
        if user_id not in ADMINS and not is_vip:
            use_right(user_id)
            limit_msg = f"\n📉 Kalan Hak: {daily_limit - 1}"
        else:
            limit_msg = "\n💎 VIP Modu"

        await status_msg.edit_text(f"✅ **İşlem Tamamlandı!**{limit_msg}")
        
        # TEMİZLİK (Dosyayı sil)
        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ Hata: {e}")
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)

# --- 8. BAŞLATMA ---
async def start_services():
    init_db()
    await bot.start()
    if userbot: await userbot.start()
    print("✅ Sistem 3 Farklı Panel Moduyla Aktif!")
    await idle()
    await bot.stop()
    if userbot: await userbot.stop()

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
