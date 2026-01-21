import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError, PeerIdInvalid
from motor.motor_asyncio import AsyncIOMotorClient

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
MONGO_URL = os.environ.get("MONGO_URL", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# LOGLAMA
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelFinal")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael System Active 🟢"
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 MONGODB ====================
if not MONGO_URL: exit(1)
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["yael_saver_db"]
users_col = db["users"]

# --- YARDIMCI FONKSİYONLAR ---
async def get_user(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "balance": 3, "invited_by": None, "total_refs": 0}
        await users_col.insert_one(user)
    return user

async def update_balance(user_id, amount):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})

# ==================== 🔥 KRİTİK FONKSİYON: HAFIZA YÜKLEME ====================
async def reload_dialogs():
    """Userbot'un olduğu tüm kanalları hafızaya alır"""
    print("🔄 Userbot kanalları tanıyor... (Bu 10-20 saniye sürebilir)")
    try:
        # Userbot'un dialog listesini çekiyoruz ki ID'leri öğrensin
        async for dialog in userbot.get_dialogs():
            pass 
        print("✅ Userbot hafızası tazelendi! Artık kanalları tanıyor.")
    except Exception as e:
        print(f"⚠️ Hafıza tazelenirken hata: {e}")

# ==================== 🚀 KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    username = message.from_user.username
    await get_user(user_id)
    
    # Referans (Basitleştirildi)
    if len(message.command) > 1:
        try:
            ref_id = int(message.command[1])
            if str(user_id) != str(ref_id):
                u = await get_user(user_id)
                if not u.get("invited_by"):
                    await users_col.update_one({"user_id": user_id}, {"$set": {"invited_by": ref_id}})
                    await users_col.update_one({"user_id": ref_id}, {"$inc": {"balance": 2}})
        except: pass

    user_data = await get_user(user_id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Hesabım", callback_data="my_account")],
        [InlineKeyboardButton("🚀 VIP Al", url=f"https://t.me/{username if username else 'yasin33'}")],
    ])
    await message.reply(f"👋 **Selam!**\n💰 **Hakkın:** `{user_data['balance']}`", reply_markup=btn)

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.data == "my_account":
        user_id = callback.from_user.id
        u = await get_user(user_id)
        link = f"https://t.me/{client.me.username}?start={user_id}"
        await callback.message.edit(f"💰 Bakiye: {u['balance']}\n🔗 Link: `{link}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back")]]))
    elif callback.data == "back":
        await start_command(client, callback.message)

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)

    if user_data["balance"] <= 0 and user_id != OWNER_ID:
        return await message.reply("⛔ **Hakkınız Bitti!**")

    status_msg = await message.reply("⏳ **İşleniyor...**")
    
    try:
        # Link Çözümleme
        chat_id = None
        msg_id = None
        
        if "t.me/c/" in message.text:
            parts = message.text.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1].split("?")[0])
        else:
            parts = message.text.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1].split("?")[0])

        # Mesajı Getir
        try:
            target_msg = await userbot.get_messages(chat_id, msg_id)
        except PeerIdInvalid:
            # Eğer hala tanımıyorsa, son bir kez zorla tanıtmaya çalış
            try:
                await userbot.resolve_peer(chat_id)
                target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                return await status_msg.edit(f"❌ **HATA:** Userbot bu kanalda ({chat_id}) ÜYE DEĞİL.\nLütfen Userbot hesabınızla kanala katılın.")
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status_msg.edit("❌ İçerik bulunamadı.")

        file_path = await userbot.download_media(target_msg)
        
        caption = "✅ **Yael Saver**"
        if target_msg.video:
            await client.send_video(user_id, video=file_path, caption=caption, duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, photo=file_path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, document=file_path, caption=caption)

        if user_id != OWNER_ID: await update_balance(user_id, -1)
        if os.path.exists(file_path): os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit(f"❌ Hata: {e}")
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

# ==================== 🔥 BAŞLATMA (GÜÇLENDİRİLMİŞ) ====================
async def main():
    print("🤖 Başlatılıyor...")
    
    # 1. Botları Başlat
    try: await bot.start(); print("✅ Bot Aktif")
    except: pass
    
    try: await userbot.start(); print("✅ Userbot Aktif")
    except: pass

    # 2. 🔥 HAFIZA TAZELEME (SORUNU ÇÖZEN KISIM)
    await reload_dialogs()

    # 3. Bekle
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
