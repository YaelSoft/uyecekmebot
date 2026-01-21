import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError, PeerIdInvalid, ChannelInvalid, ChannelPrivate
from motor.motor_asyncio import AsyncIOMotorClient

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
MONGO_URL = os.environ.get("MONGO_URL", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# REFERANS AYARLARI
START_BALANCE = 3       
REF_REWARD = 2          

# LOGLAMA
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelAntiCrash")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver System Online 🟢"
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 MONGODB ====================
if not MONGO_URL:
    print("❌ HATA: MONGO_URL EKLENMEMİŞ!")
    exit(1)

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["yael_saver_db"]
users_col = db["users"]

# --- FONKSİYONLAR ---
async def get_user(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "balance": START_BALANCE, "invited_by": None, "total_refs": 0}
        await users_col.insert_one(user)
    return user

async def update_balance(user_id, amount):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})

async def add_ref(user_id, referrer_id, client):
    if str(user_id) == str(referrer_id): return False
    user = await get_user(user_id)
    if user.get("invited_by"): return False 
    try:
        u_info = await client.get_users(user_id)
        if not u_info.username: return False 
    except: return False

    await users_col.update_one({"user_id": user_id}, {"$set": {"invited_by": referrer_id}})
    await users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": REF_REWARD, "total_refs": 1}})
    return True

# ==================== 🚀 KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.command
    await get_user(user_id)
    
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            success = await add_ref(user_id, referrer_id, client)
            if success:
                try:
                    await client.send_message(referrer_id, f"🎁 **TEBRİKLER!**\nArkadaşın geldi, +{REF_REWARD} Hak kazandın!")
                except: pass
        except: pass

    user_data = await get_user(user_id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Hesabım", callback_data="my_account")],
        [InlineKeyboardButton("🚀 VIP Al", url=f"https://t.me/{username if username else 'yasin33'}")],
        [InlineKeyboardButton("❓ Yardım", callback_data="help")]
    ])
    await message.reply(f"👋 **Selam {message.from_user.first_name}!**\n💰 **Hakkın:** `{user_data['balance']}`", reply_markup=btn)

@bot.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    user_data = await get_user(user_id)

    if data == "my_account":
        ref_link = f"https://t.me/{client.me.username}?start={user_id}"
        await callback.message.edit(f"💰 **Bakiye:** `{user_data['balance']}`\n🔗 **Link:**\n`{ref_link}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "help":
        await callback.message.edit("Linki yapıştır, gerisini bana bırak.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "back_home":
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

        # 🔥 KRİTİK NOKTA: KANAL KONTROLÜ
        # Önce mesajı getirmeye çalış, hata verirse yakala
        try:
            target_msg = await userbot.get_messages(chat_id, msg_id)
        except (PeerIdInvalid, ChannelInvalid, ChannelPrivate):
            await status_msg.edit(
                f"❌ **ERİŞİM HATASI!**\n\n"
                f"Userbot bu kanalı tanımıyor (`{chat_id}`).\n"
                f"Lütfen Userbot hesabınızla bu kanala katılın veya mesaj geçmişini güncelleyin."
            )
            return
        except Exception as e:
            await status_msg.edit(f"❌ Mesaj alınamadı: {e}")
            return
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status_msg.edit("❌ İçerik bulunamadı.")

        file_path = await userbot.download_media(target_msg)
        
        if target_msg.video:
            await client.send_video(user_id, video=file_path, caption="✅ Yael Saver", duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, photo=file_path, caption="✅ Yael Saver")
        elif target_msg.document:
            await client.send_document(user_id, document=file_path, caption="✅ Yael Saver")

        if user_id != OWNER_ID:
            await update_balance(user_id, -1)
            
        if os.path.exists(file_path): os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        # Genel Hata Yakalayıcı (Bot Çökmez, Hata Yazar)
        error_text = str(e)
        if "Peer id invalid" in error_text:
            await status_msg.edit("❌ **Hata:** Userbot kanalı bulamıyor. Kanala katıldığından emin ol.")
        else:
            await status_msg.edit(f"❌ **Bilinmeyen Hata:** {e}")
            
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

# ==================== 🔥 BAŞLATMA ====================
async def main():
    print("🤖 Başlatılıyor...")
    try: await bot.start()
    except: pass
    try: await userbot.start()
    except: pass
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
