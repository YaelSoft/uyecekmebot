import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, FileReferenceExpiredError, ChatForwardsRestrictedError, 
    UserAlreadyParticipantError, InviteHashExpiredError
)
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest

# --- 1. AYARLAR ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# --- 2. LOG & WEB SERVER ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V23.0 (Final) Online! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE DB ---
LANG_DATA = {
    "TR": {
        "welcome": "👋 **YaelSaver V23.0 Hazır!**\n\n🇹🇷 **Dil:** Türkçe\n\n📜 **Komutlar:**\n🔹 `/transfer [Kaynak] [Hedef] [Adet]`\n🔹 `/getmedia [Link]`\n🔹 `/status`\n🔹 `/lang EN`\n\n👮‍♂️ **Admin:** `/addvip`, `/delvip`",
        "rights_out": "❌ **Hakkınız Bitti!** Admin ile görüşün.",
        "admin_only": "🔒 Sadece Admin yetkisiyle.",
        "analyzing": "⚙️ **Analiz Ediliyor & Gruba Giriliyor...**",
        "started": "🚀 **BAŞLADI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n📊 **Limit:** {}",
        "transferring": "🔄 **Aktarılıyor...**\n✅ Başarılı: {}\n⏭️ Zaten Vardı: {}\n📉 Kalan: {}",
        "done": "🏁 **BİTTİ!**\n\n✅ Toplam: {}\n⏭️ Atlanan: {}\n⚠️ Hatalı: {}",
        "stopped": "🛑 **Durduruldu!**",
        "media_ok": "✅ **İndirildi, Gönderiliyor...**",
        "error": "❌ Hata: {}",
        "not_found": "❌ **Erişim Hatası:** Gruba giremedim veya link hatalı.",
        "join_ok": "✅ Gizli gruba giriş yapıldı.",
        "syntax_trans": "⚠️ Örnek: `/transfer https://t.me/kaynak/10 https://t.me/hedef/5 100`",
        "syntax_media": "⚠️ Örnek: `/getmedia https://t.me/c/xxxx/xxxx`"
    },
    "EN": { "welcome": "Ready.", "rights_out": "No rights.", "analyzing": "Analyzing...", "started": "Started", "transferring": "Progress...", "done": "Done", "stopped": "Stopped", "media_ok": "OK", "error": "Error", "not_found": "Not Found", "join_ok": "Joined", "syntax_trans": "Syntax Error", "syntax_media": "Syntax Error" }
}

DB_NAME = "yaelsaver_final.db"

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
    res = conn.cursor().execute("SELECT value FROM settings WHERE key='lang'").fetchone()
    conn.close()
    return res[0] if res else "TR"

def set_lang_db(code):
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (code,))
    conn.commit()
    conn.close()

def T(key): return LANG_DATA.get(get_lang(), LANG_DATA["TR"]).get(key, key)

def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if res: return res
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 3)", (user_id,))
    conn.commit()
    conn.close()
    return "FREE", 3

def use_right(user_id):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if rights > 0:
        conn = sqlite3.connect(DB_NAME)
        conn.cursor().execute("UPDATE users SET rights = rights - 1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    return False

def set_vip(user_id, status):
    tier = "VIP" if status else "FREE"
    rights = 99999 if status else 3
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))
    conn.commit()
    conn.close()

def check_history(src, msg, dst):
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT * FROM history WHERE src_chat=? AND msg_id=? AND dst_chat=?", (src, msg, dst)).fetchone()
    conn.close()
    return res is not None

def add_history(src, msg, dst):
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT INTO history VALUES (?, ?, ?)", (src, msg, dst))
    conn.commit()
    conn.close()

# --- 4. İSTEMCİLER ---
init_db()
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
# Auto Reconnect Aktif
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)

STOP_PROCESS = False

# --- 5. ENTITY ÇÖZÜCÜ (AKILLI JOIN SİSTEMİ) ---
async def resolve_target(link):
    """
    Linki analiz eder, gerekirse gruba katılır ve Entity + Topic ID döndürür.
    """
    clean = link.strip().replace(" ", "")
    entity = None
    topic_id = None
    
    try:
        # 1. Join Link (+ veya joinchat)
        if "+" in clean or "joinchat" in clean:
            try:
                hash_val = clean.split("+")[1] if "+" in clean else clean.split("joinchat/")[1]
                # Önce katılmayı dene
                try:
                    await userbot(ImportChatInviteRequest(hash_val))
                except UserAlreadyParticipantError:
                    pass # Zaten üyeyiz
                except InviteHashExpiredError:
                    return None, None # Link patlak
                
                # Şimdi entity'i al
                res = await userbot(CheckChatInviteRequest(hash_val))
                if hasattr(res, 'chat'): entity = res.chat
                elif hasattr(res, 'channel'): entity = res.channel
            except: pass

        # 2. Private Link (/c/)
        elif "/c/" in clean:
            try:
                # t.me/c/123456/10
                parts = clean.split("/c/")[1].split("/")
                chat_id = int("-100" + parts[0])
                entity = await userbot.get_entity(chat_id)
                # Topic ID kontrolü
                if len(parts) > 1 and parts[1].isdigit():
                    topic_id = int(parts[1])
            except: pass # Erişim yoksa entity None döner

        # 3. Public Link (@)
        else:
            try:
                parts = clean.split("t.me/")[-1].split("/")
                username = parts[0]
                entity = await userbot.get_entity(username)
                if len(parts) > 1 and parts[1].isdigit():
                    topic_id = int(parts[1])
            except: pass
            
        return entity, topic_id

    except Exception as e:
        logger.error(f"Resolve Error: {e}")
        return None, None

# --- 6. AKTARIM MOTORU ---
async def smart_send(msg, dst_entity, dst_topic):
    try:
        # 1. Temiz Kopya (İletildi yazısı olmadan)
        if msg.media:
            await userbot.send_file(dst_entity, file=msg.media, caption=msg.text or "", reply_to=dst_topic, force_document=False)
        elif msg.text:
            await userbot.send_message(dst_entity, msg.text, reply_to=dst_topic)
        return True
    except (ChatForwardsRestrictedError, FileReferenceExpiredError):
        # 2. Yasaklıysa İndir & Yükle
        path = None
        try:
            path = await userbot.download_media(msg)
            if path:
                await userbot.send_file(dst_entity, file=path, caption=msg.text or "", reply_to=dst_topic, force_document=False)
                os.remove(path)
                return True
        except:
            if path and os.path.exists(path): os.remove(path)
    except: pass
    return False

# --- 7. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    check_user(event.sender_id)
    await event.respond(T("welcome"))

@bot.on(events.NewMessage(pattern='/lang'))
async def lang_cmd(event):
    if event.sender_id not in ADMINS: return
    try:
        target = event.text.split()[1].upper()
        if target in ["TR", "EN"]:
            set_lang_db(target)
            await event.respond(f"Language: {target}")
    except: await event.respond("/lang TR | EN")

@bot.on(events.NewMessage(pattern='/status'))
async def status(event):
    tier, rights = check_user(event.sender_id)
    await event.respond(f"📊 **Durum:**\n👑 {tier}\n🎫 {rights}")

@bot.on(events.NewMessage(pattern='/addvip'))
async def add_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        set_vip(int(event.text.split()[1]), True)
        await event.respond("✅ VIP")
    except: pass

@bot.on(events.NewMessage(pattern='/delvip'))
async def del_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        set_vip(int(event.text.split()[1]), False)
        await event.respond("❌ FREE")
    except: pass

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_cmd(event):
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
        # Basit ID Çözümleme (Manuel)
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
            await status.edit(T("media_ok"))
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
        src_link, dst_link, limit = args[1], args[2], min(int(args[3]), 2000)
    except:
        await event.respond(T("syntax_trans")); return

    status = await event.respond(T("analyzing"))

    src_entity, src_topic = await resolve_target(src_link)
    dst_entity, dst_topic = await resolve_target(dst_link)
    
    if not src_entity or not dst_entity:
        await status.edit(T("not_found")); return

    await status.edit(T("started").format(src_entity.title, dst_entity.title, limit))

    count = 0
    skipped = 0
    
    try:
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            if STOP_PROCESS: break
            
            if check_history(src_entity.id, msg.id, dst_entity.id):
                skipped += 1
                continue
            
            if await smart_send(msg, dst_entity, dst_topic):
                add_history(src_entity.id, msg.id, dst_entity.id)
                count += 1
            
            if count % 5 == 0:
                await status.edit(T("transferring").format(count, skipped, limit - count))
            await asyncio.sleep(2)

        final_msg = T("stopped") if STOP_PROCESS else T("done").format(count, skipped, 0)
        await status.edit(final_msg)

    except FloodWaitError as e:
        await status.edit(f"⏳ **FloodWait:** {e.seconds}s.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        await event.respond(T("error").format(e))

def main():
    print("🚀 V23.0 Started...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
