import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from motor.motor_asyncio import AsyncIOMotorClient # MongoDB Sürücüsü

# ==================== ⚙️ AYARLAR (RENDER ENV) ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
MONGO_URL = os.environ.get("MONGO_URL", "") # Senin kopyaladığın o uzun link

# REFERANS AYARLARI
START_BALANCE = 3       # Başlangıç Hakkı
REF_REWARD = 2          # Referans Ödülü

# LOGLAMA
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelMongoBot")

# ==================== 🌐 WEB SERVER (RENDER AYAKTA KALSIN) ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver MongoDB System Online 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 MONGODB BAĞLANTISI ====================
if not MONGO_URL:
    logger.error("❌ MONGO_URL EKSIK! Lütfen Render Environment Variables kısmına ekle.")
    exit(1)

# Bağlantıyı Kur
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["yael_saver_db"] # Veritabanı adı
users_col = db["users"]            # Tablo adı

# --- VERİTABANI FONKSİYONLARI ---

async def get_user(user_id):
    """Kullanıcıyı getir, yoksa oluştur (Async)"""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "balance": START_BALANCE,
            "invited_by": None,
            "total_refs": 0
        }
        await users_col.insert_one(user)
    return user

async def update_balance(user_id, amount):
    """Bakiye ekle veya çıkar"""
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount}}
    )

async def add_ref(user_id, referrer_id, client):
    """Referans ekle (Fake ve Kendi Kendine Referans Korumalı)"""
    # 1. Kendine referans olamaz
    if str(user_id) == str(referrer_id): return False
    
    # 2. Daha önce referansla gelmiş mi?
    user = await get_user(user_id)
    if user.get("invited_by"): return False 
    
    # 3. FAKE KORUMASI: Kullanıcı adı kontrolü
    try:
        u_info = await client.get_users(user_id)
        if not u_info.username: return False # Username yoksa sayma
    except: return False

    # 4. Kayıt İşlemi
    # Kullanıcıya "Davet Edeni" işle
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"invited_by": referrer_id}}
    )
    
    # Davet Edene Ödül Ver
    await users_col.update_one(
        {"user_id": referrer_id},
        {"$inc": {"balance": REF_REWARD, "total_refs": 1}}
    )
    return True

# ==================== 🚀 KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.command
    
    # Kullanıcıyı veritabanından çek (yoksa yaratır)
    await get_user(user_id)
    
    # REFERANS İŞLEMİ (Link ile geldiyse)
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            success = await add_ref(user_id, referrer_id, client)
            
            if success:
                # Ödül Kazanan Kişiye Bildirim At
                try:
                    ref_user = await get_user(referrer_id)
                    await client.send_message(
                        referrer_id,
                        f"🎁 **TEBRİKLER!**\n\n"
                        f"Bir arkadaşın aramıza katıldı, hesabına **+{REF_REWARD} Hak** eklendi!\n"
                        f"💰 **Yeni Bakiye:** {ref_user['balance']}"
                    )
                except: pass
        except: pass

    # Güncel veriyi çek
    user_data = await get_user(user_id)

    # MENÜ BUTONLARI
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Hesabım & Referans Linkim", callback_data="my_account")],
        [InlineKeyboardButton("🚀 VIP Satın Al (Sınırsız)", url=f"https://t.me/{username if username else 'yasin33'}")],
        [InlineKeyboardButton("❓ Nasıl Kullanılır?", callback_data="help")]
    ])
    
    await message.reply(
        f"👋 **Selam {message.from_user.first_name}!**\n\n"
        f"Ben **Yael Saver Bot**. Kısıtlı kanallardan **Orijinal Kalitede** içerik indiririm.\n\n"
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
            f"💰 **Kalan Hakkın:** `{user_data['balance']}`\n"
            f"👥 **Davetlerin:** `{user_data['total_refs']}` Kişi\n\n"
            f"📢 **DAVET ET KAZAN**\n"
            f"Her arkadaşın için **+{REF_REWARD} Hak** kazan!\n\n"
            f"🔗 **Linkin:**\n`{ref_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]])
        )

    elif data == "help":
        await callback.message.edit(
            "❓ **NASIL KULLANILIR?**\n\n"
            "1️⃣ Linki kopyala, buraya yapıştır.\n"
            "2️⃣ Bot indirip **Orijinal Kalitede** atsın.\n\n"
            "⚠️ *Bot demo sürümüdür. 40.000+ toplu işlem için VIP gerekir.*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]])
        )

    elif data == "back_home":
        await start_command(client, callback.message)

# ==================== 🔥 İNDİRME VE İŞLEME (KALBİ) ====================

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    link = message.text

    # 1. BAKİYE KONTROLÜ
    if user_data["balance"] <= 0:
        ref_link = f"https://t.me/{client.me.username}?start={user_id}"
        await message.reply(
            "⛔ **Hakkınız Bitti!**\n\n"
            "Devam etmek için arkadaş davet edin veya VIP alın.\n\n"
            f"🔗 **Davet Linkin:** `{ref_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Bakiye Kazan", callback_data="my_account")],
                [InlineKeyboardButton("🚀 VIP Al", url="https://t.me/yasin33")]
            ])
        )
        return

    status_msg = await message.reply("⏳ **Analiz Ediliyor...**\n_(Orijinal kalite korunuyor)_")
    
    try:
        # Link Ayrıştırma (Private veya Public)
        if "t.me/c/" in link:
            parts = link.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1].split("?")[0])
        else:
            parts = link.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1].split("?")[0])

        # Userbot ile Mesajı Getir
        target_msg = await userbot.get_messages(chat_id, msg_id)
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            await status_msg.edit("❌ **Hata:** İçerik bulunamadı veya sadece yazı.")
            return

        await status_msg.edit("⬇️ **Sunucuya İndiriliyor...**")
        
        # Dosyayı İndir
        file_path = await userbot.download_media(target_msg)
        
        if not file_path:
            await status_msg.edit("❌ İndirme başarısız.")
            return

        await status_msg.edit("⬆️ **Yükleniyor...**")

        caption = f"✅ **İşlem Başarılı!**\n\n💎 Kalan Hakkın: {user_data['balance'] - 1}"
        
        # 🔥 ORİJİNAL KALİTE GÖNDERİM 🔥
        if target_msg.video:
            # Video özelliklerini (Width, Height, Duration) koruyoruz!
            await client.send_video(
                user_id, 
                video=file_path, 
                caption=caption,
                duration=target_msg.video.duration,
                width=target_msg.video.width,
                height=target_msg.video.height,
                supports_streaming=True
            )
        elif target_msg.photo:
            await client.send_photo(user_id, photo=file_path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, document=file_path, caption=caption)

        # 2. BAKİYEDEN DÜŞ
        await update_balance(user_id, -1)
        
        # 3. DOSYAYI SİL (GÜVENLİK)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        await status_msg.delete()

    except FloodWait as e:
        await status_msg.edit(f"⚠️ Hız limiti! {e.value} saniye bekle.")
    except Exception as e:
        logger.error(f"Hata: {e}")
        await status_msg.edit("❌ **Hata:** İçerik alınamadı. (Link doğru mu?)")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    keep_alive()
    # Userbot ve Botu aynı anda başlat
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start())
    loop.create_task(userbot.start())
    loop.run_forever()
