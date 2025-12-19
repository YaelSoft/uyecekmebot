import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, 
    FileReferenceExpiredError, 
    ChatForwardsRestrictedError, 
    UserAlreadyParticipantError,
    RPCError
)
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest

# --- 1. AYARLAR (Env Variables) ---
# Müşteriye burayı doldurtacaksın
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# --- 2. WEB SERVER (7/24 Aktiflik İçin) ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V19.0 (Commercial) Running... 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE METİNLER (TR / EN) ---
LANG = {
    "TR": {
        "welcome": "👋 **Merhaba! YaelSaver Sistemine Hoşgeldiniz.**\n\nBu bot ile içerikleri güvenle yedekleyebilir ve taşıyabilirsiniz.\n\n🇹🇷 **Dil:** Türkçe\n\n👇 **Komut Menüsü:**",
        "menu_trans": "♻️ Transfer Başlat",
        "menu_media": "📥 Tekli İndir",
        "menu_acc": "👤 Hesabım",
        "menu_lang": "🇺🇸 English",
        "rights_err": "❌ **Yetersiz Bakiye!**\nPaket yükseltmek için yönetici ile görüşün.",
        "admin_only": "🔒 **Yetkisiz Erişim!** Bu komut sadece yöneticiler içindir.",
        "analyzing": "🔍 **Bağlantılar ve Yetkiler Kontrol Ediliyor...**",
        "started": "🚀 **İŞLEM BAŞLATILDI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n📂 **Topic:** {}\n📊 **Limit:** {} Mesaj",
        "transferring": "🔄 **İşleniyor...**\n✅ Başarılı: {}\n⏭️ Atlanan: {}\n📉 Kalan: {}",
        "completed": "✅ **İŞLEM TAMAMLANDI**\n\n📦 Toplam Taşınan: {}\n♻️ Zaten Mevcut: {}\n⚠️ Hatalar: {}",
        "stopped": "🛑 **İşlem Kullanıcı Tarafından Durduruldu.**",
        "not_found": "❌ **Hata:** Kaynak veya Hedef gruba erişilemiyor!\nLütfen Userbot'un grupta olduğundan emin olun.",
        "join_ok": "✅ Gizli gruba giriş yapıldı.",
        "syntax_trans": "⚠️ **Hatalı Format!**\nKullanım: `/transfer [KaynakLink] [HedefLink] [Adet]`\n\n*İpucu: Hedef linkin sonuna /TopicID eklerseniz oraya atarım.*",
        "syntax_get": "⚠️ **Hatalı Format!**\nKullanım: `/getmedia [MesajLink]`",
        "media_ok": "✅ **Başarıyla İndirildi!** Yükleniyor...",
        "error_gen": "❌ **Bir Hata Oluştu:** {}"
    },
    "EN": {
        "welcome": "👋 **Hello! Welcome to YaelSaver System.**\n\nSecurely backup and transfer your content.\n\n🇺🇸 **Lang:** English\n\n👇 **Menu:**",
        "menu_trans": "♻️ Start Transfer",
        "menu_media": "📥 Single Download",
        "menu_acc": "👤 My Account",
        "menu_lang": "🇹🇷 Türkçe",
        "rights_err": "❌ **Insufficient Credits!**\nContact admin to upgrade.",
        "admin_only": "🔒 **Unauthorized!** Admin only command.",
        "analyzing": "🔍 **Analyzing Links & Permissions...**",
        "started": "🚀 **PROCESS STARTED**\n\n📤 **Source:** {}\n📥 **Dest:** {}\n📂 **Topic:** {}\n📊 **Limit:** {} Msgs",
        "transferring": "🔄 **Processing...**\n✅ Success: {}\n⏭️ Skipped: {}\n📉 Left: {}",
        "completed": "✅ **PROCESS COMPLETED**\n\n📦 Total Moved: {}\n♻️ Skipped: {}\n⚠️ Errors: {}",
        "stopped": "🛑 **Process Stopped by User.**",
        "not_found": "❌ **Error:** Cannot access Source or Dest chat!\nEnsure Userbot is a member.",
        "join_ok": "✅ Joined private chat.",
        "syntax_trans": "⚠️ **Invalid Format!**\nUsage: `/transfer [SrcLink] [DstLink] [Limit]`\n\n*Tip: Add /TopicID to the end of dest link for topics.*",
        "syntax_get": "⚠️ **Invalid Format!**\nUsage: `/getmedia [MsgLink]`",
        "media_ok": "✅ **Downloaded!** Uploading...",
        "error_gen": "❌ **Error Occurred:** {}"
    }
}

# --- 4. VERİTABANI (SQLite) ---
DB_NAME = "yaelsaver_pro.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS history (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.commit()

def get_text(key, lang="TR"):
    return LANG.get(lang, LANG["TR"]).get(key, key)

def get_user_lang():
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT value FROM settings WHERE key='lang'").fetchone()
    return res[0] if res else "TR"

def set_user_lang(lang):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (lang,))
        conn.commit()

# Kullanıcı Sistemi
def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    # Kayıt yoksa Free ver
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 3)", (user_id,))
    return "FREE", 3

def deduct_credit(user_id):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if rights > 0:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - 1 WHERE user_id=?", (user_id,))
        return True
    return False

def set_vip_status(user_id, status):
    tier = "VIP" if status else "FREE"
    rights = 99999 if status else 3
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

# Hafıza Sistemi
def is_processed(src, msg, dst):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT * FROM history WHERE src_chat=? AND msg_id=? AND dst_chat=?", (src, msg, dst)).fetchone()
    return res is not None

def mark_processed(src, msg, dst):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO history VALUES (?, ?, ?)", (src, msg, dst))

# --- 5. İSTEMCİLER ---
init_db()
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
# Auto-reconnect ve retry eklendi, kopma olmaz
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)

STOP_PROCESS = False

# --- 6. GELİŞMİŞ LINK ÇÖZÜCÜ (Otomatik Topic Algılama) ---
async def resolve_link(link):
    """Linkten Entity ve Topic ID'yi tereyağından kıl çeker gibi alır."""
    clean = link.strip()
    entity = None
    topic_id = None
    
    try:
        # A) Private Link (/c/)
        if "/c/" in clean:
            # t.me/c/123456/10
            parts = clean.split("/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            try:
                entity = await userbot.get_entity(chat_id)
            except: return None, None
            
            # Sondaki sayı Topic ID mi?
            if len(parts) > 1 and parts[1].isdigit():
                topic_id = int(parts[1])

        # B) Join Link (+ veya joinchat)
        elif "+" in clean or "joinchat" in clean:
            try:
                hash_val = clean.split("+")[1] if "+" in clean else clean.split("joinchat/")[1]
                try: await userbot(ImportChatInviteRequest(hash_val)) # Gruba gir
                except UserAlreadyParticipantError: pass
                
                # Check ile al
                res = await userbot(CheckChatInviteRequest(hash_val))
                if hasattr(res, 'chat'): entity = res.chat
                elif hasattr(res, 'channel'): entity = res.channel
            except: return None, None

        # C) Public Link (@ veya t.me/)
        else:
            parts = clean.split("t.me/")[-1].split("/")
            username = parts[0]
            try:
                entity = await userbot.get_entity(username)
            except: return None, None
            
            if len(parts) > 1 and parts[1].isdigit():
                topic_id = int(parts[1])

        return entity, topic_id
    except: return None, None

# --- 7. AKILLI GÖNDERİM (Smart Send) ---
async def smart_send(msg, dst_entity, dst_topic):
    # 1. Yöntem: Direkt Kopyala (Temiz)
    try:
        if msg.media:
            await userbot.send_file(dst_entity, file=msg.media, caption=msg.text or "", reply_to=dst_topic, force_document=False)
        elif msg.text:
            await userbot.send_message(dst_entity, msg.text, reply_to=dst_topic)
        return True
    except (ChatForwardsRestrictedError, FileReferenceExpiredError):
        # 2. Yöntem: İndir & Yükle (Yasaklı Kanal)
        try:
            path = await userbot.download_media(msg)
            if path:
                await userbot.send_file(dst_entity, file=path, caption=msg.text or "", reply_to=dst_topic, force_document=False)
                os.remove(path)
                return True
        except: pass
    except: pass
    return False

# --- 8. BOT KOMUTLARI ---

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    lang = get_user_lang()
    # Kayıt aç
    check_user(event.sender_id)
    
    # Menü Butonları
    buttons = [
        [Button.inline(get_text("menu_trans", lang), b"cmd_trans"), Button.inline(get_text("menu_media", lang), b"cmd_media")],
        [Button.inline(get_text("menu_acc", lang), b"cmd_acc"), Button.inline(get_text("menu_lang", lang), b"cmd_lang")]
    ]
    await event.respond(get_text("welcome", lang), buttons=buttons)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    lang = get_user_lang()
    user_id = event.sender_id
    
    if data == "cmd_lang":
        new_lang = "EN" if lang == "TR" else "TR"
        set_user_lang(new_lang)
        await event.answer("Language Changed / Dil Değişti!", alert=True)
        # Menüyü yenile
        buttons = [
            [Button.inline(get_text("menu_trans", new_lang), b"cmd_trans"), Button.inline(get_text("menu_media", new_lang), b"cmd_media")],
            [Button.inline(get_text("menu_acc", new_lang), b"cmd_acc"), Button.inline(get_text("menu_lang", new_lang), b"cmd_lang")]
        ]
        await event.edit(get_text("welcome", new_lang), buttons=buttons)
    
    elif data == "cmd_acc":
        tier, rights = check_user(user_id)
        msg = f"👤 **Account Status:**\n\n🆔 ID: `{user_id}`\n👑 Plan: **{tier}**\n🎫 Credits: **{rights}**"
        await event.answer(msg, alert=True)
        
    elif data == "cmd_trans":
        await event.respond(get_text("syntax_trans", lang))
    
    elif data == "cmd_media":
        await event.respond(get_text("syntax_get", lang))

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    global STOP_PROCESS
    lang = get_user_lang()
    if event.sender_id in ADMINS:
        STOP_PROCESS = True
        await event.respond(get_text("stopped", lang))

# ADMIN PANELİ
@bot.on(events.NewMessage(pattern='/addvip'))
async def add_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target = int(event.text.split()[1])
        set_vip_status(target, True)
        await event.respond(f"✅ {target} -> **VIP**")
    except: await event.respond("Usage: `/addvip [ID]`")

@bot.on(events.NewMessage(pattern='/delvip'))
async def del_vip(event):
    if event.sender_id not in ADMINS: return
    try:
        target = int(event.text.split()[1])
        set_vip_status(target, False)
        await event.respond(f"❌ {target} -> **FREE**")
    except: await event.respond("Usage: `/delvip [ID]`")

# --- CORE FEATURE 1: TOPLU TRANSFER ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_process(event):
    global STOP_PROCESS
    lang = get_user_lang()
    user_id = event.sender_id
    
    if not deduct_credit(user_id):
        await event.respond(get_text("rights_err", lang)); return

    STOP_PROCESS = False
    try:
        args = event.message.text.split()
        src_link, dst_link, limit = args[1], args[2], int(args[3])
    except:
        await event.respond(get_text("syntax_trans", lang)); return

    status = await event.respond(get_text("analyzing", lang))

    # Linkleri Çöz
    src_entity, src_topic = await resolve_link(src_link)
    dst_entity, dst_topic = await resolve_link(dst_link)

    if not src_entity or not dst_entity:
        await status.edit(get_text("not_found", lang)); return

    # Rapor Başlat
    topic_name = str(dst_topic) if dst_topic else "General"
    await status.edit(get_text("started", lang).format(src_entity.title, dst_entity.title, topic_name, limit))

    count = 0
    skipped = 0
    errors = 0
    
    try:
        # Mesajları Çek (Topic varsa oradan, yoksa hepsinden)
        async for msg in userbot.iter_messages(src_entity, limit=limit, reply_to=src_topic):
            if STOP_PROCESS: break
            
            # Hafıza
            if is_processed(src_entity.id, msg.id, dst_entity.id):
                skipped += 1
                continue
            
            # Gönder
            if await smart_send(msg, dst_entity, dst_topic):
                mark_processed(src_entity.id, msg.id, dst_entity.id)
                count += 1
            else:
                errors += 1
            
            # Canlı Log
            if count % 5 == 0:
                await status.edit(get_text("transferring", lang).format(count, skipped, limit - count))
            await asyncio.sleep(1.5) # FloodWait yememek için ideal süre

        final_key = "stopped" if STOP_PROCESS else "completed"
        final_msg = get_text(final_key, lang)
        if final_key == "completed":
            final_msg = final_msg.format(count, skipped, errors)
            
        await status.edit(final_msg)

    except FloodWaitError as e:
        await status.edit(f"⏳ **FloodWait:** {e.seconds}s wait.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        await event.respond(get_text("error_gen", lang).format(e))

# --- CORE FEATURE 2: TEKLİ İNDİRME ---
@bot.on(events.NewMessage(pattern='/getmedia'))
async def get_media_process(event):
    lang = get_user_lang()
    user_id = event.sender_id
    if not deduct_credit(user_id):
        await event.respond(get_text("rights_err", lang)); return

    try: link = event.text.split()[1]
    except: await event.respond(get_text("syntax_get", lang)); return

    status = await event.respond(get_text("analyzing", lang))

    try:
        # Basit ID Çözümleme
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
        if not msg:
            await status.edit(get_text("not_found", lang)); return
        
        # İndir
        path = await userbot.download_media(msg)
        if path:
            await status.edit(get_text("media_ok", lang))
            # Bota yüklet
            await bot.send_file(event.chat_id, file=path, caption=msg.text or "")
            os.remove(path)
            await status.delete()
        else:
            await status.edit("❌ No Media Found.")

    except Exception as e:
        await status.edit(get_text("error_gen", lang).format(e))

# --- BAŞLATMA ---
def main():
    print("🚀 YaelSaver V19.0 (Commercial) Başlatılıyor...")
    keep_alive()
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
