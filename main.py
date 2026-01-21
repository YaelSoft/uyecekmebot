import os
import json
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) # YEDEKLEME KANALI (ŞART!)

# DOSYA AYARLARI
DB_FILE = "users_backup.json" 
START_BALANCE = 3
REF_REWARD = 2

# LOGLAMA
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelTGDB")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael System Active (TG-DB Mode) 🟢"
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 TELEGRAM VERİTABANI SİSTEMİ ====================

# 1. VERİLERİ YÜKLE (KANALDAN ÇEK)
async def restore_data():
    if LOG_CHANNEL == 0: return {}
    print("📥 Veritabanı kanaldan aranıyor...")
    try:
        # Kanalın geçmişine bak, son "backup.json" dosyasını bul
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=20):
            if msg.document and msg.document.file_name == "yael_db.json":
                print("✅ Yedek bulundu! İndiriliyor...")
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f:
                    data = json.load(f)
                print(f"✅ {len(data)} Kullanıcı verisi yüklendi.")
                return data
    except Exception as e:
        print(f"⚠️ Yedek yüklenemedi (İlk kez çalışıyor olabilir): {e}")
    
    return {} # Bulamazsa boş başla

# 2. VERİLERİ KAYDET (KANALA AT)
async def backup_data(data):
    if LOG_CHANNEL == 0: return
    try:
        # Önce dosyaya yaz
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
        
        # Sonra kanala gönder
        await bot.send_document(
            LOG_CHANNEL, 
            document=DB_FILE, 
            file_name="yael_db.json",
            caption=f"💾 **Sistem Yedeği**\n⏰ Zaman: {asyncio.get_event_loop().time()}"
        )
    except Exception as e:
        print(f"⚠️ Yedekleme hatası: {e}")

# Global Veri Değişkeni
db_cache = {}

# --- YARDIMCI FONKSİYONLAR ---
async def get_user(user_id):
    uid = str(user_id)
    if uid not in db_cache:
        db_cache[uid] = {"balance": START_BALANCE, "invited_by": None}
        await backup_data(db_cache) # Yeni üye gelince yedekle
    return db_cache[uid]

async def update_balance(user_id, amount):
    uid = str(user_id)
    if uid in db_cache:
        db_cache[uid]["balance"] += amount
        await backup_data(db_cache) # Bakiye değişince yedekle

async def add_ref(user_id, referrer_id):
    uid = str(user_id)
    rid = str(referrer_id)
    if uid == rid or uid not in db_cache: return False
    
    if db_cache[uid].get("invited_by") is None:
        db_cache[uid]["invited_by"] = rid
        if rid in db_cache:
            db_cache[rid]["balance"] += REF_REWARD
        await backup_data(db_cache) # Referans olunca yedekle
        return True
    return False

# ==================== 🚀 KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    await get_user(user_id) # Kaydet
    
    # Referans
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if await add_ref(user_id, ref_id):
                try: await client.send_message(int(ref_id), f"🎉 +{REF_REWARD} Hak kazandın!")
                except: pass
        except: pass

    u = db_cache.get(str(user_id), {"balance": 0})
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Bakiye", callback_data="stats")],
        [InlineKeyboardButton("🚀 VIP Al", url="https://t.me/yasin33")]
    ])
    await message.reply(f"👋 **Selam!**\n💰 Hakkın: `{u['balance']}`\n\nLink gönder gelsin.", reply_markup=btn)

@bot.on_callback_query()
async def cb(client, callback):
    if callback.data == "stats":
        user_id = callback.from_user.id
        u = db_cache.get(str(user_id), {"balance": 0})
        link = f"https://t.me/{client.me.username}?start={user_id}"
        await callback.message.edit(f"💰 Bakiye: {u['balance']}\n🔗 Link: `{link}`")

# ==================== 🔥 İŞLEM MERKEZİ ====================
@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    user_id = message.from_user.id
    u = await get_user(user_id)

    # Bakiye Kontrol
    if u["balance"] <= 0 and user_id != OWNER_ID:
        return await message.reply("⛔ Hakkın bitti! Arkadaş davet et.")

    status = await message.reply("⏳ **Analiz Ediliyor...**")
    
    try:
        # Link Parçalama
        link = message.text
        chat_id = None
        msg_id = None
        
        if "t.me/c/" in link:
            parts = link.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1].split("?")[0])
        else:
            parts = link.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1].split("?")[0])

        # 🔥 USERBOT İŞLEMİ
        target_msg = None
        try:
            target_msg = await userbot.get_messages(chat_id, msg_id)
        except:
            # Bulamazsa, public ise katılmayı dene
            if isinstance(chat_id, str): 
                try:
                    await userbot.join_chat(chat_id)
                    target_msg = await userbot.get_messages(chat_id, msg_id)
                except: pass
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status.edit("❌ **Hata:** Userbot kanalı göremiyor.\nLütfen Userbot hesabınızla o kanala katılın.")

        await status.edit("⬇️ **İndiriliyor...**")
        path = await userbot.download_media(target_msg)
        
        # 🔥 VİDEO YEDEĞİ (LOG KANALI)
        if LOG_CHANNEL != 0:
            try:
                await client.send_document(LOG_CHANNEL, path, caption=f"👤 User: {user_id}\n🔗 {link}")
            except: pass

        # Kullanıcıya Gönder
        await status.edit("⬆️ **Yükleniyor...**")
        caption = "✅ **Yael Saver**"
        
        if target_msg.video:
            await client.send_video(user_id, path, caption=caption, duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, path, caption=caption)

        # Bakiye Düş
        if user_id != OWNER_ID: await update_balance(user_id, -1)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")
        if 'path' in locals() and os.path.exists(path): os.remove(path)

# ==================== 🔥 BAŞLATMA ====================
async def main():
    global db_cache
    print("🤖 Sistem Başlatılıyor...")
    
    try: await bot.start()
    except: pass
    try: await userbot.start()
    except: pass
    
    # 🔥 EN KRİTİK NOKTA: AÇILIRKEN YEDEĞİ GERİ YÜKLE
    db_cache = await restore_data()
    
    print("✅ YAEL SAVER AKTİF (TG-DB MODE)")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
