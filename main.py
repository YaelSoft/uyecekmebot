import os
import asyncio
import sqlite3
import random
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserChannelsTooMuch, 
    PeerFlood, UserNotMutualContact, UserAlreadyParticipant,
    ChatAdminRequired, UsernameInvalid, UserBannedInChannel
)

# --- 1. AYARLAR ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# --- 2. WEB SERVER ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemberAdder")

app = Flask(__name__)
@app.route('/')
def home(): return "MemberAdder V22.0 (Pyrogram Fix) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL SİSTEMİ ---
LANG = {
    "TR": {
        "welcome": "👋 **MemberAdder V22.0 Hazır!**\n\nBu bot Pyrogram tabanlıdır ve Entity hatası vermez.\n\n👇 **Komut:**\n`/basla @Kaynak @Hedef 50`\n\n🛑 **Durdur:** `/stop`",
        "analyzing": "🔍 **Gruplar Kontrol Ediliyor (Otomatik Katılım)...**",
        "started": "🚀 **BAŞLADI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n🎯 **Limit:** {}",
        "progress": "🔄 **İşleniyor...**\n✅: {}\n🙈 Gizli: {}\n⚠️ Zaten Var: {}\n📉 Kalan: {}",
        "done": "✅ **BİTTİ!**\n📦 Toplam: {}\n🙈 Gizli: {}\n⚠️ Hata: {}",
        "stopped": "🛑 **Durduruldu.**",
        "join_err": "❌ **Hata:** Userbot gruba giremedi! Link yanlış veya banlı.",
        "flood": "🚨 **SPAM KORUMASI:** Telegram bekletiyor ({} sn).",
        "peer_flood": "🚨 **LİMİT DOLDU (PeerFlood):** Hesabı dinlendir."
    }
}

# --- 4. DB ---
DB_NAME = "adder_fix.db"
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS visited (user_id INTEGER PRIMARY KEY)''')

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
# Userbot (Amele)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

STOP_PROCESS = False

# --- 6. GRUP ÇÖZÜCÜ (HATAYI ENGELLEYEN KISIM) ---
async def resolve_chat(client, link):
    """Link ne olursa olsun (ID, Username, Join Link) çözer ve Chat objesi döner."""
    try:
        # Link temizle
        clean = link.replace("https://t.me/", "").replace("@", "").strip()
        
        # 1. Önce Katılmayı Dene (Join Link veya Username)
        try:
            if "+" in clean or "joinchat" in clean:
                await client.join_chat(clean)
            elif not clean.replace("-","").isdigit(): # Sayı değilse username'dir
                await client.join_chat(clean)
        except UserAlreadyParticipant: pass # Zaten üyeyiz
        except Exception: pass # Belki private ID'dir, katılınmaz

        # 2. Chat Bilgisini Al
        chat = await client.get_chat(clean)
        return chat
        
    except Exception as e:
        logger.error(f"Chat Resolve Error: {e}")
        return None

# --- 7. KOMUTLAR ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await message.reply(LANG["TR"]["welcome"])

@bot.on_message(filters.command("stop") & filters.private)
async def stop_handler(client, message):
    global STOP_PROCESS
    if message.from_user.id in ADMINS:
        STOP_PROCESS = True
        await message.reply(LANG["TR"]["stopped"])

@bot.on_message(filters.command("basla") & filters.private)
async def start_adding(client, message):
    global STOP_PROCESS
    user_id = message.from_user.id
    if user_id not in ADMINS: return # Basitlik için sadece admin
    
    try:
        # /basla kaynak hedef 50
        src_link = message.command[1]
        dst_link = message.command[2]
        limit = int(message.command[3])
    except:
        await message.reply("⚠️ Hatalı! Örnek: `/basla @kaynak @hedef 50`")
        return

    status = await message.reply(LANG["TR"]["analyzing"])
    STOP_PROCESS = False

    # GRUPLARI ÇÖZ (Userbot Tarafında)
    src_chat = await resolve_chat(userbot, src_link)
    dst_chat = await resolve_chat(userbot, dst_link)

    if not src_chat or not dst_chat:
        await status.edit(LANG["TR"]["join_err"])
        return

    await status.edit(LANG["TR"]["started"].format(src_chat.title, dst_chat.title, limit))

    # Üye Listesi
    members = []
    try:
        async for m in userbot.get_chat_members(src_chat.id, limit=limit + 150):
            if not m.user.is_bot and not m.user.is_deleted and not is_visited(m.user.id):
                members.append(m.user)
    except Exception as e:
        await status.edit(f"❌ Liste Hatası: {e}"); return

    # Döngü
    count = 0
    privacy = 0
    already = 0
    
    for user in members:
        if STOP_PROCESS or count >= limit: break

        try:
            await userbot.add_chat_members(dst_chat.id, user.id)
            add_visited(user.id)
            count += 1
            
            if count % 5 == 0:
                await status.edit(LANG["TR"]["progress"].format(count, privacy, already, limit - count))
            
            # Rastgele Bekleme (Güvenlik)
            await asyncio.sleep(random.randint(20, 40))

        except PeerFlood:
            await status.edit(LANG["TR"]["peer_flood"])
            return
        except UserPrivacyRestricted:
            privacy += 1
            add_visited(user.id)
        except UserAlreadyParticipant:
            already += 1
            add_visited(user.id)
        except FloodWait as e:
            await status.edit(LANG["TR"]["flood"].format(e.value))
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            add_visited(user.id)
            # Kritik olmayan hataları pas geç

    await status.edit(LANG["TR"]["done"].format(count, privacy, already))

# --- BAŞLATMA ---
def main():
    print("🚀 V22.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
