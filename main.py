import os
import asyncio
import sqlite3
import logging
import re
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, enums
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserAlreadyParticipant,
    InviteHashExpired, UsernameInvalid, ChannelPrivate, PeerFlood
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== 1. AYARLAR ====================
# Render'daki Environment Variables'dan çeker
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
# Admin ID'leri virgülle ayırarak yazabilirsin: 12345,67890
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# ==================== 2. WEB SERVER (RENDER İÇİN) ====================
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home(): return "YaelSaver V36.0 (Ultimate) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ==================== 3. DİL VE METİNLER ====================
LANG = {
    "TR": {
        "welcome": (
            "👋 **YaelSaver V36.0'a Hoşgeldiniz!**\n\n"
            "👤 **Paket:** {tier}\n"
            "🎫 **Hak:** {rights} Medya\n\n"
            "🛠 **NASIL KULLANILIR?**\n"
            "1. **Link Varsa:** `/getmedia https://t.me/c/xxxx/xxxx`\n"
            "2. **Link Yoksa:** Kanaldan bir mesajı bana ilet, ID'sini vereyim.\n"
            "3. **Gizli Grup:** Davet linkini bana at, otomatik gireyim.\n\n"
            "💎 **VIP:** Sınırsız Transfer hakkı."
        ),
        "id_found": "🆔 **Kanal ID Bulundu:** `{}`\nBu ID'yi transfer işlemlerinde kullanabilirsin.",
        "join_success": "✅ **Gruba Girdim!** Artık içerik çekebilirsin.",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "vip_only": "🔒 **Sadece VIP Üyeler!**",
        "analyzing": "🔍 **İşleniyor...**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Gönderiliyor...**",
        "not_found": "❌ **HATA:** İçeriğe ulaşamadım.\nUserbot grupta mı? Link doğru mu?",
        "syntax_get": "⚠️ Kullanım: `/getmedia [Link]`",
        "syntax_trans": "⚠️ Kullanım: `/transfer [KaynakID] [HedefID] [Limit]`",
        "done": "✅ **Tamamlandı**"
    },
    "EN": {
        "welcome": "👋 **Welcome!**\n\nPlan: {tier}\nRights: {rights}\n\n**Usage:**\n1. Link: `/getmedia [Link]`\n2. No Link: Forward message to get ID.\n3. Private: Send invite link to auto-join.",
        "id_found": "🆔 **Chat ID:** `{}`",
        "join_success": "✅ **Joined!**",
        "rights_out": "❌ **No Credits!**",
        "vip_only": "🔒 **VIP Only!**",
        "analyzing": "🔍 **Processing...**",
        "media_dl": "📥 **Downloading...**",
        "media_ul": "📤 **Uploading...**",
        "not_found": "❌ **Error:** Not found or access denied.",
        "syntax_get": "⚠️ Usage: `/getmedia [Link]`",
        "syntax_trans": "⚠️ Usage: `/transfer [Src] [Dst] [Limit]`",
        "done": "✅ **Done**"
    }
}

# ==================== 4. VERİTABANI ====================
DB_NAME = "yaelsaver_v36.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

def get_text(key, lang="TR", **kwargs):
    text = LANG.get(lang, LANG["TR"]).get(key, key)
    return text.format(**kwargs)

def get_user_lang():
    # Basitlik için varsayılan TR
    return "TR"

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
    if cost > 1 and tier == "FREE": return False # Free'ler transfer yapamaz
    if rights >= cost:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - ? WHERE user_id=?", (cost, user_id))
        return True
    return False

def set_vip(user_id, status):
    tier, rights = ("VIP", 99999) if status else ("FREE", 5)
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

# ==================== 5. İSTEMCİLER ====================
init_db()
# Patron Bot
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# Amele Userbot
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# ==================== 6. ÖZELLİKLER ====================

# --- A) ID DEDEKTİFİ (LİNK YOKSA) ---
@bot.on_message(filters.private & filters.forwarded)
async def id_finder(client, message):
    # Kullanıcı bir mesaj ilettiğinde çalışır
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        title = message.forward_from_chat.title
        await message.reply(
            f"📢 **Kanal Tespit Edildi!**\n\n"
            f"📛 İsim: {title}\n"
            f"🆔 ID: `{chat_id}`\n\n"
            f"Bu ID'yi `/transfer` işlemlerinde kullanabilirsin."
        )
    else:
        await message.reply("❌ Bu mesajdan ID alamadım (Gizlilik ayarı olabilir).")

# --- B) AUTO JOIN (DAVET LİNKİ) ---
@bot.on_message(filters.private & filters.regex(r"t\.me/(\+|joinchat)"))
async def auto_join(client, message):
    links = re.findall(r"https?://t\.me/(?:\+|joinchat/)([\w-]+)", message.text)
    if not links: return
    
    msg = await message.reply("🕵️ **Link Görüldü, Giriliyor...**")
    for hash_val in links:
        try:
            await userbot.join_chat(hash_val)
            await msg.edit(LANG["TR"]["join_success"])
        except UserAlreadyParticipant:
            await msg.edit("⚠️ Zaten gruptayım.")
        except Exception as e:
            await msg.edit(f"❌ Hata: {e}")

# --- C) START ---
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    tier, rights = check_user(message.from_user.id)
    
    # Menü Butonları
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Hesabım", callback_data="acc")],
        [InlineKeyboardButton("🆘 Yardım", callback_data="help")]
    ])
    
    await message.reply(get_text("welcome", tier=tier, rights=rights), reply_markup=buttons)

@bot.on_callback_query()
async def cb_handler(client, cb):
    if cb.data == "acc":
        tier, rights = check_user(cb.from_user.id)
        await cb.answer(f"Plan: {tier} | Hak: {rights}", show_alert=True)

# --- D) GETMEDIA (TEKLİ İNDİRME) ---
@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia(client, message):
    user_id = message.from_user.id
    if not use_right(user_id, 1): await message.reply(LANG["TR"]["rights_out"]); return

    try: link = message.command[1]
    except: await message.reply(LANG["TR"]["syntax_get"]); return
    
    status = await message.reply(LANG["TR"]["analyzing"])
    
    # Link Analizi
    chat_id = None
    msg_id = None
    try:
        clean = link.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean: # Private: c/12345/67
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else: # Public: user/67
            parts = clean.split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
    except:
        await status.edit("❌ Link formatı hatalı."); return

    # İndir & Yükle
    try:
        msg = await userbot.get_messages(chat_id, msg_id)
        if not msg or msg.empty: raise Exception("Empty")
        
        await status.edit(LANG["TR"]["media_dl"])
        file = await userbot.download_media(msg)
        
        if file:
            await status.edit(LANG["TR"]["media_ul"])
            caption = msg.caption or "📥 İndirildi"
            await bot.send_document(user_id, file, caption=caption)
            os.remove(file)
            await status.delete()
        elif msg.text:
            await bot.send_message(user_id, msg.text)
            await status.delete()
        else:
            await status.edit("❌ Medya Yok.")
            
    except Exception as e:
        await status.edit(f"❌ Hata: {e}\n(Userbot grupta mı?)")

# --- E) TRANSFER (VIP) ---
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(client, message):
    user_id = message.from_user.id
    if not use_right(user_id, 2): await message.reply(LANG["TR"]["vip_only"]); return
    
    try:
        # /transfer KaynakID HedefID Limit
        args = message.command
        src = args[1]
        dst = args[2]
        limit = int(args[3])
        
        # ID'ler numerikse int'e çevir
        if src.replace("-100", "").isdigit(): src = int(src)
        if dst.replace("-100", "").isdigit(): dst = int(dst)
        
    except: await message.reply(LANG["TR"]["syntax_trans"]); return

    status = await message.reply(f"🚀 **Transfer Başladı!**\n{limit} mesaj taşınıyor...")
    
    count = 0
    try:
        async for msg in userbot.get_chat_history(src, limit=limit):
            try:
                if msg.media: await msg.copy(dst, caption=msg.caption)
                elif msg.text: await userbot.send_message(dst, msg.text)
                count += 1
                await asyncio.sleep(1.5) # FloodWait koruması
            except: pass
            
        await status.edit(f"✅ **Bitti!** Toplam: {count}")
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- F) ADMIN PANEL ---
@bot.on_message(filters.command("addvip") & filters.private)
async def addvip(c, m):
    if m.from_user.id in ADMINS: 
        try: set_vip(int(m.command[1]), True); await m.reply("✅ VIP Verildi")
        except: pass

@bot.on_message(filters.command("delvip") & filters.private)
async def delvip(c, m):
    if m.from_user.id in ADMINS: 
        try: set_vip(int(m.command[1]), False); await m.reply("❌ VIP Alındı")
        except: pass

# --- BAŞLATMA ---
def main():
    print("🚀 V36.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
