import os
import asyncio
import sqlite3
import logging
import re
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserChannelsTooMuch, 
    PeerFlood, UserAlreadyParticipant, InviteHashExpired,
    UsernameInvalid, ChannelPrivate
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
def home(): return "YaelSaver V25.0 (Pyrogram Ultimate) Online! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL SİSTEMİ ---
LANG = {
    "TR": {
        "welcome": "👋 **YaelSaver V25.0 Hazır!**\n\n🇹🇷 **Dil:** Türkçe\n\n👇 **Komutlar:**\n🔹 `/transfer [Kaynak] [Hedef] [Adet]`\n🔹 `/getmedia [Link]`\n🔹 `/status`\n🔹 `/lang EN`\n\n💡 **İpucu:** Linkin sonunda `/55` gibi sayı varsa onu Topic ID sayarım.",
        "analyzing": "🔍 **Bağlantılar Kontrol Ediliyor & Otomatik Katılım...**",
        "started": "🚀 **BAŞLADI**\n\n📤 **Kaynak:** {}\n📥 **Hedef:** {}\n📂 **Hedef Topic:** {}\n📊 **Limit:** {}",
        "progress": "🔄 **Aktarılıyor...**\n✅: {}\n⏭️: {}\n📉: {}",
        "done": "✅ **BİTTİ!**\n📦 Toplam: {}\n⏭️ Atlanan: {}\n⚠️ Hata: {}",
        "stopped": "🛑 **Durduruldu.**",
        "error": "❌ Hata: {}",
        "not_found": "❌ **Hata:** Gruba erişilemedi! Link kırık veya Userbot banlı.",
        "rights_out": "❌ **Hakkınız Bitti!** Admin ile görüşün.",
        "media_ok": "✅ **İndirildi, Gönderiliyor...**",
        "syntax": "⚠️ Hatalı! Örnek:\n`/transfer https://t.me/kaynak/10 https://t.me/hedef/5 100`"
    },
    "EN": { "welcome": "Ready.", "analyzing": "Analyzing...", "started": "Started", "progress": "Progress...", "done": "Done", "stopped": "Stopped", "error": "Error", "not_found": "Not Found", "rights_out": "No Credits", "media_ok": "OK", "syntax": "Syntax Error" }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v25.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS history (src_chat INTEGER, msg_id INTEGER, dst_chat INTEGER)''')
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

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
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 3)", (user_id,))
    return "FREE", 3

def use_right(user_id):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    if rights > 0:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - 1 WHERE user_id=?", (user_id,))
        return True
    return False

def set_vip(user_id, status):
    tier, rights = ("VIP", 99999) if status else ("FREE", 3)
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

def check_history(src, msg, dst):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT * FROM history WHERE src_chat=? AND msg_id=? AND dst_chat=?", (src, msg, dst)).fetchone()
    return res is not None

def add_history(src, msg, dst):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO history VALUES (?, ?, ?)", (src, msg, dst))

# --- 5. İSTEMCİLER ---
init_db()
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
STOP_PROCESS = False

# --- 6. GELİŞMİŞ LINK ANALİZİ (Entity Hatalarını Çözen Kısım) ---
async def analyze_link(link):
    """
    Linki parçalar, Userbot'u gruba sokar, Chat ID ve Topic ID'yi döndürür.
    Hata vermez, dener.
    """
    clean_link = link.strip().replace(" ", "")
    topic_id = None
    chat = None
    
    # Topic ID Tespiti (Linkin sonu rakam mı?)
    # Örn: https://t.me/c/12345/99 -> 99
    parts = clean_link.split("/")
    if len(parts) > 1 and parts[-1].isdigit():
        topic_id = int(parts[-1])
        # Linki temizle (chat'i bulmak için ID kısmını at)
        # Ama join linki ise (t.me/+Abc/99) join linki bozulmasın diye dikkatli olmalıyız
        if "+" not in clean_link and "joinchat" not in clean_link:
             # Eğer public username/10 ise -> username
             # Eğer private c/123/10 ise -> c/123
             pass 

    try:
        # 1. Join Link (+ veya joinchat)
        if "+" in clean_link or "joinchat" in clean_link:
            # Topic ID'yi linkten sıyırıp sadece join kısmını alalım
            join_part = clean_link
            if topic_id: 
                join_part = clean_link.rsplit('/', 1)[0] # Son slash'tan öncesini al

            try: await userbot.join_chat(join_part)
            except UserAlreadyParticipant: pass
            
            chat = await userbot.get_chat(join_part)

        # 2. Private Link (/c/)
        elif "/c/" in clean_link:
            # Format: t.me/c/1234567890/10
            # Pyrogram ID: -100 + 1234567890
            temp_parts = clean_link.split("/c/")[1].split("/")
            chat_id_raw = temp_parts[0]
            chat_id = int("-100" + chat_id_raw)
            try: chat = await userbot.get_chat(chat_id)
            except: pass # Erişim yoksa None döner

        # 3. Public Username (@ veya t.me/)
        else:
            username = parts[-2] if topic_id else parts[-1]
            try: await userbot.join_chat(username)
            except: pass
            chat = await userbot.get_chat(username)
            
        return chat, topic_id
        
    except Exception as e:
        print(f"Analyze Error: {e}")
        return None, None

# --- 7. AKTARIM ---
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_cmd(client, message):
    global STOP_PROCESS
    user_id = message.from_user.id
    if not use_right(user_id): await message.reply(get_text("rights_out")); return
    
    try:
        # /transfer src dst limit
        args = message.command
        src_link, dst_link, limit = args[1], args[2], min(int(args[3]), 2000)
    except: await message.reply(get_text("syntax")); return

    status = await message.reply(get_text("analyzing"))
    STOP_PROCESS = False

    # Analiz
    src_chat, src_topic = await analyze_link(src_link)
    dst_chat, dst_topic = await analyze_link(dst_link)

    if not src_chat or not dst_chat:
        await status.edit(get_text("not_found")); return

    dst_info = f"{dst_topic}" if dst_topic else "Genel"
    await status.edit(get_text("started").format(src_chat.title, dst_chat.title, dst_info, limit))

    count = 0
    skipped = 0
    errors = 0

    try:
        # Pyrogram History
        async for msg in userbot.get_chat_history(src_chat.id, limit=limit):
            if STOP_PROCESS: break
            
            # Eğer kaynak linkte Topic belirttiysek, sadece o topic'ten gelenleri alalım
            # Forum gruplarında msg.reply_to_top_message_id veya message_thread_id kullanılır
            # Ama basitlik ve hız için şimdilik ID'si uyanları alacağız.
            
            # Hafıza
            if check_history(src_chat.id, msg.id, dst_chat.id):
                skipped += 1
                continue

            # Gönder
            try:
                # Akıllı Kopyalama (İletildi yazısı olmadan)
                if msg.media:
                    # Caption varsa al
                    cap = msg.caption if msg.caption else ""
                    # Topic'e gönderiyorsak message_thread_id kullan
                    if dst_topic:
                        await msg.copy(dst_chat.id, caption=cap, message_thread_id=dst_topic)
                    else:
                        await msg.copy(dst_chat.id, caption=cap)
                elif msg.text:
                    if dst_topic:
                        await userbot.send_message(dst_chat.id, msg.text, message_thread_id=dst_topic)
                    else:
                        await userbot.send_message(dst_chat.id, msg.text)

                add_history(src_chat.id, msg.id, dst_chat.id)
                count += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
            except Exception as e:
                errors += 1
            
            if count % 5 == 0:
                await status.edit(get_text("progress").format(count, skipped, limit - count))
            await asyncio.sleep(1.5)

        final = get_text("stopped") if STOP_PROCESS else get_text("done").format(count, skipped, errors)
        await status.edit(final)

    except Exception as e:
        await status.edit(get_text("error").format(e))

# --- DİĞER KOMUTLAR ---
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    check_user(message.from_user.id)
    await message.reply(get_text("welcome"))

@bot.on_message(filters.command("lang") & filters.private)
async def lang_cmd(client, message):
    if message.from_user.id not in ADMINS: return
    try: set_lang_db(message.command[1].upper()); await message.reply("OK")
    except: pass

@bot.on_message(filters.command("status") & filters.private)
async def status_cmd(client, message):
    tier, rights = check_user(message.from_user.id)
    await message.reply(f"📊 {tier} - {rights}")

@bot.on_message(filters.command("addvip") & filters.private)
async def addvip(client, message):
    if message.from_user.id in ADMINS: set_vip(int(message.command[1]), True); await message.reply("VIP OK")

@bot.on_message(filters.command("delvip") & filters.private)
async def delvip(client, message):
    if message.from_user.id in ADMINS: set_vip(int(message.command[1]), False); await message.reply("FREE OK")

@bot.on_message(filters.command("stop") & filters.private)
async def stop_cmd(client, message):
    global STOP_PROCESS
    if message.from_user.id in ADMINS: STOP_PROCESS = True; await message.reply(get_text("stopped"))

@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia(client, message):
    user_id = message.from_user.id
    if not use_right(user_id): await message.reply(get_text("rights_out")); return
    try:
        link = message.command[1]
        chat, _ = await analyze_link(link) # Chat'i bul
        msg_id = int(link.split("/")[-1]) # ID'yi al
        
        status = await message.reply(get_text("analyzing"))
        msg = await userbot.get_messages(chat.id, msg_id)
        
        # İndir
        file = await userbot.download_media(msg)
        if file:
            await status.edit(get_text("media_ok"))
            await bot.send_document(user_id, file, caption=msg.caption)
            os.remove(file)
            await status.delete()
        else: await status.edit("Medya Yok")
    except Exception as e: await status.edit(f"Hata: {e}")

# --- BAŞLATMA ---
def main():
    print("🚀 YaelSaver V25.0 (Pyrogram) Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
