import os
import asyncio
import sqlite3
import random
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserChannelsTooMuch, 
    PeerFlood, UserNotMutualContact, UserAlreadyParticipant,
    ChatAdminRequired
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 1. AYARLAR (Müşteri Burayı Dolduracak) ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Userbot Session String (Pyrogram)
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# --- 2. WEB SERVER (7/24) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemberAdder")

app = Flask(__name__)
@app.route('/')
def home(): return "MemberAdder V20.0 (Sales Edition) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL SİSTEMİ (TR/EN) ---
LANG = {
    "TR": {
        "welcome": "👋 **MemberAdder V20.0 Paneline Hoşgeldiniz!**\n\n🇹🇷 **Dil:** Türkçe\n\n🤖 **Durum:** Sistem Aktif\n\n👇 **Komutlar:**\n🔹 `/basla @kaynak @hedef 50` -> Üye Çek\n🔹 `/status` -> Hesap Durumu\n🔹 `/lang EN` -> İngilizce Yap\n\n👮‍♂️ **Admin:** `/addvip`, `/delvip`",
        "rights_err": "❌ **Lisans Hatası:** Hakkınız bitmiş veya üyeliğiniz yok. Satıcı ile görüşün.",
        "started": "🚀 **İŞLEM BAŞLATILDI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n🎯 **Hedeflenen:** {} Kişi\n\n*Userbot çalışmaya başladı...*",
        "analyzing": "🔍 **Gruplar Analiz Ediliyor ve Giriş Yapılıyor...**",
        "progress": "🔄 **İşleniyor...**\n\n✅ **Eklenen:** {}\n🙈 **Gizlilik (Atlandı):** {}\n⚠️ **Zaten Ekli:** {}\n📉 **Kalan:** {}",
        "done": "✅ **İŞLEM TAMAMLANDI**\n\n📦 Toplam Eklenen: {}\n🙈 Gizlilik: {}\n⚠️ Hata/Zaten: {}\n\n*Hizmetimizi tercih ettiğiniz için teşekkürler.*",
        "stopped": "🛑 **İşlem Durduruldu!**",
        "peer_flood": "🚨 **SPAM KORUMASI DEVREYE GİRDİ!**\n\nTelegram bu hesabı geçici olarak kısıtladı (PeerFlood).\nBot güvenli modda durduruldu.",
        "join_err": "❌ **Hata:** Userbot kaynak veya hedef gruba giremedi! Linkleri kontrol et veya banlı olabilir.",
        "admin_err": "❌ **Hata:** Hedef grupta üye ekleme kapalı! Userbot'u admin yapmalısınız.",
        "syntax": "⚠️ **Hatalı Kullanım!**\nÖrnek: `/basla @kaynak @hedef 50`"
    },
    "EN": {
        "welcome": "👋 **Welcome to MemberAdder V20.0!**\n\n🇺🇸 **Lang:** English\n\n🤖 **Status:** Online\n\n👇 **Commands:**\n🔹 `/basla @src @dst 50` -> Start Adding\n🔹 `/status` -> Check Credits\n🔹 `/lang TR` -> Turkish\n\n👮‍♂️ **Admin:** `/addvip`, `/delvip`",
        "rights_err": "❌ **License Error:** No credits left. Contact support.",
        "started": "🚀 **PROCESS STARTED**\n\n📤 **Source:** {}\n📥 **Dest:** {}\n🎯 **Target:** {} Users",
        "analyzing": "🔍 **Analyzing & Joining Groups...**",
        "progress": "🔄 **Processing...**\n\n✅ **Added:** {}\n🙈 **Privacy:** {}\n⚠️ **Already:** {}\n📉 **Left:** {}",
        "done": "✅ **COMPLETED**\n\n📦 Total Added: {}\n🙈 Privacy: {}\n⚠️ Errors: {}",
        "stopped": "🛑 **Stopped by User!**",
        "peer_flood": "🚨 **SPAM PROTECTION TRIGGERED!**\n\nTelegram limited this account (PeerFlood).\nStopped for safety.",
        "join_err": "❌ **Error:** Userbot cannot join source or dest group!",
        "admin_err": "❌ **Error:** Adding members is restricted in dest group! Make Userbot admin.",
        "syntax": "⚠️ **Usage:** `/basla @src @dst 50`"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "adder_v20.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS visited (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.commit()

def get_text(key, lang="TR"): return LANG.get(lang, LANG["TR"]).get(key, key)

def get_lang():
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT value FROM settings WHERE key='lang'").fetchone()
    return res[0] if res else "TR"

def set_lang(lang):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (lang,))

# Lisans Sistemi
def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    # Varsayılan: FREE, 100 Üye hakkı
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 100)", (user_id,))
    return "FREE", 100

def use_credit(user_id, amount):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if rights >= amount:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - ? WHERE user_id=?", (amount, user_id))
        return True
    return False

# Hafıza (Daha önce denenenleri atla)
def is_visited(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT user_id FROM visited WHERE user_id=?", (user_id,)).fetchone()
    return res is not None

def add_visited(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR IGNORE INTO visited VALUES (?)", (user_id,))

# --- 5. İSTEMCİLER ---
init_db()
# Bot (Patron)
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# Userbot (Amele) - Pyrogram Session String
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

STOP_PROCESS = False

# --- 6. GRUBA GİRME FONKSİYONU ---
async def join_chat_safe(client, link):
    try:
        if "+" in link or "joinchat" in link:
            # Davet linki ise katıl
            try: await client.join_chat(link)
            except UserAlreadyParticipant: pass
            
            chat = await client.get_chat(link)
            return chat
        else:
            # Username ise
            username = link.split("/")[-1]
            try: await client.join_chat(username)
            except UserAlreadyParticipant: pass
            
            chat = await client.get_chat(username)
            return chat
    except Exception as e:
        logger.error(f"Join Error: {e}")
        return None

# --- 7. KOMUTLAR ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    check_user(message.from_user.id)
    lang = get_lang()
    await message.reply(get_text("welcome", lang))

@bot.on_message(filters.command("lang") & filters.private)
async def lang_handler(client, message):
    if message.from_user.id not in ADMINS: return
    try:
        target = message.command[1].upper()
        if target in ["TR", "EN"]:
            set_lang(target)
            await message.reply(f"Language: {target}")
    except: await message.reply("/lang TR or /lang EN")

@bot.on_message(filters.command("stop") & filters.private)
async def stop_handler(client, message):
    global STOP_PROCESS
    if message.from_user.id in ADMINS:
        STOP_PROCESS = True
        await message.reply("🛑 STOP!")

# --- ANA İŞLEM: ÜYE ÇEKME ---
@bot.on_message(filters.command("basla") & filters.private)
async def add_members(client, message):
    global STOP_PROCESS
    lang = get_lang()
    user_id = message.from_user.id
    
    # Argüman Kontrolü
    try:
        # /basla @src @dst 50
        src_input = message.command[1]
        dst_input = message.command[2]
        limit = int(message.command[3])
    except:
        await message.reply(get_text("syntax", lang)); return

    # Bakiye Kontrolü (1 üye = 1 kredi mantığı yerine işlem başı kontrol yapıyoruz burada)
    if not use_credit(user_id, limit):
        await message.reply(get_text("rights_err", lang)); return

    status_msg = await message.reply(get_text("analyzing", lang))
    STOP_PROCESS = False

    # 1. Userbot ile Gruplara Gir/Kontrol Et
    src_chat = await join_chat_safe(userbot, src_input)
    dst_chat = await join_chat_safe(userbot, dst_input)

    if not src_chat or not dst_chat:
        await status_msg.edit(get_text("join_err", lang)); return

    await status_msg.edit(get_text("started", lang).format(src_chat.title, dst_chat.title, limit))

    # 2. Üye Listesini Çek (Filtreli)
    members = []
    try:
        # Daha fazla çekelim ki gizlilikten elenenler olunca hedef sayıya ulaşalım
        async for member in userbot.get_chat_members(src_chat.id, limit=limit + 200):
            user = member.user
            if not user.is_bot and not user.is_deleted and not is_visited(user.id):
                members.append(user)
    except Exception as e:
        await status_msg.edit(f"❌ Liste hatası: {e}"); return

    # 3. Ekleme Döngüsü
    stats = {"success": 0, "privacy": 0, "already": 0, "flood": 0}
    
    for user in members:
        if STOP_PROCESS: break
        if stats["success"] >= limit: break

        try:
            await userbot.add_chat_members(dst_chat.id, user.id)
            add_visited(user.id)
            stats["success"] += 1
            
            # Güncelleme
            if stats["success"] % 5 == 0:
                await status_msg.edit(get_text("progress", lang).format(stats["success"], stats["privacy"], stats["already"], limit - stats["success"]))
            
            # Bekleme (Güvenlik için Rastgele)
            await asyncio.sleep(random.randint(30, 50))

        except UserPrivacyRestricted:
            stats["privacy"] += 1
            add_visited(user.id)
        except UserAlreadyParticipant:
            stats["already"] += 1
            add_visited(user.id)
        except PeerFlood:
            await status_msg.edit(get_text("peer_flood", lang))
            return # Direkt çık
        except FloodWait as e:
            await asyncio.sleep(e.value + 5)
        except ChatAdminRequired:
            await status_msg.edit(get_text("admin_err", lang))
            return
        except Exception as e:
            print(f"Hata: {e}")
            add_visited(user.id) # Hata vereni de geç

    # 4. Bitiş
    final_key = "stopped" if STOP_PROCESS else "done"
    text = get_text(final_key, lang)
    if final_key == "done":
        text = text.format(stats["success"], stats["privacy"], stats["already"])
    
    await status_msg.edit(text)

# --- BAŞLATMA ---
def main():
    print("🚀 MemberAdder V20.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
