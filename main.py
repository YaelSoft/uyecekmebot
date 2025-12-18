import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWait, FileReferenceExpiredError, ChatForwardsRestrictedError

# --- 1. AYARLAR (Pella/Render Env Variables) ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") # Userbot Session
# Admin ID'leri (Virgülle ayır)
ADMINS = list(map(int, os.environ.get("ADMINS", "123456789").split(",")))

# --- 2. LOG & WEB SERVER (7/24) ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V14.0 (Panel Edition) Online! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. VERİTABANI YÖNETİMİ ---
DB_NAME = "yaelsaver_v14.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Kullanıcılar Tablosu: ID, Üyelik Tipi (FREE/VIP), Kalan Hak
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
    # Hafıza Tablosu: Aynı mesajı tekrar atmamak için
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
    conn.commit()
    conn.close()

# Kullanıcı İşlemleri
def register_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, tier, rights) VALUES (?, 'FREE', 3)", (user_id,))
    conn.commit()
    conn.close()

def get_user_status(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res if res else ("FREE", 0) # Kayıtlı değilse

def use_right(user_id):
    tier, rights = get_user_status(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if rights > 0:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE users SET rights = rights - 1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    return False

def set_vip(user_id, is_vip):
    tier = "VIP" if is_vip else "FREE"
    rights = 9999 if is_vip else 3
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, tier, rights) VALUES (?, ?, ?)", (user_id, tier, rights))
    conn.commit()
    conn.close()

# Hafıza Kontrolü
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
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
STOP_PROCESS = False

# --- 5. YARDIMCI: Link Çözücü ---
async def parse_link(link):
    parts = link.strip().rstrip('/').split('/')
    entity = None
    topic_id = None
    msg_id = None
    
    try:
        # Mesaj ID var mı? (En sondaki sayı)
        if parts[-1].isdigit():
            msg_id = int(parts[-1])
        
        # Topic ID var mı? (Sondan ikinci sayı)
        # Örnek: t.me/c/1234/TOPIC/MSG -> len=...
        
        if 't.me/c/' in link:
            # Private: .../c/CHATID/...
            c_index = parts.index('c')
            chat_id = int('-100' + parts[c_index + 1])
            entity = await userbot.get_entity(chat_id)
            
            # Topic ve Msg ayrımı
            remaining = parts[c_index + 2:]
            if len(remaining) == 2: # CHAT/TOPIC/MSG
                topic_id = int(remaining[0])
                msg_id = int(remaining[1])
            elif len(remaining) == 1: # CHAT/MSG
                msg_id = int(remaining[0])
                
        else:
            # Public: t.me/user/MSG
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): msg_id = int(parts[-1])
            
        # Topic ID Güvenliği (Mesaj ID ile karışmasın)
        if topic_id and topic_id > 2000000000: topic_id = None

    except Exception as e:
        logger.error(f"Link Parse Error: {e}")
    
    return entity, topic_id, msg_id

# --- 6. CORE: TRANSFER MOTORU (Kopyala -> Olmazsa İndir) ---
async def smart_send(msg, dst_entity, dst_topic=None):
    # 1. YÖNTEM: TEMİZ KOPYALAMA (İletildi yazmaz)
    # Telethon'da 'send_message(file=msg.media)' yapmak temiz kopya oluşturur.
    try:
        if msg.media:
            await userbot.send_file(
                dst_entity,
                file=msg.media,
                caption=msg.text or "",
                reply_to=dst_topic,
                force_document=False
            )
        elif msg.text:
            await userbot.send_message(
                dst_entity,
                msg.text,
                reply_to=dst_topic
            )
        return True # Başarılı
        
    except (ChatForwardsRestrictedError, FileReferenceExpiredError) as e:
        # 2. YÖNTEM: KANAL KORUMALIYSA İNDİR -> YÜKLE
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
        except Exception as inner_e:
            if path and os.path.exists(path): os.remove(path)
            return False
    except Exception as e:
        return False

# --- 7. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    register_user(event.sender_id)
    await event.respond(
        "👋 **YaelSaver V14.0 (Panel) Hazır!**\n\n"
        "📜 **Komutlar:**\n"
        "🔹 `/getmedia [Link]` -> Tek Mesaj İndir\n"
        "🔹 `/transfer [Kaynak] [Hedef] [Limit]` -> Toplu Çek\n"
        "🔹 `/status` -> Hakkını Sorgula\n"
        "👮‍♂️ **Admin:** `/addvip`, `/delvip`"
    )

@bot.on(events.NewMessage(pattern='/status'))
async def status(event):
    tier, rights = get_user_status(event.sender_id)
    await event.respond(f"📊 **Durumunuz:**\n👑 Üyelik: **{tier}**\n🎫 Kalan Hak: **{rights}**")

# --- ADMIN KOMUTLARI ---
@bot.on(events.NewMessage(pattern='/addvip'))
async def add_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target_id = int(event.text.split()[1])
        set_vip(target_id, True)
        await event.respond(f"✅ Kullanıcı ({target_id}) **VIP** yapıldı!")
    except: await event.respond("Hata: `/addvip ID`")

@bot.on(events.NewMessage(pattern='/delvip'))
async def del_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target_id = int(event.text.split()[1])
        set_vip(target_id, False)
        await event.respond(f"❌ Kullanıcı ({target_id}) **FREE** moda alındı.")
    except: await event.respond("Hata: `/delvip ID`")

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_process(event):
    global STOP_PROCESS
    if event.sender_id in ADMINS:
        STOP_PROCESS = True
        await event.respond("🛑 **İşlemler Durduruluyor...**")

# --- TEKLİ İNDİRME ---
@bot.on(events.NewMessage(pattern='/getmedia'))
async def get_media_handler(event):
    user_id = event.sender_id
    if not use_right(user_id):
        await event.respond("❌ **Hakkınız Bitti!** Admin ile görüşün."); return
        
    try:
        link = event.text.split()[1]
    except:
        await event.respond("⚠️ Kullanım: `/getmedia https://t.me/c/123/456`"); return
    
    status = await event.respond("🔍 **Aranıyor...**")
    
    try:
        entity, topic, msg_id = await parse_link(link)
        if not entity or not msg_id:
            await status.edit("❌ Mesaj bulunamadı!"); return

        msg = await userbot.get_messages(entity, ids=msg_id)
        if not msg:
            await status.edit("❌ Mesaj silinmiş veya erişilemiyor."); return

        # Direkt Botun olduğu sohbete at (Userbot indirip Bota atar)
        path = await userbot.download_media(msg)
        if path:
            await status.edit("📤 **Yükleniyor...**")
            await bot.send_file(
                event.chat_id,
                file=path,
                caption=msg.text or ""
            )
            os.remove(path)
            await status.delete()
        else:
            await status.edit("❌ Medya indirilemedi.")
            
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- TOPLU TRANSFER (TRANSFER & TOPIC TRANSFER BİRLEŞİK) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_handler(event):
    global STOP_PROCESS
    user_id = event.sender_id
    
    # Hak Kontrolü (Toplu işlem 1 hak yer)
    if not use_right(user_id):
        await event.respond("❌ **Hakkınız Bitti!**"); return
    
    STOP_PROCESS = False
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        limit = min(int(args[3]), 1000) # Max 1000 mesaj güvenlik için
    except:
        await event.respond("⚠️ **Örnek:** `/transfer [Kaynak] [Hedef] [Adet]`\nTopic linki verirsen topic'e atar.")
        return

    status = await event.respond("⚙️ **Analiz Ediliyor...**")

    # Linkleri Çöz
    src_entity, src_topic, _ = await parse_link(src_link)
    dst_entity, dst_topic, _ = await parse_link(dst_link)
    
    try:
        src_id_db = src_entity.id
        dst_id_db = dst_entity.id
    except:
        await status.edit("❌ Gruplara erişilemiyor."); return

    dst_info = f"📂 Topic: `{dst_topic}`" if dst_topic else "🌍 GENEL"
    
    await status.edit(
        f"🚀 **TRANSFER BAŞLADI**\n"
        f"📤 Kaynak ID: `{src_id_db}`\n"
        f"📥 Hedef: {dst_info}\n"
        f"📊 Hedeflenen: {limit}"
    )

    count = 0
    skipped = 0
    
    # --- DÖNGÜ ---
    try:
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            if STOP_PROCESS: break
            
            # Hafıza Kontrolü
            if check_history(src_id_db, msg.id, dst_id_db):
                skipped += 1
                continue
            
            # Akıllı Gönderim (Copy -> Fail -> Download)
            success = await smart_send(msg, dst_entity, dst_topic)
            
            if success:
                add_history(src_id_db, msg.id, dst_id_db)
                count += 1
            else:
                # Başarısızsa (FloodWait vb. değilse)
                pass
            
            # Log
            if count % 5 == 0:
                await status.edit(f"🔄 **Aktarılıyor...**\n✅ Başarılı: {count}\n⏭️ Zaten Vardı: {skipped}")
            
            await asyncio.sleep(2) # Spam koruması

        final_msg = "🛑 **DURDURULDU**" if STOP_PROCESS else "🏁 **BİTTİ**"
        await status.edit(f"{final_msg}\n✅ Toplam: {count}\n⏭️ Atlanan: {skipped}")

    except Exception as e:
        await event.respond(f"❌ Kritik Hata: {e}")

# --- 8. BAŞLATMA ---
def main():
    print("🚀 YaelSaver V14.0 (Panel Edition) Başlatılıyor...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
