import os
import asyncio
import threading
import sqlite3
import time
import sys
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest
from telethon.tl.types import Channel
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V6.0 (Debug Mode) Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []
OWNER_CONTACT = "@yasin33" 

FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 

# --- 3. METİNLER ---
TEXTS = {
    "en": {"vip_only": "🔒 **VIP Only!**", "processing": "🔄 **Processing...**"},
    "tr": {"vip_only": "🔒 **Sadece VIP!**", "processing": "🔄 **İşleniyor...**"}
}
def get_text(lang, key): return TEXTS.get(lang, TEXTS['en']).get(key, "")

# --- 4. İSTEMCİLER ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 5. VERİTABANI (Basitleştirildi) ---
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

# --- 6. LINK ÇÖZÜCÜ (PRO VERSİYON) ---
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
                 topic_id = int(parts[-2]) # .../TOPIC/MSG_ID
            elif parts[-1].isdigit() and str(parts[-1]) != channel_id_part:
                 topic_id = int(parts[-1]) # .../TOPIC
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): topic_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
    except Exception as e:
        print(f"Link Çözme Hatası: {e}")
        
    return entity, topic_id, entity_name

# --- 7. TRANSFER (DEBUG MODLU) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    if uid not in ADMINS and u[1] == 0: await event.respond("🔒 VIP Only"); return
    
    try:
        # Komut: /transfer [Kaynak] [Hedef] [Adet]
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 100000)
        
        status = await event.respond(f"🕵️‍♂️ **Analiz Başlatılıyor...**\n`{src_link}` inceleniyor.")

        # 1. Kaynak ve Hedefi Çöz
        src_entity, src_topic, src_name = await get_entity_and_topic(src_link)
        dst_entity, dst_topic, dst_name = await get_entity_and_topic(dst_link)
        
        if not src_entity or not dst_entity:
            await status.edit("❌ **HATA:** Gruplardan birine erişilemedi. Userbot üye mi?")
            return

        # 2. Durum Raporu (Kullanıcı görsün diye)
        src_type = f"📂 TEK TOPIC ({src_topic})" if src_topic else "🌍 TÜM GRUP (Komple)"
        dst_type = f"📂 HEDEF TOPIC ({dst_topic})" if dst_topic else "🌍 HEDEF ANA SAYFA"
        
        await status.edit(
            f"✅ **Analiz Tamam!**\n\n"
            f"📤 **Kaynak:** {src_name}\n"
            f"ℹ️ **Mod:** {src_type}\n"
            f"📥 **Hedef:** {dst_name}\n"
            f"🎯 **Nereye:** {dst_type}\n\n"
            f"🚀 **Transfer Başlıyor...**"
        )

        # 3. İŞLEM DÖNGÜSÜ
        count = 0
        skipped = 0
        
        # Mantık: Eğer src_topic YOKSA (None), reply_to parametresini hiç verme.
        # Bu sayede Telethon tüm mesajları çeker.
        if src_topic:
            iterator = userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic)
        else:
            iterator = userbot.iter_messages(src_entity, limit=limit) # reply_to YOK = HEPSİ

        async for msg in iterator:
            if msg.media:
                try:
                    # Hedefe atarken dst_topic varsa onu kullan, yoksa düz at
                    await userbot.send_message(
                        dst_entity, 
                        file=msg.media, 
                        message="", # Metin Yok
                        reply_to=dst_topic # Varsa Topic'e, yoksa genele
                    )
                    count += 1
                    
                    # Loglama (Her 20 mesajda bir güncelle)
                    if count % 20 == 0:
                        await status.edit(f"🚀 **Aktarılıyor...**\n📦 Başarılı: {count}\n⏩ İşlenen: {count+skipped}")
                    
                    await asyncio.sleep(1.5) # Spam önlemi
                except Exception as e:
                    print(f"Transfer Hatası: {e}")
                    # FloodWait gelirse bekle
                    if "FloodWait" in str(e):
                        wait_time = int(str(e).split()[3])
                        await status.edit(f"⏳ **FloodWait:** Telegram dur dedi. {wait_time} saniye bekleniyor...")
                        await asyncio.sleep(wait_time + 5)
                    continue
            else:
                skipped += 1
                    
        await status.edit(f"🏁 **İŞLEM BİTTİ!**\n\n✅ Toplam Taşınan: {count}\n🗑️ Atlanan (Yazı vb.): {skipped}")

    except Exception as e: await event.respond(f"❌ Kritik Hata: {e}")

# --- 8. DİĞER KOMUTLAR (Kısa Tutuldu) ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event): await event.respond("👋 **YaelSaver V6.0** Active.\nUse `/transfer` for magic.")

@bot.on(events.NewMessage(pattern='/vip'))
async def vip(event): 
    if event.sender_id in ADMINS: 
        try: t=int(event.message.text.split()[1]); set_vip(t,1); await event.respond("✅ VIP")
        except: pass

def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
