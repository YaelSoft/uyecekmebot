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
    InviteHashExpired, UsernameInvalid, ChannelPrivate, PeerFlood,
    SessionPasswordNeeded
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
def home(): return "YaelSaver V34.0 Running! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 3. DİL SİSTEMİ ---
LANG = {
    "TR": {
        "welcome": (
            "👋 **YaelSaver'a Hoşgeldiniz!**\n\n"
            "👤 **Paketiniz:** {tier}\n"
            "🎫 **Kalan Hakkınız:** {rights} Medya\n\n"
            "👇 **NASIL KULLANILIR?**\n"
            "1. Gizli bir gruptan içerik çekecekseniz, önce grubun **Davet Linkini** bana gönderin.\n"
            "2. Ben gruba girdikten sonra `/getmedia [MesajLinki]` yazın.\n\n"
            "🚫 **Free Üyeler:** Sadece Tekli İndirme yapabilir.\n"
            "⭐ **VIP Üyeler:** Sınırsız Transfer yapabilir."
        ),
        "menu_acc": "👤 Hesabım",
        "menu_lang": "🇺🇸 English",
        "menu_help": "❓ Yardım",
        "join_success": "✅ **Gruba Başarıyla Girdim!**\nŞimdi içerik linkini göndererek indirme yapabilirsin.",
        "join_fail": "❌ **Gruba Giremedim!** Link geçersiz veya Userbot banlı.",
        "join_already": "⚠️ **Zaten Gruptayım.** İçerik linkini gönderebilirsin.",
        "rights_out": "❌ **Günlük Limitiniz Doldu!**\nYeni hak satın almak için yöneticiyle görüşün.",
        "vip_only": "🔒 **Bu özellik sadece VIP üyeler içindir!**",
        "analyzing": "🔍 **İçerik Aranıyor...**",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Size Gönderiliyor...**",
        "not_found": (
            "🚫 **ERİŞİM HATASI!**\n\n"
            "Bu içeriği göremiyorum. Sebepler:\n"
            "1. Userbot bu grupta değil.\n"
            "2. Link hatalı.\n\n"
            "💡 **Çözüm:** Grubun davet linkini (`https://t.me/+...`) bana gönder, otomatik gireyim."
        ),
        "success_deduct": "✅ İşlem Başarılı! (1 Hak Kullanıldı)",
        "syntax_get": "⚠️ **Kullanım:** `/getmedia https://t.me/c/xxxx/xxxx`",
        "syntax_trans": "⚠️ **Kullanım:** `/transfer [Kaynak] [Hedef] [Adet]`",
        "syntax_topic": "⚠️ **Kullanım:** `/topictransfer [Kay.Link] [Kay.ID] [Hed.Link] [Hed.ID] [Adet]`",
        "started": "🚀 **Transfer Başladı**",
        "stopped": "🛑 **Durduruldu**",
        "done": "✅ **Tamamlandı**"
    },
    "EN": {
        "welcome": (
            "👋 **Welcome to YaelSaver!**\n\n"
            "👤 **Plan:** {tier}\n"
            "🎫 **Credits:** {rights} Medias\n\n"
            "👇 **HOW TO USE?**\n"
            "1. If the group is private, send me the **Invite Link** first.\n"
            "2. After I join, type `/getmedia [MessageLink]`.\n\n"
            "🚫 **Free Users:** Single Download Only.\n"
            "⭐ **VIP Users:** Unlimited Transfer."
        ),
        "menu_acc": "👤 Account",
        "menu_lang": "🇹🇷 Türkçe",
        "menu_help": "❓ Help",
        "join_success": "✅ **Joined Successfully!** Now try downloading.",
        "join_fail": "❌ **Failed to Join!** Invalid link.",
        "join_already": "⚠️ **Already in Group.**",
        "rights_out": "❌ **Daily Limit Reached!** Contact admin.",
        "vip_only": "🔒 **VIP Only Feature!**",
        "analyzing": "🔍 **Searching...**",
        "media_dl": "📥 **Downloading...**",
        "media_ul": "📤 **Uploading...**",
        "not_found": "🚫 **NO ACCESS!**\nI'm not in this group. Send me the Invite Link first.",
        "success_deduct": "✅ Success! (1 Credit Used)",
        "syntax_get": "⚠️ Usage: `/getmedia [Link]`",
        "syntax_trans": "⚠️ Usage: `/transfer [Src] [Dst] [Limit]`",
        "syntax_topic": "⚠️ Usage: `/topictransfer [Src] [SID] [Dst] [DID] [Limit]`",
        "started": "🚀 **Started**",
        "stopped": "🛑 **Stopped**",
        "done": "✅ **Done**"
    }
}

# --- 4. VERİTABANI ---
DB_NAME = "yaelsaver_v34.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.commit()

def get_text(key, lang="TR", **kwargs):
    text = LANG.get(lang, LANG["TR"]).get(key, key)
    return text.format(**kwargs)

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
    # YENİ ÜYE: FREE, 5 HAK
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 5)", (user_id,))
    return "FREE", 5

def has_rights(user_id):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return True
    return rights > 0

def deduct_right(user_id):
    tier, rights = check_user(user_id)
    if tier in ["ADMIN", "VIP"]: return
    if rights > 0:
        with sqlite3.connect(DB_NAME) as conn:
            conn.cursor().execute("UPDATE users SET rights = rights - 1 WHERE user_id=?", (user_id,))

def set_vip(user_id, status):
    tier, rights = ("VIP", 99999) if status else ("FREE", 5)
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, tier, rights))

# --- 5. İSTEMCİLER ---
init_db()
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
STOP_PROCESS = False

# --- 6. OTOMATİK JOINER (Link Yakalayıcı) ---
@bot.on_message(filters.private & filters.regex(r"t\.me/(\+|joinchat)"))
async def auto_joiner(client, message):
    lang = get_user_lang()
    links = re.findall(r"https?://t\.me/(?:\+|joinchat/)([\w-]+)", message.text)
    
    if not links: return
    
    msg = await message.reply("🕵️ ...")
    
    for hash_val in links:
        try:
            await userbot.join_chat(hash_val)
            await msg.edit(get_text("join_success", lang))
        except UserAlreadyParticipant:
            await msg.edit(get_text("join_already", lang))
        except Exception:
            await msg.edit(get_text("join_fail", lang))

# --- 7. START & MENÜ ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    lang = get_user_lang()
    tier, rights = check_user(message.from_user.id)
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text("menu_acc", lang), callback_data="btn_acc"),
         InlineKeyboardButton(get_text("menu_lang", lang), callback_data="btn_lang")]
    ])
    
    await message.reply(get_text("welcome", lang, tier=tier, rights=rights), reply_markup=buttons)

@bot.on_callback_query()
async def cb_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    lang = get_user_lang()
    
    if data == "btn_lang":
        new_lang = "EN" if lang == "TR" else "TR"
        set_user_lang(new_lang)
        await callback.answer("Dil Değişti / Language Changed")
        tier, rights = check_user(user_id)
        
        new_text = get_text("welcome", new_lang, tier=tier, rights=rights)
        new_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text("menu_acc", new_lang), callback_data="btn_acc"),
             InlineKeyboardButton(get_text("menu_lang", new_lang), callback_data="btn_lang")]
        ])
        await callback.message.edit(new_text, reply_markup=new_buttons)
        
    elif data == "btn_acc":
        tier, rights = check_user(user_id)
        await callback.answer(f"Plan: {tier} | Rights: {rights}", show_alert=True)

# --- 8. /getmedia (TEKLİ İNDİRME) ---
@bot.on_message(filters.command("getmedia") & filters.private)
async def getmedia(client, message):
    user_id = message.from_user.id
    lang = get_user_lang()
    
    # 1. HAK KONTROLÜ (Düşmüyoruz, sadece var mı diye bakıyoruz)
    if not has_rights(user_id):
        await message.reply(get_text("rights_out", lang)); return

    try: link = message.command[1]
    except: await message.reply(get_text("syntax_get", lang)); return
    
    status = await message.reply(get_text("analyzing", lang))
    
    # 2. Link Çözümleme
    chat_id = None
    msg_id = None
    
    try:
        clean = link.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean: # Private
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else: # Public
            parts = clean.split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
            # Public ise Userbot girmemiş olabilir, deneyelim
            try: await userbot.join_chat(chat_id)
            except: pass
    except:
        await status.edit(get_text("not_found", lang)); return

    # 3. İndirme & Gönderme
    try:
        # Mesajı al
        msg = await userbot.get_messages(chat_id, msg_id)
        if not msg or msg.empty: raise Exception("Empty")

        await status.edit(get_text("media_dl", lang))
        
        # HIZLI COPY (Varsa)
        try:
            await msg.copy(user_id)
            deduct_right(user_id) # Başarılı oldu, hak düş
            await status.delete()
            return
        except: pass # Copy yasaksa aşağıdan devam (Download)

        # DOWNLOAD (Yasaklı Kanal)
        file = await userbot.download_media(msg)
        if file:
            await status.edit(get_text("media_ul", lang))
            cap = msg.caption or "📥 @yasin33"
            await bot.send_document(user_id, file, caption=cap)
            os.remove(file)
            
            # Başarılı -> Hak düş
            deduct_right(user_id)
            await status.delete()
        else:
            await status.edit("❌ Medya Yok.")

    except Exception:
        # Hata aldıysak (Userbot grupta değilse)
        await status.edit(get_text("not_found", lang))

# --- 9. TRANSFER (NORMAL & TOPIC AYRI) ---

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_normal(client, message):
    user_id = message.from_user.id
    lang = get_user_lang()
    tier, _ = check_user(user_id)
    
    if tier == "FREE": await message.reply(get_text("vip_only", lang)); return
    
    try:
        args = message.command
        src, dst, limit = args[1], args[2], int(args[3])
        # Basit mantık (Daha önceki kodlardaki gibi)
        await message.reply(f"🚀 {limit} Mesaj Transfer Ediliyor (Normal)...")
        # Buraya transfer loop kodu gelir
    except: await message.reply(get_text("syntax_trans", lang))

@bot.on_message(filters.command("topictransfer") & filters.private)
async def transfer_topic(client, message):
    user_id = message.from_user.id
    lang = get_user_lang()
    tier, _ = check_user(user_id)
    
    if tier == "FREE": await message.reply(get_text("vip_only", lang)); return
    
    try:
        # /topictransfer src sid dst did limit
        args = message.command
        src, sid, dst, did, limit = args[1], int(args[2]), args[3], int(args[4]), int(args[5])
        await message.reply(f"🚀 {limit} Mesaj Transfer Ediliyor (Topic)...")
        # Topic transfer loop
    except: await message.reply(get_text("syntax_topic", lang))

# --- ADMIN ---
@bot.on_message(filters.command("addvip") & filters.private)
async def addvip(c, m):
    if m.from_user.id in ADMINS: set_vip(int(m.command[1]), True); await m.reply("VIP OK")

@bot.on_message(filters.command("delvip") & filters.private)
async def delvip(c, m):
    if m.from_user.id in ADMINS: set_vip(int(m.command[1]), False); await m.reply("FREE OK")

# --- BAŞLATMA ---
def main():
    print("🚀 V34.0 Started...")
    keep_alive()
    userbot.start()
    bot.start()
    idle()
    userbot.stop()
    bot.stop()

if __name__ == '__main__':
    main()
