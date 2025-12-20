import os
import asyncio
import sqlite3
import logging
import re
from threading import Thread
from flask import Flask
# DÜZELTME BURADA: 'idle' EKLENDİ 👇
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import (
    FloodWait, UserPrivacyRestricted, UserAlreadyParticipant,
    InviteHashExpired, UsernameInvalid, ChannelPrivate, PeerFlood,
    SessionPasswordNeeded, BadRequest
)

# ==================== 1. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ADMINS", "0").split(",")))

# ==================== 2. WEB SERVER ====================
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V41.0 Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ==================== 3. DURUM YÖNETİMİ ====================
USER_STATE = {} 

# ==================== 4. DİL VE METİNLER ====================
LANG = {
    "TR": {
        "welcome": (
            "👋 **YaelSaver Premium'a Hoşgeldiniz!**\n\n"
            "👤 **Durum:** {tier}\n"
            "🎫 **Kalan Hak:** {rights}\n\n"
            "🛡️ **Gelişmiş İndirme Sihirbazı:**\n"
            "Sizi adım adım yönlendirerek gizli gruplardan içerik çekerim.\n\n"
            "👨‍💻 **Developer:** @yasin33"
        ),
        "step_1": (
            "1️⃣ **ADIM 1: Erişim Kontrolü**\n\n"
            "Önce içeriğin bulunduğu grubun **Davet Linkini** (t.me/+..) gönder.\n\n"
            "💡 *Eğer Userbot zaten o gruptaysa veya grup herkese açıksa `/gec` yazabilirsin.*"
        ),
        "step_2": (
            "2️⃣ **ADIM 2: İçerik Linki**\n\n"
            "Şimdi indirmek istediğin mesajın linkini gönder.\n"
            "🔗 Örn: `https://t.me/c/123456/789`"
        ),
        "processing_join": "🕵️ **Gruba Sızılıyor...**",
        "join_success": "✅ **Başarıyla Girildi!** Devam ediyoruz...",
        "join_exists": "⚠️ **Zaten Gruptayım.** Devam ediyoruz...",
        "join_error": "❌ **Hata:** Link geçersiz veya banlanmışım. Yine de `/gec` diyerek şansını deneyebilirsin.",
        "media_dl": "📥 **İndiriliyor...**",
        "media_ul": "📤 **Size Yükleniyor...**",
        "done": "✅ **İşlem Tamamlandı!** (1 Hak Düştü)",
        "rights_out": "❌ **Günlük Limitiniz Doldu!**\nVIP almak için yöneticiye ulaşın: @yasin33",
        "error_generic": "❌ **Hata:** {}\nLütfen tekrar deneyin.",
        "not_found": "🚫 **İçerik Bulunamadı!**\nYa grupta değilim ya da mesaj silinmiş.",
        "vip_only": "🔒 **Sadece VIP Üyeler Transfer Yapabilir!**",
        "menu_dl": "📥 İndirme Sihirbazı",
        "menu_acc": "👤 Hesabım",
        "cancel": "❌ İptal Edildi."
    }
}

# ==================== 5. VERİTABANI ====================
DB_NAME = "yaelsaver_v41.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tier TEXT, rights INTEGER)''')

def get_text(key, lang="TR", **kwargs):
    text = LANG.get(lang, LANG["TR"]).get(key, key)
    return text.format(**kwargs)

def check_user(user_id):
    if user_id in ADMINS: return "ADMIN", 999999
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT tier, rights FROM users WHERE user_id=?", (user_id,)).fetchone()
    if res: return res
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', 5)", (user_id,))
    return "FREE", 5

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

# ==================== 6. İSTEMCİLER ====================
init_db()
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 7. İŞ AKIŞI (WIZARD) ====================

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    USER_STATE.pop(message.from_user.id, None)
    tier, rights = check_user(message.from_user.id)
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text("menu_dl"), callback_data="start_wizard")],
        [InlineKeyboardButton(get_text("menu_acc"), callback_data="account")]
    ])
    await message.reply(get_text("welcome", tier=tier, rights=rights), reply_markup=buttons)

@bot.on_callback_query()
async def callbacks(client, cb):
    user_id = cb.from_user.id
    if cb.data == "account":
        tier, rights = check_user(user_id)
        await cb.answer(f"Plan: {tier} | Hak: {rights}", show_alert=True)
    elif cb.data == "start_wizard":
        tier, rights = check_user(user_id)
        if rights <= 0 and tier == "FREE":
            await cb.answer(get_text("rights_out"), show_alert=True)
            return
        USER_STATE[user_id] = "WAITING_INVITE"
        await cb.message.reply(get_text("step_1"))
        await cb.answer()

@bot.on_message(filters.private & filters.text)
async def message_handler(client, message):
    user_id = message.from_user.id
    state = USER_STATE.get(user_id)
    text = message.text.strip()
    
    # 1. ADIM: DAVET LİNKİ
    if state == "WAITING_INVITE":
        if text.lower() == "/gec":
            await message.reply(get_text("step_2"))
            USER_STATE[user_id] = "WAITING_LINK"
            return
        if "t.me/" in text:
            status = await message.reply(get_text("processing_join"))
            try:
                join_link = text.replace("https://t.me/", "").replace("+", "joinchat/")
                await userbot.join_chat(join_link)
                await status.edit(get_text("join_success"))
            except UserAlreadyParticipant:
                await status.edit(get_text("join_exists"))
            except Exception:
                await status.edit(get_text("join_error"))
            
            await message.reply(get_text("step_2"))
            USER_STATE[user_id] = "WAITING_LINK"
        else:
            await message.reply("⚠️ Link atın veya `/gec` yazın.")

    # 2. ADIM: İÇERİK LİNKİ
    elif state == "WAITING_LINK":
        if "t.me/" not in text:
            await message.reply("⚠️ Geçersiz link.")
            return
        status = await message.reply(get_text("media_dl"))
        
        chat_id = None
        msg_id = None
        try:
            clean = text.replace("https://t.me/", "").replace("@", "")
            if "c/" in clean: 
                parts = clean.split("c/")[1].split("/")
                chat_id = int("-100" + parts[0])
                msg_id = int(parts[1])
            else: 
                parts = clean.split("/")
                chat_id = parts[0]
                msg_id = int(parts[1])
        except:
            await status.edit("❌ Link çözülemedi."); return

        try:
            msg = await userbot.get_messages(chat_id, msg_id)
            if not msg or msg.empty:
                await status.edit(get_text("not_found"))
                USER_STATE.pop(user_id, None)
                return

            try:
                await msg.copy(user_id)
                await status.delete()
                deduct_right(user_id)
                await message.reply(get_text("done"))
                USER_STATE.pop(user_id, None)
                return
            except: pass 

            path = await userbot.download_media(msg)
            if path:
                await status.edit(get_text("media_ul"))
                caption = msg.caption or "📥 @yasin33"
                await bot.send_document(user_id, path, caption=caption)
                os.remove(path)
                await status.delete()
                deduct_right(user_id)
                await message.reply(get_text("done"))
            else:
                if msg.text:
                    await bot.send_message(user_id, msg.text)
                    deduct_right(user_id)
                else:
                    await status.edit("❌ Dosya türü desteklenmiyor.")
            USER_STATE.pop(user_id, None)
        except Exception as e:
            await status.edit(get_text("error_generic").format(e))
            USER_STATE.pop(user_id, None)

# --- ADMIN ---
@bot.on_message(filters.command("addvip") & filters.user(ADMINS))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅ VIP Verildi")

@bot.on_message(filters.command("delvip") & filters.user(ADMINS))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌ VIP Alındı")

# --- BAŞLATMA ---
async def start_bot():
    print("🚀 Sistem Başlatılıyor...")
    await bot.start()
    try: await userbot.start(); print("✅ Userbot Aktif")
    except Exception as e: print(f"⚠️ Userbot Hatası: {e}")
    # DÜZELTME BURADA YAPILDI:
    await idle()
    await bot.stop()
    try: await userbot.stop()
    except: pass

if __name__ == '__main__':
    keep_alive()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
