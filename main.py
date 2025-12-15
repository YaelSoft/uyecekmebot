import os
import asyncio
import threading
import sqlite3
import time
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Sistem Aktif! Patronun hesabı devrede."
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")       
SESSION_STRING = os.environ.get("SESSION_STRING", "") # BURAYA KENDİ ANA HESABININ KODU GELECEK
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 3. BAŞLATMA ---
# Müşteri Botu
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
# Senin Hesabın (Gizli Userbot)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 4. VERİTABANI ---
def init_db():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0, daily_limit INTEGER DEFAULT 3, last_reset TEXT)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    today = datetime.now().strftime("%Y-%m-%d")
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
        conn.commit(); conn.close(); return (user_id, 0, 3, today)
    if user[3] != today and user[1] == 0:
        c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
        conn.commit(); conn.close(); return (user_id, 0, 3, today)
    conn.close(); return user

def dusur_hak(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET daily_limit = daily_limit - 1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

def set_vip(user_id, status):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit(); conn.close()

# --- 5. KOMUTLAR ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    
    if uid in ADMINS:
        msg = "👑 **PATRON MODU**\nSenin hesabın üzerinden her yerden veri çekebilirim.\n`/vip ID` ile müşteri yönet."
    elif vip:
        msg = "🌟 **VIP MÜŞTERİ**\nSınırsız hakkınız var. Link gönderin."
    else:
        msg = f"👋 **Deneme Sürümü**\nHakkın: {u[2]}/3. \n\nÖzel kanallardan (Patronun olduğu) içerik çekebilirsin."
    await event.respond(msg)

@bot.on(events.NewMessage(pattern='/vip'))
async def vip_yap(event):
    if event.sender_id in ADMINS:
        try: set_vip(int(event.text.split()[1]), 1); await event.respond("✅ VIP Yapıldı.")
        except: pass

@bot.on(events.NewMessage(pattern='/unvip'))
async def vip_al(event):
    if event.sender_id in ADMINS:
        try: set_vip(int(event.text.split()[1]), 0); await event.respond("❌ Normal Üye Oldu.")
        except: pass

# --- 6. İÇERİK ÇEKİCİ (TRUVA ATI MODU) ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    limit = u[2]
    
    if uid not in ADMINS and not vip:
        if limit <= 0: await event.respond("⛔ Limit doldu. VIP al."); return
        status = await event.respond("⏳ **Sıraya alındı (Bekle)...**"); await asyncio.sleep(5)
    else:
        status = await event.respond("🔄 **İşleniyor...**")

    text = event.message.text.strip()
    
    try:
        # Link Analizi
        msg_id = None
        entity = None
        
        # 1. Özel/Gizli Kanal Linki (t.me/c/...)
        # Sen zaten içeridesin, direkt ID ile çekiyoruz.
        if 't.me/c/' in text:
            parts = text.split('t.me/c/')[1].split('/')
            channel_id = int(parts[0])
            msg_id = int(parts[1])
            # Telethon için ID düzeltmesi (-100 ekle)
            entity = await userbot.get_entity(int(f'-100{channel_id}'))
            
        # 2. Public Kanal Linki
        elif 't.me/' in text:
            parts = text.split('t.me/')[1].split('/')
            username = parts[0]
            msg_id = int(parts[1])
            entity = await userbot.get_entity(username)
            
        else:
            await status.edit("❌ Geçersiz Link."); return

        # Mesajı AL (Senin Gözünle)
        try:
            msg = await userbot.get_messages(entity, ids=msg_id)
        except Exception as e:
            await status.edit("❌ **Erişim Yok!**\nPatron (Admin) bu grupta ekli değil. Önce Adminin gruba girmesi lazım.")
            return

        if not msg or not msg.media:
            await status.edit("❌ Medya bulunamadı veya silinmiş."); return

        # İndir
        await status.edit("⬇️ **İndiriliyor...**")
        path = await userbot.download_media(msg.media)
        
        # Yükle
        await status.edit("⬆️ **Yükleniyor...**")
        await bot.send_file(event.chat_id, path, caption=msg.text or "")
        
        # Sil
        if os.path.exists(path): os.remove(path)
        
        # Hak Düş
        if uid not in ADMINS and not vip: use_right(uid)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {str(e)}")
        if 'path' in locals() and path and os.path.exists(path): os.remove(path)

# --- BAŞLATMA ---
def main():
    threading.Thread(target=run_web).start()
    userbot.start()
    print("Sistem Hazır!")
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
