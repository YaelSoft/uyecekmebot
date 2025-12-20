import os
import asyncio
import sqlite3
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserAlreadyParticipant,
    InviteHashExpired, UsernameInvalid, ChannelPrivate, PeerFlood
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
def home(): return "YaelSaver V26.0 Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL VE METİNLER ---
LANG = {
    "TR": {
        "welcome": "👋 **YaelSaver Sistemine Hoşgeldiniz!**\n\n🇹🇷 **Dil:** Türkçe\n\n👇 **Menü:**",
        "menu_get": "📥 Medya İndir",
        "menu_trans": "♻️ Transfer Yap",
        "menu_acc": "👤 Hesabım",
        "menu_lang": "🇺🇸 English",
        "free_limit": "❌ **Ücretsiz Limit Aşıldı!**\nFree üyeler günlük 10 medya indirebilir. Transfer yapamaz.\nVIP almak için yöneticiye yazın.",
        "rights_out": "❌ **Hakkınız Bitti!**",
        "analyzing": "🔍 **Bağlantı Kontrol Ediliyor...**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Yükleniyor...**",
        "not_found": "❌ **Hata:** İçerik bulunamadı veya gruba erişilemiyor!\nLinkin doğru olduğundan emin olun.",
        "error": "❌ Hata: {}",
        "syntax_get": "⚠️ **Kullanım:** `/getmedia https://t.me/c/xxxx/xxxx`",
        "syntax_trans": "⚠️ **Kullanım:** `/transfer [Kaynak] [Hedef] [Adet]`",
        "started": "🚀 **TRANSFER BAŞLADI**\n📤 Kaynak: {}\n📥 Hedef: {}\n📊 Adet: {}",
        "stopped": "🛑 **Durduruldu.**",
        "done": "✅ **TAMAMLANDI**"
    },
    "EN": {
        "welcome": "👋 **Welcome to YaelSaver!**\n\n🇺🇸 **Lang:** English\n\n👇 **Menu:**",
        "menu_get": "📥 Get Media",
        "menu_trans": "♻️ Transfer",
        "menu_acc": "👤 Account",
        "menu_lang": "🇹🇷 Türkçe",
        "free_limit": "❌ **Free Limit Reached!**\nFree users: 10 medias/day. No Transfer.\nContact admin for VIP.",
        "rights_out": "❌ **No Credits!**",
        "analyzing": "🔍 **Checking Link...**",
        "media_dl": "📥 **Downloading...**",
        "media_ul": "📤 **Uploading...**",
        "not_found": "❌ **Error:** Content not found or access denied.",
        "error": "❌ Error: {}",
        "syntax_get": "⚠️ **Usage:** `/getmedia [Link]`",
        "syntax_trans": "⚠️ **Usage:** `/transfer [Src] [Dst] [Limit]`",
        "started": "🚀 **STARTED**\n📤 Src: {}\n📥 Dst: {}\n📊 Limit: {}",
        "stopped": "🛑 **Stopped.**",
        "done": "✅ **DONE**"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v26.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # rights: Günlük kalan hak (Free için 10, VIP için 9999)
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
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

def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    # YENİ ÜYE: FREE, 10 HAK
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 10)", (user_id,))
    return "FREE", 10

def use_right(user_id, cost=1):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    
    # Free üyeler Transfer kullanamaz (Sadece getmedia)
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
STOP_PROCESS = False

# --- 6. GELİŞMİŞ LINK ÇÖZÜCÜ (NoneType Hatasını Çözen Kısım) ---
async def resolve_link_details(client, link):
    """
    Linki analiz eder: Chat Objesi ve Mesaj ID döndürür.
    Otomatik join yapar.
    """
    clean = link.strip().replace("https://t.me/", "").replace("@", "")
    chat = None
    msg_id = None
    
    try:
        # Mesaj ID'sini bul (Linkin en sonundaki sayı)
        parts = clean.split("/")
        if parts[-1].isdigit():
            msg_id = int(parts[-1])
        
        # Chat'i Bul
        # 1. Join Link (+ veya joinchat)
        if "+" in clean or "joinchat" in clean:
            # Join linklerde mesaj ID olmaz genelde ama link yapısı bozulmasın diye join kısmını ayıralım
            join_part = clean
            if msg_id:
                # Linkin sonundaki /123 kısmını atıp sadece hash'i alalım
                join_part = clean.rsplit('/', 1)[0]
                
            try: await client.join_chat(join_part)
            except UserAlreadyParticipant: pass
            chat = await client.get_chat(join_part)

        # 2. Private Link (/c/)
        elif "c/" in clean:
            # c/123456789/10
            # Chat ID: -100 + 123456789
            chat_id_str = clean.split("c/")[1].split("/")[0]
            chat_id = int("-100" + chat_id_str)
            
            # Gruba girmeyi dene (Eğer ID ile girilmiyorsa yapacak bir şey yok, userbot zaten içinde olmalı)
            try: chat = await client.get_chat(chat_id)
            except: pass

        # 3. Public Username
        else:
            # username/10
            username = parts[0]
            try: await client.join_chat(username)
            except: pass
            chat = await client.get_chat(username)
            
        return chat, msg_id

    except Exception as e:
        print(f"Resolve Error: {e}")
        return None, None

# --- 7. KOMUTLAR ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    lang = get_user_lang()
    check_user(message.from_user.id)
    
    # Butonlar
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text("menu_get", lang), callback_data="btn_get"),
         InlineKeyboardButton(get_text("menu_trans", lang), callback_data="btn_trans")],
        [InlineKeyboardButton(get_text("menu_acc", lang), callback_data="btn_acc"),
         InlineKeyboardButton(get_text("menu_lang", lang), callback_data="btn_lang")]
    ])
    await message.reply(get_text("welcome", lang), reply_markup=buttons)

@bot.on_callback_query()
async def cb_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    lang = get_user_lang()
    
    if data == "btn_lang":
        new_lang = "EN" if lang == "TR" else "TR"
        set_user_lang(new_lang)
        await callback.answer("Language Changed / Dil Değişti")
        # Menüyü Yenile
        new_text = get_text("welcome", new_lang)
        new_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text("menu_get", new_lang), callback_data="btn_get"),
             InlineKeyboardButton(get_text("menu_trans", new_lang), callback_data="btn_trans")],
            [InlineKeyboardButton(get_text("menu_acc", new_lang), callback_data="btn_acc"),
             InlineKeyboardButton(get_text("menu_lang", new_lang), callback_data="btn_lang")]
        ])
        await callback.message.edit(new_text, reply_markup=new_buttons)
        
    elif data == "btn_acc":
        tier, rights = check_user(user_id)
        text = f"👤 **Hesap:**\n👑 Plan: {tier}\n🎫 Hak: {rights}"
        await callback.answer(text, show_alert=True)
        
    elif data == "btn_get":
        await callback.message.reply(get_text("syntax_get", lang))
        
    elif data == "btn_trans":
        tier, _ = check_user(user_id)
        if tier == "FREE":
            await callback.answer(get_text("free_limit", lang), show_alert=True)
        else:
            await callback.message.reply(get_text("syntax_trans", lang))

# --- GETMEDIA (TEKLİ İNDİRME) ---
@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia_cmd(client, message):
    user_id = message.from_user.id
    lang = get_user_lang()
    
    # Free üye 1 hak yer
    if not use_right(user_id, cost=1):
        await message.reply(get_text("free_limit", lang)); return

    try: link = message.command[1]
    except: await message.reply(get_text("syntax_get", lang)); return
    
    status = await message.reply(get_text("analyzing", lang))
    
    try:
        chat, msg_id = await resolve_link_details(userbot, link)
        
        if not chat or not msg_id:
            await status.edit(get_text("not_found", lang))
            return

        # Mesajı Çek
        msg = await userbot.get_messages(chat.id, msg_id)
        
        if not msg or msg.empty:
            await status.edit(get_text("not_found", lang))
            return

        # İndir
        await status.edit(get_text("media_dl", lang))
        file_path = await userbot.download_media(msg)
        
        if file_path:
            await status.edit(get_text("media_ul", lang))
            # Gönder
            await bot.send_document(
                chat_id=user_id,
                document=file_path,
                caption=msg.caption or ""
            )
            os.remove(file_path)
            await status.delete()
        else:
            # Sadece metinse
            if msg.text:
                await bot.send_message(user_id, msg.text)
                await status.delete()
            else:
                await status.edit("❌ Medya Yok.")

    except Exception as e:
        await status.edit(get_text("error", lang).format(e))

# --- TRANSFER (VIP ONLY) ---
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_cmd(client, message):
    global STOP_PROCESS
    user_id = message.from_user.id
    lang = get_user_lang()
    
    # Transfer 2 hak yer (Sadece VIP geçebilir, use_right fonksiyonunda kontrol var)
    if not use_right(user_id, cost=2):
        await message.reply(get_text("free_limit", lang)); return
        
    try:
        args = message.command
        src_link, dst_link, limit = args[1], args[2], int(args[3])
    except: await message.reply(get_text("syntax_trans", lang)); return

    status = await message.reply(get_text("analyzing", lang))
    STOP_PROCESS = False
    
    src_chat, _ = await resolve_link_details(userbot, src_link)
    dst_chat, _ = await resolve_link_details(userbot, dst_link)
    
    if not src_chat or not dst_chat:
        await status.edit(get_text("not_found", lang)); return
        
    await status.edit(get_text("started", lang).format(src_chat.title, dst_chat.title, limit))
    
    count = 0
    try:
        async for msg in userbot.get_chat_history(src_chat.id, limit=limit):
            if STOP_PROCESS: break
            try:
                if msg.media: await msg.copy(dst_chat.id, caption=msg.caption)
                elif msg.text: await userbot.send_message(dst_chat.id, msg.text)
                count += 1
                await asyncio.sleep(2)
            except: pass
            
        await status.edit(get_text("done", lang))
    except Exception as e:
        await status.edit(get_text("error", lang).format(e))

# --- ADMIN PANEL ---
@bot.on_message(filters.command("addvip") & filters.private)
async def addvip(client, message):
    if message.from_user.id in ADMINS:
        try:
            set_vip(int(message.command[1]), True)
            await message.reply("✅ VIP Yapıldı")
        except: pass

@bot.on_message(filters.command("delvip") & filters.private)
async def delvip(client, message):
    if message.from_user.id in ADMINS:
        try:
            set_vip(int(message.command[1]), False)
            await message.reply("❌ FREE Yapıldı")
        except: pass

@bot.on_message(filters.command("stop") & filters.private)
async def stop(client, message):
    global STOP_PROCESS
    if message.from_user.id in ADMINS: STOP_PROCESS=True; await message.reply("STOP")

# --- BAŞLATMA ---
def main():
    print("🚀 V26.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
