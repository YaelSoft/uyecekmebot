import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# ==================== ⚙️ AYARLAR (RENDER) ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
MONGO_URL = os.environ.get("MONGO_URL", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0")) # 🔥 EKLENDİ: SENİN ID'N

# REFERANS AYARLARI
START_BALANCE = 3       
REF_REWARD = 2          

# LOGLAMA
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelProBot")

# ==================== 🌐 WEB SERVER (ARKAPLAN) ====================
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

# ==================== 👑 ADMIN KOMUTLARI (YENİ) ====================

@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    """Sadece Owner'ın göreceği panel"""
    count = await users_col.count_documents({})
    text = (
        f"👑 **YÖNETİCİ PANELİ**\n\n"
        f"👥 **Toplam Kullanıcı:** {count}\n"
        f"⚙️ **Sistem:** Aktif\n\n"
        f"__Bakiye eklemek için:__\n`/add 123456 10` (ID ve Miktar)"
    )
    await message.reply(text)

@bot.on_message(filters.command("add") & filters.user(OWNER_ID))
async def admin_add_balance(client, message):
    """Elle bakiye ekleme komutu"""
    try:
        _, target_id, amount = message.text.split()
        target_id = int(target_id)
        amount = int(amount)
        
        await update_balance(target_id, amount)
        await message.reply(f"✅ `{target_id}` kullanıcısına **{amount} hak** eklendi.")
        
        # Kullanıcıya haber ver
        try:
            await client.send_message(target_id, f"🎁 **YÖNETİCİ HEDİYESİ!**\nHesabına +{amount} hak yüklendi.")
        except: pass
    except:
        await message.reply("❌ Hatalı kullanım! Örnek: `/add 12345678 50`")

# ==================== 🚀 KULLANICI KOMUTLARI ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.command
    await get_user(user_id)
    
    # Referans İşlemi
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
    
    # MENÜ (Eksiksiz)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Hesabım & Referans", callback_data="my_account")],
        [InlineKeyboardButton("🚀 VIP Satın Al", url=f"https://t.me/{username if username else 'yasin33'}")],
        [InlineKeyboardButton("❓ Nasıl Kullanılır?", callback_data="help")]
    ])
    
    await message.reply(
        f"👋 **Selam {message.from_user.first_name}!**\n\n"
        f"Ben **Yael Saver**. Kısıtlı içerikleri orijinal kalitede indiririm.\n\n"
        f"💰 **Mevcut Hakkın:** `{user_data['balance']}` Dosya\n\n"
        f"👇 Link gönder veya arkadaş davet et kazan!",
        reply_markup=btn
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    user_data = await get_user(user_id)

    if data == "my_account":
        ref_link = f"https://t.me/{client.me.username}?start={user_id}"
        await callback.message.edit(
            f"👤 **HESAP BİLGİLERİ**\n\n"
            f"💰 **Bakiye:** `{user_data['balance']}`\n"
            f"👥 **Davetler:** `{user_data['total_refs']}`\n\n"
            f"🔗 **Referans Linkin:**\n`{ref_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]])
        )

    elif data == "help":
        await callback.message.edit(
            "❓ **NASIL KULLANILIR?**\n\n"
            "1️⃣ Yasaklı kanaldan linki kopyala.\n"
            "2️⃣ Buraya yapıştır.\n"
            "3️⃣ Bot indirip sana atsın.\n\n"
            "💎 **VIP:** Sınırsız indirme için yöneticiye yaz.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]])
        )

    elif data == "back_home":
        await start_command(client, callback.message)

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)

    # 1. Bakiye Kontrolü
    if user_data["balance"] <= 0 and user_id != OWNER_ID: # Owner'a sınır yok
        return await message.reply(
            "⛔ **Hakkınız Bitti!**\nVIP alın veya arkadaş davet edin.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 VIP Al", url=f"https://t.me/yasin33")]
            ])
        )

    status_msg = await message.reply("⏳ **İşleniyor...**")
    
    try:
        # Link Ayrıştırma
        if "t.me/c/" in message.text:
            parts = message.text.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1].split("?")[0])
        else:
            parts = message.text.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1].split("?")[0])

        target_msg = await userbot.get_messages(chat_id, msg_id)
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status_msg.edit("❌ İçerik bulunamadı veya sadece yazı.")

        # İndirme
        file_path = await userbot.download_media(target_msg)
        
        # Gönderme
        caption = "✅ **Yael Saver** | @yasin33" # Buraya kendi reklamını yaz
        
        if target_msg.video:
            await client.send_video(user_id, video=file_path, caption=caption, 
                                  duration=target_msg.video.duration, 
                                  width=target_msg.video.width, 
                                  height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, photo=file_path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, document=file_path, caption=caption)

        # Bakiye Düş (Owner hariç)
        if user_id != OWNER_ID:
            await update_balance(user_id, -1)
            
        # Temizlik
        if os.path.exists(file_path): os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit(f"❌ Hata: {e}")
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

# ==================== 🔥 BAŞLATMA SİSTEMİ (DÜZELTİLDİ) ====================
async def main():
    print("🤖 Botlar Başlatılıyor...")
    
    # Botları başlat
    try:
        await bot.start()
        print(f"✅ SALES BOT AKTİF: @{bot.me.username}")
    except Exception as e:
        print(f"❌ BOT TOKEN HATASI: {e}")

    try:
        await userbot.start()
        print("✅ USERBOT AKTİF")
    except Exception as e:
        print(f"❌ USERBOT HATASI: {e}")

    # Sonsuza kadar bekle
    await idle()
    
    # Kapanış
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    # 1. Önce Web Sunucusunu AYRI bir thread'de başlat (Botu bekletmesin)
    print("🌍 Web Sunucusu Başlatılıyor...")
    web_thread = Thread(target=run_web)
    web_thread.daemon = True # Ana program kapanınca bu da kapansın
    web_thread.start()

    # 2. Sonra Botu Ana Döngüde Başlat
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
