import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, FileReferenceExpiredError, ChatForwardsRestrictedError

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
def home(): return "YaelSaver V15.0 Online! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL PAKETİ ---
LANG_DATA = {
    "TR": {
        "welcome": "👋 **YaelSaver V15.0 Hazır!**\n\n🇹🇷 **Dil:** Türkçe\n\n📜 **Komutlar:**\n🔹 `/transfer [Kaynak] [Hedef] [Adet]`\n🔹 `/getmedia [Link]`\n🔹 `/status`\n🔹 `/lang EN`\n\n👮‍♂️ **Admin:** `/addvip`, `/delvip`",
        "lang_set": "🇹🇷 Dil Türkçe yapıldı.",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "admin_only": "🔒 Sadece Admin.",
        "analyzing": "⚙️ **Analiz Ediliyor...**",
        "started": "🚀 **BAŞLADI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n📊 **Limit:** {}",
        "transferring": "🔄 **Aktarılıyor...**\n✅ Başarılı: {}\n⏭️ Zaten Vardı: {}\n📉 Kalan: {}",
        "done": "🏁 **BİTTİ!**\n\n✅ Toplam: {}\n⏭️ Atlanan: {}\n⚠️ Hatalı: {}",
        "stopped": "🛑 **Durduruldu!**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Yükleniyor...**",
        "error": "❌ Hata: {}",
        "not_found": "❌ İçerik bulunamadı.",
        "syntax_transfer": "⚠️ Hatalı! Örnek:\n`/transfer https://t.me/kaynak/10 https://t.me/hedef/5 100`",
        "syntax_media": "⚠️ Hatalı! Örnek:\n`/getmedia https://t.me/c/xxxx/xxxx`"
    },
    "EN": {
        "welcome": "👋 **YaelSaver V15.0 Ready!**\n\n🇺🇸 **Lang:** English\n\n📜 **Commands:**\n🔹 `/transfer [Src] [Dst] [Limit]`\n🔹 `/getmedia [Link]`\n🔹 `/status`\n🔹 `/lang TR`\n\n👮‍♂️ **Admin:** `/addvip`, `/delvip`",
        "lang_set": "🇺🇸 Language set to English.",
        "rights_out": "❌ **Out of credits!**",
        "admin_only": "🔒 Admin only.",
        "analyzing": "⚙️ **Analyzing...**",
        "started": "🚀 **STARTED**\n\n📤 **Src:** {}\n📥 **Dst:** {}\n📊 **Limit:** {}",
        "transferring": "🔄 **Transferring...**\n✅ OK: {}\n⏭️ Skip: {}\n📉 Left: {}",
        "done": "🏁 **DONE!**\n\n✅ Total: {}\n⏭️ Skip: {}\n⚠️ Error: {}",
        "stopped": "🛑 **Stopped!**",
        "media_dl": "📥 **Downloading...**",
        "media_ul": "📤 **Uploading...**",
        "error": "❌ Error: {}",
        "not_found": "❌ Content not found.",
        "syntax_transfer": "⚠️ Usage:\n`/transfer [Src] [Dst] [Limit]`",
        "syntax_media": "⚠️ Usage:\n`/getmedia [Link]`"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v15.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def get_lang():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='lang'")
    res = c.fetchone()
    conn.close()
    return res[0] if res else "TR"

def set_lang_db(lang_code):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (lang_code,))
    conn.commit()
    conn.close()

def T(key):
    lang = get_lang()
    return LANG_DATA.get(lang, LANG_DATA["TR"]).get(key, key)

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
    return res if res else ("FREE", 0)

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

# --- 5. İSTEMCİLER ---
init_db()
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)

STOP_PROCESS = False

# --- 6. PARSE & SMART SEND ---
async def parse_link(link):
    parts = link.strip().rstrip('/').split('/')
    entity = None
    topic_id = None
    msg_id = None
    entity_name = "Unknown"
    
    try:
        if parts[-1].isdigit(): msg_id = int(parts[-1])
        
        if 't.me/c/' in link:
            c_index = parts.index('c')
            chat_id = int('-100' + parts[c_index + 1])
            entity = await userbot.get_entity(chat_id)
            remaining = parts[c_index + 2:]
            if len(remaining) == 2:
                topic_id = int(remaining[0])
                msg_id = int(remaining[1])
            elif len(remaining) == 1:
                msg_id = int(remaining[0])
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)
            if parts[-1].isdigit(): msg_id = int(parts[-1])
            
        if hasattr(entity, 'title'): entity_name = entity.title
        if topic_id and topic_id > 2000000000: topic_id = None

    except Exception: pass
    return entity, topic_id, msg_id, entity_name

async def smart_send(msg, dst_entity, dst_topic=None):
    try:
        if msg.media:
            await userbot.send_file(dst_entity, file=msg.media, caption=msg.text or "", reply_to=dst_topic, force_document=False)
        elif msg.text:
            await userbot.send_message(dst_entity, msg.text, reply_to=dst_topic)
        return True
    except (ChatForwardsRestrictedError, FileReferenceExpiredError):
        path = None
        try:
            path = await userbot.download_media(msg)
            if path:
                await userbot.send_file(dst_entity, file=path, caption=msg.text or "", reply_to=dst_topic, force_document=False)
                os.remove(path)
                return True
        except Exception:
            if path and os.path.exists(path): os.remove(path)
            return False
    except Exception: return False

# --- 7. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    register_user(event.sender_id)
    await event.respond(T("welcome"))

@bot.on(events.NewMessage(pattern='/lang'))
async def lang_handler(event):
    if event.sender_id not in ADMINS: return
    try:
        target = event.text.split()[1].upper()
        if target in ["TR", "EN"]:
            set_lang_db(target)
            await event.respond(T("lang_set"))
        else: await event.respond("TR / EN ?")
    except: await event.respond("/lang TR")

@bot.on(events.NewMessage(pattern='/status'))
async def status(event):
    tier, rights = get_user_status(event.sender_id)
    await event.respond(f"📊 **User Status:**\n👑 Tier: **{tier}**\n🎫 Rights: **{rights}**")

@bot.on(events.NewMessage(pattern='/addvip'))
async def add_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target_id = int(event.text.split()[1])
        set_vip(target_id, True)
        await event.respond(f"✅ {target_id} -> VIP")
    except: await event.respond("Usage: `/addvip ID`")

@bot.on(events.NewMessage(pattern='/delvip'))
async def del_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target_id = int(event.text.split()[1])
        set_vip(target_id, False)
        await event.respond(f"❌ {target_id} -> FREE")
    except: await event.respond("Usage: `/delvip ID`")

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_process(event):
    global STOP_PROCESS
    if event.sender_id in ADMINS:
        STOP_PROCESS = True
        await event.respond(T("stopped"))

@bot.on(events.NewMessage(pattern='/getmedia'))
async def get_media(event):
    user_id = event.sender_id
    if not use_right(user_id):
        await event.respond(T("rights_out")); return
        
    try: link = event.text.split()[1]
    except: await event.respond(T("syntax_media")); return
    
    status = await event.respond(T("analyzing"))
    
    try:
        entity, topic, msg_id, _ = await parse_link(link)
        if not entity or not msg_id:
            await status.edit(T("not_found"))
            return

        msg = await userbot.get_messages(entity, ids=msg_id)
        if not msg:
            await status.edit(T("not_found"))
            return

        path = await userbot.download_media(msg)
        if path:
            await status.edit(T("media_ul"))
            await bot.send_file(event.chat_id, file=path, caption=msg.text or "")
            os.remove(path)
            await status.delete()
        else:
            await status.edit(T("error").format("No Media"))
            
    except Exception as e:
        await status.edit(T("error").format(e))

@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer(event):
    global STOP_PROCESS
    user_id = event.sender_id
    if not use_right(user_id):
        await event.respond(T("rights_out")); return
    
    STOP_PROCESS = False
    try:
        args = event.message.text.split()
        src_link = args[1]; dst_link = args[2]
        limit = min(int(args[3]), 2000)
    except:
        await event.respond(T("syntax_transfer"))
        return

    status = await event.respond(T("analyzing"))

    src_entity, src_topic, _, src_name = await parse_link(src_link)
    dst_entity, dst_topic, _, _ = await parse_link(dst_link)
    
    # HATA DÜZELTME BURADA: try-except bloğu açıldı
    try:
        src_id_db = src_entity.id
        dst_id_db = dst_entity.id
    except Exception:
        await status.edit(T("not_found"))
        return

    await status.edit(T("started").format(src_name, dst_entity.title if hasattr(dst_entity, 'title') else "Dest", limit))

    count = 0
    skipped = 0
    
    try:
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            if STOP_PROCESS: break
            
            if check_history(src_id_db, msg.id, dst_id_db):
                skipped += 1
                continue
            
            if await smart_send(msg, dst_entity, dst_topic):
                add_history(src_id_db, msg.id, dst_id_db)
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

# --- 8. BAŞLATMA ---
def main():
    print("🚀 YaelSaver V15.0 Started...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
