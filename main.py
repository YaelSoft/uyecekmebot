import os
import asyncio
import sqlite3
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask

# --- 1. AYARLAR & LOGLAMA ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V12.0 (Otomatik Hafıza) Aktif!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 2. HAFIZA SİSTEMİ (SQLITE) ---
DB_NAME = "transfer_hafiza.db"

def init_db():
    """Veritabanını başlatır."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Tablo: Hangi mesaj, hangi hedef gruba gönderildi?
    c.execute('''CREATE TABLE IF NOT EXISTS sent_messages
                 (src_chat_id INTEGER, src_msg_id INTEGER, dst_chat_id INTEGER)''')
    conn.commit()
    conn.close()

def is_already_sent(src_chat, msg_id, dst_chat):
    """Mesaj daha önce bu hedefe atılmış mı kontrol eder."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM sent_messages WHERE src_chat_id=? AND src_msg_id=? AND dst_chat_id=?", 
              (src_chat, msg_id, dst_chat))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_as_sent(src_chat, msg_id, dst_chat):
    """Mesajı 'gönderildi' olarak işaretler."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO sent_messages VALUES (?, ?, ?)", (src_chat, msg_id, dst_chat))
    conn.commit()
    conn.close()

# Başlangıçta veritabanını kur
init_db()

# --- 3. İSTEMCİLER ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
STOP_PROCESS = False 

# --- 4. YARDIMCI FONKSİYONLAR ---
async def get_entity_and_topic(link):
    parts = link.strip().rstrip('/').split('/')
    topic_id = None
    entity = None
    entity_name = "Bilinmiyor"
    
    try:
        if 't.me/c/' in link:
            try: c_index = parts.index('c')
            except: 
                for i, p in enumerate(parts):
                    if p == 'c': c_index = i; break
            
            group_id = int('-100' + parts[c_index + 1])
            entity = await userbot.get_entity(group_id)
            
            remaining = parts[c_index + 2:]
            if len(remaining) >= 1 and remaining[0].isdigit():
                topic_id = int(remaining[0])
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): topic_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
        if topic_id and topic_id > 2147483647: topic_id = None

    except Exception as e: logger.error(f"Link Hatası: {e}")
    return entity, topic_id, entity_name

# --- 5. KOMUTLAR ---
@bot.on(events.NewMessage(pattern='/stop'))
async def stop_process(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return
    STOP_PROCESS = True
    await event.respond("🛑 **DURDURULUYOR...**")

@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_auto(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return
    
    STOP_PROCESS = False 
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 10000)
    except:
        await event.respond("⚠️ **Örnek:** `/transfer https://t.me/c/kaynak/10 https://t.me/c/hedef/5 500`")
        return
        
    status = await event.respond(f"⚙️ **Analiz Ediliyor...**")

    # Linkleri Çöz
    src_entity, src_topic, src_name = await get_entity_and_topic(src_link)
    dst_entity, dst_topic, dst_name = await get_entity_and_topic(dst_link)
    
    # ID'leri veritabanı için al
    try:
        src_id_db = src_entity.id
        dst_id_db = dst_entity.id
    except:
        await status.edit("❌ Grup ID'leri alınamadı. Linkleri kontrol et.")
        return

    dst_info = f"📂 Topic: `{dst_topic}`" if dst_topic else "🌍 GENEL"
    
    await status.edit(
        f"🚀 **AKILLI TRANSFER BAŞLADI**\n\n"
        f"📤 **Kaynak:** {src_name}\n"
        f"📥 **Hedef:** {dst_name}\n"
        f"🎯 **Hedef Yer:** {dst_info}\n"
        f"🧠 **Mod:** Otomatik (Atılanlar Atlanır)\n"
    )

    count = 0
    skipped_existing = 0
    skipped_error = 0
    
    # --- İŞLEYİCİ ---
    async def process_message(msg):
        nonlocal count, skipped_existing, skipped_error
        if STOP_PROCESS: return "STOP"

        # 1. KONTROL: Bu mesaj daha önce atıldı mı?
        if is_already_sent(src_id_db, msg.id, dst_id_db):
            skipped_existing += 1
            return "SKIP_EXISTING"

        # 2. HATA DÜZELTME: Dosya boyutu kontrolü (Güvenli)
        is_large = False
        if msg.file: # Dosya varsa
            try:
                if msg.file.size > 100 * 1024 * 1024: is_large = True # 100MB
            except: pass 
        
        if is_large:
            return "SKIP_LARGE"

        path = None
        try:
            # Medya varsa indir
            if msg.media:
                path = await userbot.download_media(msg)
                
                if path:
                    # Gönder
                    await userbot.send_file(
                        dst_entity, 
                        file=path, 
                        caption=msg.text or "", 
                        reply_to=dst_topic,
                        force_document=False
                    )
                    os.remove(path)
                    
                    # BAŞARILI OLURSA VERİTABANINA YAZ
                    mark_as_sent(src_id_db, msg.id, dst_id_db)
                    count += 1
            
            # Sadece metin ise (İstersen burayı aktif et, şu an pasif)
            # else:
            #     await userbot.send_message(dst_entity, msg.text, reply_to=dst_topic)
            #     mark_as_sent(src_id_db, msg.id, dst_id_db)
            #     count += 1

            # Bilgi güncelleme (Her 5 işlemde bir)
            if count % 5 == 0 and count > 0:
                await status.edit(
                    f"🔄 **AKTARIYORUM...**\n"
                    f"✅ **Yeni Atılan:** {count}\n"
                    f"⏭️ **Zaten Vardı (Atlandı):** {skipped_existing}\n"
                )
                        
        except Exception as e:
            if path and os.path.exists(path): os.remove(path)
            if "FloodWait" in str(e):
                wait = int(str(e).split()[3])
                await status.edit(f"⏳ **Telegram Bekletiyor:** {wait}sn mola...")
                await asyncio.sleep(wait + 5)
            elif "You can't write" in str(e):
                return "ERROR_PERM"
            else:
                logger.error(f"Hata: {e}")
                skipped_error += 1

    # --- DÖNGÜ ---
    try:
        # iter_messages otomatik olarak sondan başa tarar
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            res = await process_message(msg)
            
            if res == "STOP": break
            if res == "ERROR_PERM": 
                await status.edit("🚨 **HATA:** Hedef grupta yazma izni yok!"); return
            
            # Eğer mesaj zaten vardıysa (SKIP_EXISTING), bekleme yapmaya gerek yok, hızlı geçsin
            if res != "SKIP_EXISTING":
                await asyncio.sleep(2) # Sadece yeni mesaj atınca bekle

        final_msg = "🛑 **DURDURULDU!**" if STOP_PROCESS else "🏁 **İŞLEM BİTTİ!**"
        
        await status.edit(
            f"{final_msg}\n\n"
            f"✅ **Toplam Yeni Atılan:** {count}\n"
            f"⏭️ **Zaten Vardı (Atlandı):** {skipped_existing}\n"
            f"⚠️ **Hatalı/Büyük:** {skipped_error}\n"
            f"💾 *Hafızaya Kaydedildi.*"
        )

    except Exception as e: await event.respond(f"❌ Sistem Hatası: {e}")

# --- 6. BAŞLATMA ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event): await event.respond("👋 **YaelSaver V12.0 (Akıllı Hafıza)** Hazır.\nArtık ID girme derdi yok.")

def main():
    import threading
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
