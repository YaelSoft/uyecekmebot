import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, FileReferenceExpiredError, ChatForwardsRestrictedError
from telethon.tl.types import InputPeerChannel

# --- 1. AYARLAR ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "123456789").split(",")))

# --- 2. LOG & WEB SERVER ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V16.0 (Control Mode) Online! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. VERİTABANI ---
DB_NAME = "yaelsaver_v16.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
    conn.commit()
    conn.close()

def check_history(src, msg, dst):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM history WHERE src_chat=? AND msg_id=? AND dst_chat=?", (src, msg, dst))
    res = c.fetchone()
    conn.close()
    return res is not None

def add_history(src, msg, dst):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO history VALUES (?, ?, ?)", (src, msg, dst))
    conn.commit()
    conn.close()

# --- 4. İSTEMCİLER ---
init_db()
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)

STOP_PROCESS = False

# --- 5. GELİŞMİŞ ENTITY BULUCU (Userbot Kontrollü) ---
async def get_target_entity(link):
    """
    Userbot'un verilen linke erişimi olup olmadığını kontrol eder.
    Link formatları:
    - https://t.me/c/123456789/10 (Private)
    - https://t.me/username (Public)
    - @username
    """
    try:
        # 1. Linki Temizle
        clean_link = link.strip()
        
        # 2. Eğer Private Link ise (t.me/c/...) ID'yi ayıkla
        if 't.me/c/' in clean_link:
            parts = clean_link.split('/')
            c_index = parts.index('c')
            chat_id_raw = parts[c_index + 1]
            
            # Telethon için ID formatı: -100 + ID
            if not chat_id_raw.startswith('-100'):
                chat_id = int('-100' + chat_id_raw)
            else:
                chat_id = int(chat_id_raw)
                
            # Userbot ile bu ID'yi bulmaya çalış
            entity = await userbot.get_entity(chat_id)
            return entity, chat_id
            
        # 3. Eğer Public Link ise
        elif 't.me/' in clean_link or '@' in clean_link:
            # Username'i al (t.me/deneme -> deneme)
            if 't.me/' in clean_link:
                username = clean_link.split('t.me/')[1].split('/')[0]
            else:
                username = clean_link
            
            entity = await userbot.get_entity(username)
            return entity, entity.id
            
        # 4. Direkt ID girildiyse
        elif clean_link.replace('-','').isdigit():
            entity = await userbot.get_entity(int(clean_link))
            return entity, int(clean_link)

    except Exception as e:
        logger.error(f"Entity Error: {e}")
        return None, None

# --- 6. AKTARIM FONKSİYONLARI ---
async def smart_send(msg, dst_entity, dst_topic=None):
    try:
        # Önce Kopyalama (Hızlı)
        if msg.media:
            await userbot.send_file(dst_entity, file=msg.media, caption=msg.text or "", reply_to=dst_topic, force_document=False)
        elif msg.text:
            await userbot.send_message(dst_entity, msg.text, reply_to=dst_topic)
        return True
    except (ChatForwardsRestrictedError, FileReferenceExpiredError):
        # Hata verirse İndir/Yükle (Yavaş ama Garanti)
        path = None
        try:
            path = await userbot.download_media(msg)
            if path:
                await userbot.send_file(dst_entity, file=path, caption=msg.text or "", reply_to=dst_topic, force_document=False)
                os.remove(path)
                return True
        except:
            if path and os.path.exists(path): os.remove(path)
            return False
    except: return False

# --- 7. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond(
        "👋 **YaelSaver V16.0 (Manual) Hazır!**\n\n"
        "📜 **Komutlar:**\n"
        "1️⃣ **Normal Transfer:**\n`/transfer [Kaynak_Link] [Hedef_Link] [Adet]`\n"
        "*(Topicsiz düz gruplar ve kanallar için)*\n\n"
        "2️⃣ **Topic Transfer:**\n`/topictransfer [Kaynak_Link] [Kaynak_Topic_ID] [Hedef_Link] [Hedef_Topic_ID] [Adet]`\n"
        "*(Topicli gruplar için özel komut)*\n\n"
        "🛑 Durdurmak için: `/stop`"
    )

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_cmd(event):
    global STOP_PROCESS
    if event.sender_id in ADMINS:
        STOP_PROCESS = True
        await event.respond("🛑 **İşlemler Durduruluyor...**")

# --- NORMAL TRANSFER (Topicsiz) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_normal(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return

    try:
        args = event.message.text.split()
        # args: /transfer src dst limit
        if len(args) < 4:
            await event.respond("⚠️ **Hata:** `/transfer [Kaynak] [Hedef] [Adet]`")
            return
        
        src_link = args[1]
        dst_link = args[2]
        limit = int(args[3])

    except: await event.respond("⚠️ Sayısal değer hatası."); return

    status = await event.respond("🕵️ **Userbot ile Bağlantı Kontrol Ediliyor...**")

    # 1. KONTROL AŞAMASI
    src_entity, src_id = await get_target_entity(src_link)
    if not src_entity:
        await status.edit("❌ **HATA:** Userbot 'Kaynak' grupta bulunamadı! Linki kontrol et veya Userbot'u gruba ekle.")
        return

    dst_entity, dst_id = await get_target_entity(dst_link)
    if not dst_entity:
        await status.edit("❌ **HATA:** Userbot 'Hedef' grupta bulunamadı!")
        return

    await status.edit(
        f"✅ **Erişim Doğrulandı!**\n\n"
        f"📤 Kaynak: `{src_entity.title}`\n"
        f"📥 Hedef: `{dst_entity.title}`\n"
        f"🚀 **İşlem Başlatılıyor...**"
    )
    await asyncio.sleep(1)

    # 2. İŞLEM AŞAMASI
    STOP_PROCESS = False
    count = 0
    
    try:
        async for msg in userbot.iter_messages(src_entity, limit=limit):
            if STOP_PROCESS: break
            
            # Hafıza
            if check_history(src_id, msg.id, dst_id): continue

            success = await smart_send(msg, dst_entity, None)
            if success:
                add_history(src_id, msg.id, dst_id)
                count += 1
            
            if count % 5 == 0:
                await status.edit(f"🔄 **Aktarılıyor...** {count}")
            await asyncio.sleep(2)

        await status.edit(f"🏁 **Tamamlandı!** Toplam: {count}")

    except Exception as e:
        await event.respond(f"❌ Kritik Hata: {e}")

# --- TOPIC TRANSFER (Topicli) ---
@bot.on(events.NewMessage(pattern='/topictransfer'))
async def transfer_topic(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return

    try:
        args = event.message.text.split()
        # args: /topictransfer src src_top_id dst dst_top_id limit
        if len(args) < 6:
            await event.respond(
                "⚠️ **Hata:** Eksik parametre!\n"
                "`/topictransfer [KaynakLink] [KaynakTopicID] [HedefLink] [HedefTopicID] [Adet]`"
            )
            return
        
        src_link = args[1]
        src_topic_id = int(args[2])
        dst_link = args[3]
        dst_topic_id = int(args[4])
        limit = int(args[5])

    except: await event.respond("⚠️ ID'ler sayı olmalı!"); return

    status = await event.respond("🕵️ **Topic Erişimi Kontrol Ediliyor...**")

    # 1. KONTROL
    src_entity, src_id = await get_target_entity(src_link)
    dst_entity, dst_id = await get_target_entity(dst_link)

    if not src_entity or not dst_entity:
        await status.edit("❌ **HATA:** Userbot gruplardan birine erişemiyor!")
        return

    await status.edit(
        f"✅ **Topic Modu Aktif!**\n\n"
        f"📤 Kaynak: `{src_entity.title}` (Topic: {src_topic_id})\n"
        f"📥 Hedef: `{dst_entity.title}` (Topic: {dst_topic_id})\n"
        f"🚀 **Başlıyor...**"
    )

    # 2. İŞLEM
    STOP_PROCESS = False
    count = 0
    
    try:
        # reply_to parametresi Telethon'da topic ID'sidir
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic_id):
            if STOP_PROCESS: break
            
            if check_history(src_id, msg.id, dst_id): continue

            # Hedef topic'e gönder
            success = await smart_send(msg, dst_entity, dst_topic_id)
            if success:
                add_history(src_id, msg.id, dst_id)
                count += 1
            
            if count % 5 == 0:
                await status.edit(f"🔄 **Aktarılıyor (Topic)...** {count}")
            await asyncio.sleep(2)

        await status.edit(f"🏁 **Tamamlandı!** Toplam: {count}")

    except Exception as e:
        await event.respond(f"❌ Kritik Hata: {e}")

# --- 8. BAŞLATMA ---
def main():
    print("🚀 YaelSaver V16.0 Started...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
