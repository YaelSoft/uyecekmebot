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
def home(): return "YaelSaver V11.0 (Control Mode) Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 2. GLOBAL KONTROL DEĞİŞKENLERİ ---
STOP_PROCESS = False  # Durdurma tetiği

# --- 3. İSTEMCİLER ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 4. YARDIMCI FONKSİYONLAR ---
async def get_entity_and_topic(link):
    """Linki analiz eder: Grup Entity'sini ve Topic ID'sini bulur."""
    parts = link.rstrip('/').split('/')
    topic_id = None
    entity = None
    entity_name = "Bilinmiyor"
    
    try:
        if 't.me/c/' in link:
            c_index = parts.index('c')
            group_id = int('-100' + parts[c_index + 1])
            entity = await userbot.get_entity(group_id)
            
            # Topic ID Tespiti (Gelişmiş)
            if len(parts) > c_index + 2 and parts[-1].isdigit() and parts[-2].isdigit():
                 topic_id = int(parts[-2]) # .../TOPIC/MSG
            elif parts[-1].isdigit():
                 topic_id = int(parts[-1]) # .../TOPIC
                 
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): topic_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
        # Topic ID Güvenlik (General'e düşmemesi için kontrol)
        if topic_id and topic_id > 2147483647: topic_id = None

    except Exception as e: logger.error(f"Link Hatası: {e}")
    return entity, topic_id, entity_name

# --- 5. DURDURMA KOMUTU ---
@bot.on(events.NewMessage(pattern='/stop'))
async def stop_process(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return
    STOP_PROCESS = True
    await event.respond("🛑 **İŞLEM DURDURULUYOR...**\n(Mevcut dosya bittikten sonra duracak)")

# --- 6. TRANSFER (V11 - DETAYLI & KONTROLLÜ) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_dl(event):
    global STOP_PROCESS
    uid = event.sender_id
    if uid not in ADMINS: await event.respond("🔒 Admin Only"); return
    
    # 1. Başlangıç Hazırlığı
    STOP_PROCESS = False # Bayrağı indir
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 10000)
    except:
        await event.respond("⚠️ **Hatalı Komut!**\nKullanım: `/transfer [Kaynak] [Hedef] [Adet]`")
        return
        
    status = await event.respond(f"⚙️ **Analiz Yapılıyor...**")

    # 2. Link Çözme
    src_entity, src_topic, src_name = await get_entity_and_topic(src_link)
    dst_entity, dst_topic, dst_name = await get_entity_and_topic(dst_link)
    
    # Hedef Topic Kontrolü
    dst_info = f"📂 Topic: {dst_topic}" if dst_topic else "🌍 GENEL (Topic Yok!)"
    
    # 3. Bilgi Paneli Göster
    await status.edit(
        f"🚀 **TRANSFER BAŞLATILDI**\n\n"
        f"📤 **Kaynak:** {src_name}\n"
        f"📥 **Hedef:** {dst_name}\n"
        f"🎯 **Hedef Oda:** {dst_info}\n"
        f"📊 **Toplam İşlenecek:** {limit}\n\n"
        f"👇 *Durdurmak için /stop yazın*"
    )

    count = 0
    skipped_size = 0
    
    # --- İŞLEYİCİ ---
    async def process_message(msg):
        nonlocal count, skipped_size
        
        # STOP KONTROLÜ
        if STOP_PROCESS: return "STOP"

        if msg.media:
            # 100MB Limit
            if hasattr(msg, 'file') and msg.file.size > 100 * 1024 * 1024:
                skipped_size += 1
                return "SKIP"

            path = None
            try:
                # İNDİR
                path = await userbot.download_media(msg)
                
                if path:
                    # YÜKLE
                    # force_document=False -> Video video olarak gider
                    # reply_to=dst_topic -> KESİN OLARAK o odaya atar
                    await userbot.send_file(
                        dst_entity, 
                        file=path, 
                        caption="", 
                        reply_to=dst_topic,
                        force_document=False
                    )
                    os.remove(path)
                    count += 1
                    
                    # Canlı Güncelleme (Her 3 işlemde bir)
                    if count % 3 == 0:
                        await status.edit(
                            f"🔄 **AKTARIYORUM...**\n\n"
                            f"📤 **Kaynak:** {src_name}\n"
                            f"📥 **Hedef:** {dst_name}\n"
                            f"📂 **Oda:** {dst_topic if dst_topic else 'Genel'}\n\n"
                            f"✅ **Başarılı:** {count}\n"
                            f"⚠️ **Büyük Dosya:** {skipped_size}\n"
                            f"📉 **Kalan (Tahmini):** {limit - count}"
                        )
                        
            except Exception as e:
                if path and os.path.exists(path): os.remove(path)
                if "FloodWait" in str(e):
                    wait = int(str(e).split()[3])
                    await status.edit(f"⏳ **Telegram Bekletiyor:** {wait} saniye...")
                    await asyncio.sleep(wait + 5)
                elif "You can't write" in str(e):
                    await status.edit("🚨 **HATA:** Hedef grupta YAZMA İZNİN YOK! Userbot'u Admin yap.")
                    return "ERROR"
                else:
                    logger.error(f"Hata: {e}")

    # --- DÖNGÜ ---
    try:
        if src_topic:
            # Topic Modu
            async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
                res = await process_message(msg)
                if res == "STOP": break
                if res == "ERROR": break
                await asyncio.sleep(2) 
        else:
            # Genel Mod
            last_msg = await userbot.get_messages(src_entity, limit=1)
            if not last_msg: await status.edit("❌ Mesaj bulunamadı."); return
            current_id = last_msg[0].id
            processed = 0
            
            while processed < limit and current_id > 0:
                if STOP_PROCESS: break
                ids = list(range(current_id, max(0, current_id - 10), -1))
                if not ids: break
                
                msgs = await userbot.get_messages(src_entity, ids=ids)
                for msg in msgs:
                    if STOP_PROCESS: break
                    if msg: await process_message(msg)
                
                processed += len(ids)
                current_id -= 10
                if count % 3 == 0: 
                     await status.edit(f"🚀 **Taranıyor...**\n✅ Başarılı: {count}\n🔍 ID: {current_id}")

        final_msg = "🛑 **DURDURULDU!**" if STOP_PROCESS else "🏁 **İŞLEM TAMAMLANDI!**"
        await status.edit(
            f"{final_msg}\n\n"
            f"✅ **Toplam Taşınan:** {count}\n"
            f"⚠️ **Atlanan (Büyük):** {skipped_size}\n"
            f"📂 **Hedef Oda:** {dst_topic if dst_topic else 'Genel'}"
        )

    except Exception as e: await event.respond(f"❌ Kritik Hata: {e}")

# --- 7. BAŞLATMA ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event): await event.respond("👋 **YaelSaver V11.0** Ready.")

def main():
    import threading
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
