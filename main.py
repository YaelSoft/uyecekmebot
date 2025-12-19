import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, FileReferenceExpiredError, ChatForwardsRestrictedError, UserAlreadyParticipantError
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest

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
def home(): return "YaelSaver V18.0 (Topic Fix) Online! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE DB ---
LANG_DATA = {
    "TR": {
        "welcome": "👋 **YaelSaver V18.0 Hazır!**\n\n🇹🇷 **Topic Fix Sürümü**\n\n📜 **Tek Komut:**\n🔹 `/transfer [KaynakLink] [HedefLink] [Adet]`\n\n💡 **İpucu:** Hedef linkin sonuna Topic ID eklersen (örn: `.../c/123/55`) otomatik o kategoriye atarım.",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "admin_only": "🔒 Sadece Admin.",
        "analyzing": "⚙️ **Analiz Ediliyor...**",
        "started": "🚀 **BAŞLADI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {} (Topic: {})\n📊 **Limit:** {}",
        "transferring": "🔄 **Aktarılıyor...**\n✅ Başarılı: {}\n⏭️ Zaten Vardı: {}\n📉 Kalan: {}",
        "done": "🏁 **BİTTİ!**\n\n✅ Toplam: {}\n⏭️ Atlanan: {}\n⚠️ Hatalı: {}",
        "stopped": "🛑 **Durduruldu!**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Yükleniyor...**",
        "error": "❌ Hata: {}",
        "not_found": "❌ Grup veya Topic bulunamadı! Linkleri kontrol et.",
        "syntax_transfer": "⚠️ Hatalı! Örnek:\n`/transfer https://t.me/kaynak/10 https://t.me/hedef/5 100`"
    },
    "EN": { "welcome": "Ready.", "rights_out": "No rights.", "analyzing": "Analyzing...", "started": "Started", "transferring": "Transferring...", "done": "Done", "stopped": "Stopped", "media_dl": "DL", "media_ul": "UL", "error": "Error", "not_found": "Not Found", "syntax_transfer": "Error"}
}

DB_NAME = "yaelsaver_v18.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def get_lang(): return "TR" # Sabit TR, istersen açarsın
def T(key): return LANG_DATA["TR"].get(key, key)

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

# --- 5. GELİŞMİŞ LINK ÇÖZÜCÜ (TOPIC DAHİL) ---
async def resolve_destination(link):
    """
    Linki analiz eder: Entity (Grup) ve Topic ID'yi döndürür.
    Örnek: t.me/c/12345/55 -> Entity(12345), Topic(55)
    """
    clean_link = link.strip()
    entity = None
    topic_id = None
    
    try:
        # 1. Entity'yi Bul
        if "/c/" in clean_link:
            # Private Link: t.me/c/123456/10
            parts = clean_link.split("/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            entity = await userbot.get_entity(chat_id)
            
            # Topic Var mı? (Linkin sonundaki sayı)
            if len(parts) >= 2 and parts[1].isdigit():
                topic_id = int(parts[1])
                
        elif "+" in clean_link or "joinchat" in clean_link:
            # Davet Linki: Önce katıl
            try:
                if "+" in clean_link: hash_val = clean_link.split("+")[1]
                else: hash_val = clean_link.split("joinchat/")[1]
                await userbot(ImportChatInviteRequest(hash_val))
            except: pass
            
            # Entity al (Burası biraz kör uçuşu, linkten ID çıkmaz)
            # Davet linklerinde topic ID genelde linkte olmaz, manuel verilmesi gerekir
            # Ama biz yine de entity'i çözmeye çalışalım
            try:
                res = await userbot(CheckChatInviteRequest(hash_val))
                if hasattr(res, 'chat'): entity = res.chat
                elif hasattr(res, 'channel'): entity = res.channel
            except: pass
            
        else:
            # Public Link: t.me/username/10
            parts = clean_link.split("t.me/")[-1].split("/")
            username = parts[0]
            entity = await userbot.get_entity(username)
            
            if len(parts) >= 2 and parts[1].isdigit():
                topic_id = int(parts[1])

        return entity, topic_id

    except Exception as e:
        logger.error(f"Resolve Error: {e}")
        return None, None

# --- 6. AKTARIM ---
async def smart_send(msg, dst_entity, dst_topic=None):
    try:
        # Topic ID varsa reply_to olarak ekle
        # Telethon'da forum topiclerine mesaj atmak için reply_to kullanılır.
        if msg.media:
            await userbot.send_file(
                dst_entity, 
                file=msg.media, 
                caption=msg.text or "", 
                reply_to=dst_topic, # KRİTİK NOKTA: Burası Topic ID olacak
                force_document=False
            )
        elif msg.text:
            await userbot.send_message(
                dst_entity, 
                msg.text, 
                reply_to=dst_topic
            )
        return True
    except (ChatForwardsRestrictedError, FileReferenceExpiredError):
        path = None
        try:
            path = await userbot.download_media(msg)
            if path:
                await userbot.send_file(
                    dst_entity, 
                    file=path, 
                    caption=msg.text or "", 
                    reply_to=dst_topic, 
                    force_document=False
                )
                os.remove(path)
                return True
        except:
            if path and os.path.exists(path): os.remove(path)
            return False
    except: return False

# --- 7. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond(T("welcome"))

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_process(event):
    global STOP_PROCESS
    if event.sender_id in ADMINS:
        STOP_PROCESS = True
        await event.respond(T("stopped"))

@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer(event):
    global STOP_PROCESS
    if event.sender_id not in ADMINS: return
    
    STOP_PROCESS = False
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 2000)
    except:
        await event.respond(T("syntax_transfer"))
        return

    status = await event.respond(T("analyzing"))

    # 1. Kaynak ve Hedefi Çöz (Topic ID Dahil)
    src_entity, src_topic = await resolve_destination(src_link)
    dst_entity, dst_topic = await resolve_destination(dst_link)
    
    if not src_entity or not dst_entity:
        await status.edit(T("not_found"))
        return

    # Bilgi Mesajı
    dst_topic_info = f"ID: {dst_topic}" if dst_topic else "Genel (Yok)"
    src_topic_info = f"ID: {src_topic}" if src_topic else "Tümü"
    
    await status.edit(
        f"🚀 **BAŞLADI**\n\n"
        f"📤 **Kaynak:** {src_entity.title}\n"
        f"📂 **Kaynak Topic:** {src_topic_info}\n"
        f"📥 **Hedef:** {dst_entity.title}\n"
        f"📂 **Hedef Topic:** {dst_topic_info} (Buraya atılacak)\n"
        f"📊 **Limit:** {limit}"
    )

    count = 0
    skipped = 0
    
    try:
        # Kaynaktan mesajları çek (Eğer src_topic varsa sadece oradan çeker)
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            if STOP_PROCESS: break
            
            if check_history(src_entity.id, msg.id, dst_entity.id):
                skipped += 1
                continue
            
            # HEDEFE GÖNDER (dst_topic kullanarak)
            if await smart_send(msg, dst_entity, dst_topic):
                add_history(src_entity.id, msg.id, dst_entity.id)
                count += 1
            
            if count % 5 == 0:
                await status.edit(T("transferring").format(count, skipped, limit - count))
            await asyncio.sleep(2)

        final_msg = T("stopped") if STOP_PROCESS else T("done").format(count, skipped, 0)
        await status.edit(final_msg)

    except FloodWaitError as e:
        await status.edit(f"⏳ **FloodWait:** {e.seconds}s wait.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        await event.respond(T("error").format(e))

# --- TEKLİ İNDİRME (/getmedia) ---
@bot.on(events.NewMessage(pattern='/getmedia'))
async def get_media(event):
    try: link = event.text.split()[1]
    except: await event.respond("Link?"); return
    
    status = await event.respond("🔍...")
    try:
        # Basit mantık: Linkten ID bul
        if '/c/' in link:
            parts = link.split('/c/')[1].split('/')
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[-1])
            entity = await userbot.get_entity(chat_id)
        else:
            parts = link.split('/')
            msg_id = int(parts[-1])
            entity = await userbot.get_entity(parts[-2])
            
        msg = await userbot.get_messages(entity, ids=msg_id)
        path = await userbot.download_media(msg)
        if path:
            await status.edit("📤")
            await bot.send_file(event.chat_id, file=path)
            os.remove(path)
            await status.delete()
        else: await status.edit("Medya yok.")
    except Exception as e: await status.edit(f"Hata: {e}")

# --- 8. BAŞLATMA ---
def main():
    print("🚀 YaelSaver V18.0 (Topic Fix) Started...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
