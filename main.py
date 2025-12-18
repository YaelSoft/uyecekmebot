import os
import asyncio
import threading
import sqlite3
import time
import sys
import logging
import struct
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
def home(): return "YaelSaver V8.0 (Safe Mode) Active!"
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

# --- 6. LINK ÇÖZÜCÜ (Düzeltilmiş ve Güvenli) ---
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
            
            # Topic ID Kontrolü
            if len(parts) > c_index + 2 and parts[-1].isdigit() and parts[-2].isdigit():
                 possible = int(parts[-2]) # Link mesaj linki ise (.../TOPIC/MSG)
                 if str(possible) != channel_id_part: topic_id = possible
            
            elif parts[-1].isdigit():
                 possible = int(parts[-1]) # Link topic linki ise (.../TOPIC)
                 if str(possible) != channel_id_part: topic_id = possible

        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): topic_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
        
        # EMNİYET SİBOBU: Topic ID 2 Milyardan büyükse geçersizdir.
        if topic_id and topic_id > 2147483647:
            logger.warning(f"Hatalı Topic ID Tespit Edildi: {topic_id}. Sıfırlanıyor.")
            topic_id = None

    except Exception as e:
        logger.error(f"Link Çözme Hatası: {e}")
        
    return entity, topic_id, entity_name

# --- 7. TRANSFER (SAFE MODE) ---
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
        
        status = await event.respond(f"⚙️ **V8.0 Başlatılıyor...**\nGüvenlik kontrolleri yapılıyor.")

        src_entity, src_topic, src_name = await get_entity_and_topic(src_link)
        dst_entity, dst_topic, dst_name = await get_entity_and_topic(dst_link)
        
        # HEDEF TOPIC GÜVENLİK KONTROLÜ
        if dst_topic and dst_topic > 2147483647:
            dst_topic = None 
            await event.respond("⚠️ **UYARI:** Hedef Topic ID çok büyük. Dosyalar 'Genel' odaya atılacak.")

        mode = "NORMAL" if src_topic else "BRUTE FORCE"

        await status.edit(
            f"✅ **Transfer Aktif!**\n\n"
            f"📤 **Kaynak:** {src_name} (Topic: {src_topic or 'Tümü'})\n"
            f"📥 **Hedef:** {dst_name} (Topic: {dst_topic or 'Genel'})\n"
            f"📊 **Limit:** {limit}\n\n"
            f"🚀 **Başladı...**"
        )

        count = 0
        skipped = 0
        
        # --- A) NORMAL MOD (Topic Varsa) ---
        if src_topic:
            async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
                if msg.media:
                    try:
                        await userbot.send_message(dst_entity, file=msg.media, message="", reply_to=dst_topic)
                        count += 1
                        await asyncio.sleep(1.5)
                        if count % 10 == 0: await status.edit(f"🚀 **Aktarılıyor...**\n📦 {count} Medya")
                    except struct.error:
                        # Eğer ID hatası verirse Topic'siz (Genele) atmayı dene
                        try:
                            await userbot.send_message(dst_entity, file=msg.media, message="")
                            count += 1
                        except: continue
                    except Exception as e:
                        if "FloodWait" in str(e):
                            wait = int(str(e).split()[3])
                            await status.edit(f"⏳ **FloodWait:** {wait}sn bekleme...")
                            await asyncio.sleep(wait + 5)
                        continue
        
        # --- B) BRUTE FORCE (Topic Yoksa) ---
        else:
            last_msg = await userbot.get_messages(src_entity, limit=1)
            if not last_msg: await status.edit("❌ Mesaj bulunamadı!"); return
            
            current_id = last_msg[0].id
            processed = 0
            
            while processed < limit and current_id > 0:
                ids_to_fetch = list(range(current_id, max(0, current_id - 20), -1))
                if not ids_to_fetch: break
                
                try:
                    msgs = await userbot.get_messages(src_entity, ids=ids_to_fetch)
                    for msg in msgs:
                        if msg and msg.media:
                            try:
                                await userbot.send_message(dst_entity, file=msg.media, message="", reply_to=dst_topic)
                                count += 1
                                await asyncio.sleep(1.5)
                            except struct.error:
                                # ID Hatası kurtarma
                                try:
                                    await userbot.send_message(dst_entity, file=msg.media, message="")
                                    count += 1
                                except: pass
                            except Exception as e:
                                if "FloodWait" in str(e):
                                    wait = int(str(e).split()[3])
                                    await status.edit(f"⏳ **FloodWait:** {wait}sn bekleme...")
                                    await asyncio.sleep(wait + 5)
                                continue
                        else:
                            skipped += 1
                    
                    processed += len(ids_to_fetch)
                    current_id -= 20
                    if count % 10 == 0: await status.edit(f"🚀 **Brute Force...**\n📦 {count} Medya\n🔍 ID: {current_id}")
                         
                except Exception as e:
                    current_id -= 20
                    continue

        await status.edit(f"🏁 **TAMAMLANDI!**\n✅ Başarılı: {count}")

    except Exception as e: await event.respond(f"❌ Hata: {e}")

# --- 8. BAŞLATMA ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event): await event.respond("👋 **YaelSaver V8.0** Ready.")

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
