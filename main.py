import os
import asyncio
import threading
import sqlite3
import time
import sys
import logging
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest
from telethon.errors import FloodWaitError
from flask import Flask

# --- 1. LOGLAMA ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V9.5 (Restricted Bypass) Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 3. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 4. İSTEMCİLER ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 5. VERİTABANI ---
def init_db():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0, lang TEXT DEFAULT 'en')''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor(); c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if user is None:
        c.execute("INSERT INTO users (user_id, lang) VALUES (?, ?)", (user_id, 'en'))
        conn.commit(); conn.close(); return (user_id, 0, 'en')
    conn.close(); return user

def set_vip(user_id, status):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit(); conn.close()

# --- 6. LINK ÇÖZÜCÜ ---
async def get_entity_and_topic(link):
    parts = link.rstrip('/').split('/')
    topic_id = None
    entity = None
    entity_name = "Bilinmiyor"
    
    try:
        if 't.me/c/' in link:
            c_index = parts.index('c')
            channel_id_part = parts[c_index + 1]
            group_id = int('-100' + channel_id_part)
            entity = await userbot.get_entity(group_id)
            
            if len(parts) > c_index + 2 and parts[-1].isdigit() and parts[-2].isdigit():
                 possible = int(parts[-2])
                 if str(possible) != channel_id_part: topic_id = possible
            elif parts[-1].isdigit():
                 possible = int(parts[-1])
                 if str(possible) != channel_id_part: topic_id = possible
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): topic_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
        # GÜVENLİK: ID çok büyükse sıfırla
        if topic_id and topic_id > 2147483647: topic_id = None

    except Exception as e: logger.error(f"Link Hatası: {e}")
    return entity, topic_id, entity_name

# --- 7. TRANSFER (BYPASS MODE) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    if uid not in ADMINS and u[1] == 0: await event.respond("🔒 VIP Only"); return
    
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 100000)
        
        status = await event.respond(f"⚙️ **V9.5 (Korumalı İçerik Modu)**\nAnaliz ediliyor...")

        src_entity, src_topic, src_name = await get_entity_and_topic(src_link)
        dst_entity, dst_topic, dst_name = await get_entity_and_topic(dst_link)
        
        # Hedef topic güvenliği
        if dst_topic and dst_topic > 2147483647: dst_topic = None 

        await status.edit(
            f"✅ **Bypass Aktif!**\n\n"
            f"📤 **Kaynak:** {src_name} (Korumalı)\n"
            f"📥 **Hedef:** {dst_name}\n"
            f"🛠 **Mod:** İNDİR -> YÜKLE -> SİL\n"
            f"🚀 **Başladı...**"
        )

        count = 0
        
        # --- TEK FONKSİYON: İŞLEYİCİ ---
        async def process_message(msg):
            nonlocal count
            if msg.media:
                path = None
                try:
                    # 1. İNDİR (Sunucuya Çek)
                    path = await userbot.download_media(msg)
                    
                    if path:
                        # 2. YÜKLE (Hedef Gruba)
                        # force_document=False: Video video olarak, resim resim olarak gider
                        await userbot.send_file(
                            dst_entity, 
                            file=path, 
                            caption="", 
                            reply_to=dst_topic,
                            force_document=False
                        )
                        
                        # 3. SİL (Diski Boşalt)
                        os.remove(path)
                        count += 1
                        
                        # Her 1 dosyada güncelleme yapma, log kirlenmesin. 5'te bir yap.
                        if count % 2 == 0: 
                            await status.edit(f"🚀 **Taşınıyor...**\n📦 Adet: {count}")
                            
                except Exception as e:
                    # Hata olursa dosyayı sil ki disk dolmasın
                    if path and os.path.exists(path): os.remove(path)
                    
                    if "FloodWait" in str(e):
                        wait = int(str(e).split()[3])
                        await status.edit(f"⏳ **FloodWait:** {wait}sn mola...")
                        await asyncio.sleep(wait + 5)
                    else:
                        logger.error(f"Hata: {e}")

        # --- DÖNGÜ SEÇİMİ ---
        if src_topic:
            # Topic Modu
            async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
                await process_message(msg)
                # İndirme işlemi ağır olduğu için 2-3 saniye bekle
                await asyncio.sleep(2) 
        else:
            # Brute Force / Genel Mod
            last_msg = await userbot.get_messages(src_entity, limit=1)
            if not last_msg: await status.edit("❌ Mesaj yok."); return
            current_id = last_msg[0].id
            processed = 0
            
            while processed < limit and current_id > 0:
                ids = list(range(current_id, max(0, current_id - 10), -1)) # 10'arlı paket
                if not ids: break
                
                try:
                    msgs = await userbot.get_messages(src_entity, ids=ids)
                    for msg in msgs:
                        if msg: await process_message(msg)
                    
                    processed += len(ids)
                    current_id -= 10
                    if count % 2 == 0: await status.edit(f"🚀 **Taraniyor...**\n📦 Taşınan: {count}\n🔍 ID: {current_id}")
                except:
                    current_id -= 10
                    continue

        await status.edit(f"🏁 **BİTTİ!**\n✅ Toplam: {count}")

    except Exception as e: await event.respond(f"❌ Hata: {e}")

# --- 8. BAŞLATMA ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event): await event.respond("👋 **YaelSaver V9.5** Active.")

@bot.on(events.NewMessage(pattern='/vip'))
async def vip(event): 
    if event.sender_id in ADMINS: 
        try: t=int(event.message.text.split()[1]); set_vip(t,1); await event.respond("✅ VIP")
        except: pass

def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    logger.info("Sistem Başlatıldı")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
