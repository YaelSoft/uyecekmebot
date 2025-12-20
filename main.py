import os
import asyncio
import sqlite3
import logging
import re
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
# HATALI IMPORT SİLİNDİ, SADECE GEREKLİ OLANLAR KALDI:
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserAlreadyParticipant,
    InviteHashExpired, UsernameInvalid, ChannelPrivate, PeerFlood
)

# --- 1. AYARLAR ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# --- 2. WEB SERVER ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V29.0 Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE METİNLER ---
LANG = {
    "TR": {
        "welcome": "👋 **YaelSaver V29.0 Sistemine Hoşgeldiniz!**\n\n🇹🇷 **Dil:** Türkçe\n\n👇 **Komutlar:**\n🔹 `/getmedia [MesajLink]` -> İçerik İndir\n🔹 `/join [DavetLinki]` -> Userbot'u Gruba Sok\n🔹 `/transfer [K] [H] [Limit]` -> Transfer\n\n👨‍💻 **Developer:** @yasin33",
        "analyzing": "🔍 **Erişim Kontrol Ediliyor...**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Bot Yüklüyor...**",
        "not_in_chat": "🚫 **ERİŞİM YOK!**\n\nUserbot bu gizli grupta değil.\nLütfen şu komutla Userbot'u içeri alın:\n`/join https://t.me/+DavetLinki`\n\nSonra tekrar deneyin.",
        "join_success": "✅ **Başarılı!** Userbot gruba girdi.\nŞimdi `/getmedia` işlemini tekrar deneyebilirsiniz.",
        "join_fail": "❌ **Giremedim!** Link geçersiz veya banlı.",
        "join_already": "⚠️ **Zaten Üye:** Userbot bu grupta zaten var.",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "error": "❌ Hata: {}",
        "syntax_get": "⚠️ Örnek: `/getmedia https://t.me/c/123456/789`",
        "syntax_join": "⚠️ Örnek: `/join https://t.me/+AbCdEfGhIjK`"
    },
    "EN": {
        "welcome": "👋 **YaelSaver V29.0 Ready!**\n\n🇺🇸 **Lang:** English\n\n👇 **Commands:**\n🔹 `/getmedia [Link]`\n🔹 `/join [Link]`\n🔹 `/transfer`\n\n👨‍💻 **Dev:** @yasin33",
        "analyzing": "🔍 **Checking...**",
        "media_dl": "📥 **Downloading...**",
        "media_ul": "📤 **Uploading...**",
        "not_in_chat": "🚫 **NO ACCESS!**\n\nUserbot not in chat.\nUse `/join [InviteLink]` first.",
        "join_success": "✅ **Joined!** Retry command.",
        "join_fail": "❌ **Failed!**",
        "join_already": "⚠️ **Already Member.**",
        "rights_out": "❌ **No Credits!**",
        "error": "❌ Error: {}",
        "syntax_get": "⚠️ Usage: `/getmedia [Link]`",
        "syntax_join": "⚠️ Usage: `/join [Link]`"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v29.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.commit()

def get_text(key):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT value FROM settings WHERE key='lang'").fetchone()
    lang = res[0] if res else "TR"
    return LANG.get(lang, LANG["TR"]).get(key, key)

def set_lang_db(lang):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (lang,))

def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 10)", (user_id,))
    return "FREE", 10

def use_right(user_id, cost=1):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if cost > 1 and tier == "FREE": return False 
    if rights >= cost:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - ? WHERE user_id=?", (cost, user_id))
        return True
    return False

def set_vip(user_id, status):
    tier, rights = ("VIP", 99999) if status else ("FREE", 10)
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

# --- 5. İSTEMCİLER ---
init_db()
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# --- 6. ID ÇÖZÜCÜ ---
def get_private_chat_id(link):
    try:
        if "c/" in link:
            parts = link.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
            return chat_id, msg_id
    except: pass
    return None, None

# --- 7. KOMUTLAR ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    check_user(message.from_user.id)
    await message.reply(get_text("welcome"))

@bot.on_message(filters.command("lang") & filters.private)
async def lang_cmd(client, message):
    if message.from_user.id not in ADMINS: return
    try: set_lang_db(message.command[1].upper()); await message.reply("OK")
    except: pass

@bot.on_message(filters.command("addvip") & filters.private)
async def addvip(client, message):
    if message.from_user.id in ADMINS: set_vip(int(message.command[1]), True); await message.reply("VIP OK")

@bot.on_message(filters.command("delvip") & filters.private)
async def delvip(client, message):
    if message.from_user.id in ADMINS: set_vip(int(message.command[1]), False); await message.reply("FREE OK")

# --- /join ---
@bot.on_message(filters.command("join") & filters.private)
async def join_cmd(client, message):
    user_id = message.from_user.id
    if not use_right(user_id, 0): return
    
    try: link = message.command[1]
    except: await message.reply(get_text("syntax_join")); return
    
    msg = await message.reply("🕵️ ...")
    
    try:
        clean = link.replace("https://t.me/", "").replace("+", "joinchat/")
        await userbot.join_chat(clean)
        await msg.edit(get_text("join_success"))
    except UserAlreadyParticipant:
        await msg.edit(get_text("join_already"))
    except Exception as e:
        await msg.edit(get_text("join_fail") + f"\n`{e}`")

# --- /getmedia ---
@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia(client, message):
    user_id = message.from_user.id
    if not use_right(user_id, 1): await message.reply(get_text("rights_out")); return

    try: link = message.command[1]
    except: await message.reply(get_text("syntax_get")); return
    
    status = await message.reply(get_text("analyzing"))
    
    chat_id = None
    msg_id = None
    
    if "/c/" in link:
        chat_id, msg_id = get_private_chat_id(link)
    else:
        try:
            temp = link.replace("https://t.me/", "").split("/")
            username = temp[0]
            msg_id = int(temp[1])
            chat = await userbot.get_chat(username)
            chat_id = chat.id
        except: pass

    if not chat_id or not msg_id:
        await status.edit("❌ **Link Hatası:** `https://t.me/c/...` formatı kullanın.")
        return

    try:
        msg = await userbot.get_messages(chat_id, msg_id)
        if not msg or msg.empty: raise ChannelPrivate
            
    except (ChannelPrivate, PeerFlood, Exception):
        await status.edit(get_text("not_in_chat"))
        return

    try:
        await status.edit(get_text("media_dl"))
        file = await userbot.download_media(msg)
        
        if file:
            await status.edit(get_text("media_ul"))
            cap = msg.caption if msg.caption else f"📥 @yasin33"
            await bot.send_document(chat_id=user_id, document=file, caption=cap)
            os.remove(file)
            await status.delete()
        else:
            if msg.text:
                await bot.send_message(user_id, msg.text)
                await status.delete()
            else:
                await status.edit("❌ Dosya yok.")
                
    except Exception as e:
        await status.edit(f"Hata: {e}")

# --- BAŞLATMA ---
def main():
    print("🚀 V29.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
