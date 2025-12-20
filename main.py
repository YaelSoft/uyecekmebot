import os
import asyncio
import sqlite3
import logging
import re
from threading import Thread
from flask import Flask
# SADECE PYROGRAM KULLANIYORUZ
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
def home(): return "YaelSaver V37.0 (Full Pyrogram) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE METİNLER ---
# (Buradaki metinler V36 ile aynı, yer kaplamasın diye kısalttım)
LANG = {
    "TR": {
        "welcome": "👋 **YaelSaver V37.0 Hazır!**\n\n🇹🇷 **Dil:** Türkçe\n\n👇 **Menü:**",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "vip_only": "🔒 **Sadece VIP!**",
        "analyzing": "🔍 **İşleniyor...**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Gönderiliyor...**",
        "not_found": "❌ **HATA:** İçerik bulunamadı.",
        "join_success": "✅ **Girdim!**",
        "join_fail": "❌ **Giremedim!**",
        "syntax_get": "⚠️ `/getmedia [Link]`",
        "syntax_trans": "⚠️ `/transfer [K] [H] [L]`"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v37.db"
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')

def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 5)", (user_id,))
    return "FREE", 5

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
    tier, rights = ("VIP", 99999) if status else ("FREE", 5)
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

# --- 5. İSTEMCİLER ---
init_db()
# Bot İstemcisi
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# Userbot İstemcisi
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# --- 6. ÖZELLİKLER ---

# A) LINK ANALİZ (Pyrogram)
async def resolve_link_details(link):
    clean = link.strip().replace("https://t.me/", "").replace("@", "")
    chat = None
    msg_id = None
    try:
        parts = clean.split("/")
        if parts[-1].isdigit(): msg_id = int(parts[-1])
        
        if "+" in clean or "joinchat" in clean:
            # Join link
            try: await userbot.join_chat(clean)
            except: pass
            # Join linkten chat objesi almak zordur, genelde kullanıcıya "Girdim" deriz
            return None, None 
            
        elif "c/" in clean:
            # Private
            chat_id = int("-100" + parts[parts.index("c")+1])
            try: chat = await userbot.get_chat(chat_id)
            except: pass
        else:
            # Public
            username = parts[0]
            try: chat = await userbot.get_chat(username)
            except: pass
            
        return chat, msg_id
    except: return None, None

# B) START KOMUTU
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    tier, rights = check_user(message.from_user.id)
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Hesap", callback_data="acc")]
    ])
    await message.reply(f"👋 **Hoşgeldin!**\n\nPlan: {tier}\nHak: {rights}", reply_markup=buttons)

@bot.on_callback_query()
async def cb(client, callback):
    if callback.data == "acc":
        tier, rights = check_user(callback.from_user.id)
        await callback.answer(f"Plan: {tier} | Hak: {rights}", show_alert=True)

# C) GETMEDIA
@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia(client, message):
    user_id = message.from_user.id
    if not use_right(user_id, 1): await message.reply(LANG["TR"]["rights_out"]); return

    try: link = message.command[1]
    except: await message.reply(LANG["TR"]["syntax_get"]); return
    
    status = await message.reply(LANG["TR"]["analyzing"])
    
    chat, msg_id = await resolve_link_details(link)
    
    # Chat objesi yoksa ama msg_id varsa, manuel ID denemesi yapalım
    if not chat and "c/" in link:
        try:
            cid = int("-100" + link.split("c/")[1].split("/")[0])
            msg = await userbot.get_messages(cid, int(link.split("/")[-1]))
        except: msg = None
    elif chat:
        try: msg = await userbot.get_messages(chat.id, msg_id)
        except: msg = None
    else: msg = None

    if not msg or msg.empty:
        await status.edit(LANG["TR"]["not_found"])
        return

    # İndir
    await status.edit(LANG["TR"]["media_dl"])
    try:
        path = await userbot.download_media(msg)
        if path:
            await status.edit(LANG["TR"]["media_ul"])
            caption = msg.caption or "📥 @yasin33"
            await bot.send_document(user_id, path, caption=caption)
            os.remove(path)
            await status.delete()
        elif msg.text:
            await bot.send_message(user_id, msg.text)
            await status.delete()
        else:
            await status.edit("❌ Medya Yok.")
    except Exception as e:
        await status.edit(f"Hata: {e}")

# D) JOIN
@bot.on_message(filters.command("join") & filters.private)
async def join(client, message):
    try:
        link = message.command[1]
        await userbot.join_chat(link)
        await message.reply(LANG["TR"]["join_success"])
    except Exception as e:
        await message.reply(f"Hata: {e}")

# E) ADMIN
@bot.on_message(filters.command("addvip") & filters.user(ADMINS))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("VIP OK")

@bot.on_message(filters.command("delvip") & filters.user(ADMINS))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("FREE OK")

# --- 7. BAŞLATMA (HİBRİT YAPININ KALBİ) ---
async def start_bot():
    print("🚀 Bot Başlatılıyor...")
    await bot.start()
    print("✅ Bot Aktif!")
    
    print("🚀 Userbot Başlatılıyor...")
    try:
        await userbot.start()
        print("✅ Userbot Aktif!")
    except Exception as e:
        print(f"⚠️ Userbot Hatası: {e}")
        # Userbot çalışmasa bile Bot çalışmaya devam etsin
    
    # Sistemi ayakta tut
    await idle()
    
    # Kapanış
    await bot.stop()
    try: await userbot.stop()
    except: pass

if __name__ == '__main__':
    keep_alive() # Web server
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
