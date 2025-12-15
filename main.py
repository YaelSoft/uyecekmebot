import asyncio
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, UserPrivacyRestricted, UserAlreadyParticipant, UserNotParticipant, UsernameInvalid
import sqlite3
import threading
from flask import Flask

# --- AYARLAR ---
API_ID = 37107052
API_HASH = "afc7a787cbde453b8fc7134383658b30"

# 1. GÖRÜNÜR BOT (BotFather Token)
BOT_TOKEN = "7839067076:AAHgC6C-mzQegzVVHLmkVH08vu-jkTBaQlI"

# 2. GİZLİ İŞÇİ (Session String - Pyrogram Formatı)
SESSION_STRING = "BAI2NWwAj6zZYFPYXXWDK2fNcBeZYSn7qPtcrB-5dQTPyHazeVF7F_fvw2gLMvB5JyB7exqyKcLicCqG5e_o9z46BbsR1lKZCGxaE9xYm3_O_NMI-8ZciOCn6o5VFUMZJnEappc6Py_6eNA2w7kOB-YpYNCOZp5A4cGF_wY_2LWR9UzSbGIeYLMoYokUrYtYTANDNrxG5lX50WtUusyr6_OX1uHsXIRuyeYWNa0qqZJY0A_KuTKKuFBIpn11H0BXf1DSxj1EvpwTM82rh2S1Oq3CfdROQYS0ADvl68-yTf-Sa2EmbeGEa6sXj_-7Z-QjC9lgOiPltG8FMSvw-kWgKRtF2W89igAAAAH4WvQ0AA"
# SENİN ID'N (Bunu yazınca Admin Menüsünü göreceksin)
ADMIN_ID = 8102629232 

# --- FLASK (Botun uyumaması için) ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Aktif"

def run_flask():
    app_web.run(host='0.0.0.0', port=5000)

# --- VERİTABANI ---
def db_connect():
    return sqlite3.connect('database.db', check_same_thread=False)

def init_db():
    conn = db_connect()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, status TEXT, credits INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- BOTLARI BAŞLAT ---
bot = Client("ManagerBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
worker = Client("WorkerBot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# --- YARDIMCI FONKSİYONLAR ---

def get_user_data(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT status, credits FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    if not result:
        # Yeni gelene 3 hak ver
        set_user_data(user_id, "free", 3)
        return ("free", 3)
    return result

def set_user_data(user_id, status, credits):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, status, credits) VALUES (?, ?, ?)", 
              (user_id, status, credits))
    conn.commit()
    conn.close()

# Link Temizleyici (Hata Çözümü)
def clean_username(text):
    if not text:
        return ""
    # Link ise temizle (https://t.me/grup -> grup)
    if "t.me/" in text:
        text = text.split("t.me/")[1]
    # @ işareti varsa kaldır (@grup -> grup)
    text = text.replace("@", "").strip()
    return text

# --- ÖZELLEŞTİRİLMİŞ START MESAJLARI ---

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # 1. SEN (ADMİN) İSEN:
    if user_id == ADMIN_ID:
        await message.reply(
            "👑 **Patron Hoş Geldin!**\n\n"
            "Sistem emrine amade. İşte gizli komutların:\n\n"
            "👤 **Kullanıcı Yönetimi:**\n"
            "• `/vipyap ID` -> Kullanıcıyı sınırsız VIP yapar.\n"
            "• `/vipsil ID` -> Kullanıcının VIP'sini alır.\n"
            "• `/krediver ID MİKTAR` -> Kullanıcıya kredi ekler.\n\n"
            "🚀 **İşlem Komutu:**\n"
            "• `/uyecek kaynak hedef` -> (Örn: /uyecek grup1 grup2)\n\n"
            "📊 **Durum:** Sistem aktif, İşçi (Userbot) hazır."
        )
        return

    # Veritabanından kullanıcı durumunu çek
    status, credits = get_user_data(user_id)

    # 2. VIP KULLANICI İSE:
    if status == "vip":
        await message.reply(
            "💎 **VIP Panelindesiniz**\n\n"
            "Hoş geldiniz! Hesabınızda **SINIRSIZ** işlem hakkı tanımlı.\n"
            "Bekleme süresi olmadan, dilediğiniz kadar üye çekebilirsiniz.\n\n"
            "🚀 **Kullanım:**\n"
            "`/uyecek @kaynakgrup @hedefgrup`\n\n"
            "⚠️ _Not: Botun kaynak grupta yönetici olmasına gerek yoktur._"
        )
    
    # 3. NORMAL (FREE) KULLANICI İSE:
    else:
        await message.reply(
            f"👋 **Hoş Geldin!**\n\n"
            f"Şu an **Deneme Sürümü** kullanıyorsun.\n"
            f"💰 **Kalan Hakkın:** {credits} Üye\n\n"
            "🚀 **Nasıl Kullanılır?**\n"
            "`/uyecek @kaynakgrup @hedefgrup`\n\n"
            "💎 **Daha Fazlası İçin:**\n"
            "VIP satın alarak sınırsız ve hızlı işlem yapabilirsin.\n"
            "İletişim: @SahipKullaniciAdi"
        )

# --- ADMİN KOMUTLARI ---

@bot.on_message(filters.command("vipyap") & filters.user(ADMIN_ID))
async def vip_add(client, message):
    try:
        target = int(message.text.split()[1])
        set_user_data(target, "vip", 999999)
        await message.reply(f"✅ {target} artık VIP!")
    except: await message.reply("Hata! Kullanım: /vipyap ID")

@bot.on_message(filters.command("vipsil") & filters.user(ADMIN_ID))
async def vip_del(client, message):
    try:
        target = int(message.text.split()[1])
        set_user_data(target, "free", 0)
        await message.reply(f"❌ {target} artık Normal Üye (0 Kredi).")
    except: await message.reply("Hata! Kullanım: /vipsil ID")

@bot.on_message(filters.command("krediver") & filters.user(ADMIN_ID))
async def add_credit(client, message):
    try:
        args = message.text.split()
        target = int(args[1])
        amount = int(args[2])
        status, current = get_user_data(target)
        set_user_data(target, status, current + amount)
        await message.reply(f"✅ {target} ID'li kişiye {amount} kredi eklendi.")
    except: await message.reply("Hata! Kullanım: /krediver ID MİKTAR")

# --- ÜYE ÇEKME İŞLEMİ ---

@bot.on_message(filters.command("uyecek"))
async def scrape_process(client, message):
    user_id = message.from_user.id
    
    # Admin değilse kredi kontrolü yap
    status, credits = get_user_data(user_id)
    if user_id != ADMIN_ID:
        if status == "free" and credits < 1:
            await message.reply("⛔ **Hakkınız bitti!** VIP satın almalısınız.")
            return

    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply("⚠️ **Kullanım:** `/uyecek kaynak hedef`\n(Link veya @kullaniciadi yazabilirsin)")
            return
        
        # Linkleri temizle (Hata Çözümü Burada)
        source = clean_username(args[1])
        target = clean_username(args[2])
        
        status_msg = await message.reply(f"🔍 **{source}** taranıyor... Lütfen bekleyin.")
        
        # 1. Userbot Gruba Girer
        try:
            await worker.join_chat(source)
        except UserAlreadyParticipant:
            pass
        except Exception as e:
            await status_msg.edit(f"❌ Kaynak gruba girilemedi: {e}")
            return

        # 2. Üyeleri Topla
        members = []
        limit = 500 if status == "vip" or user_id == ADMIN_ID else 100
        
        async for m in worker.get_chat_members(source, limit=limit):
            if not m.user.is_bot and not m.user.is_deleted:
                members.append(m.user.id)
        
        if not members:
            await status_msg.edit("❌ Üye bulunamadı.")
            return

        # 3. Ekleme İşlemi
        await status_msg.edit(f"🚀 **{len(members)}** kişi bulundu. Hedefe ({target}) ekleniyor...")
        
        success = 0
        max_add = 50 if status == "vip" or user_id == ADMIN_ID else 3 # Free ise 3 kişi
        
        for uid in members:
            if success >= max_add:
                break
            try:
                await worker.add_chat_members(target, uid)
                success += 1
                await asyncio.sleep(1) # Hız ayarı
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                continue
        
        # Kredi düşme
        if user_id != ADMIN_ID and status == "free":
            new_credits = credits - success
            set_user_data(user_id, "free", max(0, new_credits))

        await status_msg.edit(
            f"✅ **İşlem Tamamlandı!**\n"
            f"👤 Eklenen: {success}\n"
            f"📉 Kalan Kredi: {get_user_data(user_id)[1] if status == 'free' else 'SINIRSIZ'}"
        )

    except Exception as e:
        await message.reply(f"❌ Hata: {str(e)}")

# --- SİSTEMİ BAŞLAT ---
async def main():
    threading.Thread(target=run_flask).start()
    print("Sistem Başlatılıyor...")
    await bot.start()
    await worker.start()
    print(">>> BOT AKTİF <<<")
    await idle()
    await bot.stop()
    await worker.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
