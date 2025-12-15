import asyncio
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, UserPrivacyRestricted, UserAlreadyParticipant, PeerIdInvalid
import sqlite3
import threading
from flask import Flask

# --- YAPILANDIRMA ---
API_ID = 37107052
API_HASH = "afc7a787cbde453b8fc7134383658b30"

# 1. GÖRÜNÜR BOT (BotFather'dan aldığın Token)
BOT_TOKEN = "7839067076:AAHgC6C-mzQegzVVHLmkVH08vu-jkTBaQlI"

# 2. GİZLİ ASKER (Fake numaranın Session String kodu)
# Kendi ana hesabının kodunu koyma, yan hesabını koy!
SESSION_STRING = "BAI2NWwAj6zZYFPYXXWDK2fNcBeZYSn7qPtcrB-5dQTPyHazeVF7F_fvw2gLMvB5JyB7exqyKcLicCqG5e_o9z46BbsR1lKZCGxaE9xYm3_O_NMI-8ZciOCn6o5VFUMZJnEappc6Py_6eNA2w7kOB-YpYNCOZp5A4cGF_wY_2LWR9UzSbGIeYLMoYokUrYtYTANDNrxG5lX50WtUusyr6_OX1uHsXIRuyeYWNa0qqZJY0A_KuTKKuFBIpn11H0BXf1DSxj1EvpwTM82rh2S1Oq3CfdROQYS0ADvl68-yTf-Sa2EmbeGEa6sXj_-7Z-QjC9lgOiPltG8FMSvw-kWgKRtF2W89igAAAAH4WvQ0AA"

ADMIN_ID = 8102629232  # Senin ID'n

# --- FLASK (Botun 7/24 Pella'da çalışması için) ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot ve Asker Calisiyor..."

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

# --- BOTLARI TANIMLA ---
# Patron Bot (Kullanıcılarla konuşur)
bot = Client("ManagerBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Asker Bot (Arka planda üye çeker - Userbot modunda çalışır)
worker = Client("WorkerBot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# --- YARDIMCI FONKSİYONLAR ---
def get_user_data(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT status, credits FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    if not result:
        # İlk gelene 3 hak ver
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

# --- KOMUTLAR ---

@bot.on_message(filters.command("start"))
async def start_msg(client, message):
    user_id = message.from_user.id
    status, credits = get_user_data(user_id)
    
    msg = (
        f"🤖 **Üye Çekme Botuna Hoş Geldin!**\n\n"
        f"📊 **Üyelik:** {status.upper()}\n"
        f"💎 **Kalan Hakkın:** {credits if status == 'free' else 'SINIRSIZ'}\n\n"
        "🚀 **Nasıl Kullanılır?**\n"
        "`/uyecek @kaynakgrup @hedefgrup`\n\n"
        "⚡ _Botun kaynak grupta yönetici olmasına gerek yoktur._"
    )
    await message.reply(msg)

@bot.on_message(filters.command("vipyap") & filters.user(ADMIN_ID))
async def vip_yap(client, message):
    try:
        target = int(message.text.split()[1])
        set_user_data(target, "vip", 999999)
        await message.reply(f"✅ {target} ID'li kullanıcı artık VIP!")
    except:
        await message.reply("Hata: /vipyap ID")

@bot.on_message(filters.command("uyecek"))
async def scrape_handler(client, message):
    user_id = message.from_user.id
    status, credits = get_user_data(user_id)
    
    # Kredi Kontrolü
    if status == "free" and credits < 1:
        await message.reply("⛔ **Deneme hakkınız bitti!** VIP satın almalısınız.")
        return

    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply("⚠️ Kullanım: `/uyecek @kaynak @hedef`")
            return
        
        source = args[1]
        target = args[2]
        
        info_msg = await message.reply("⚙️ **Sistem hazırlanıyor...**\n_Asker hesap kaynak gruba sızıyor..._")
        
        # --- ASKER (WORKER) DEVREYE GİRER ---
        try:
            # 1. Asker gruba girer
            await worker.join_chat(source)
        except UserAlreadyParticipant:
            pass
        except Exception as e:
            await info_msg.edit(f"❌ Kaynak gruba girilemedi: {e}")
            return

        # 2. Üyeleri listeler
        await info_msg.edit("📥 **Üye listesi alınıyor...**")
        members = []
        limit_to_fetch = 100 if status == "free" else 500
        
        async for m in worker.get_chat_members(source, limit=limit_to_fetch):
            if not m.user.is_bot and not m.user.is_deleted:
                members.append(m.user.id)
        
        if not members:
            await info_msg.edit("❌ Üye bulunamadı veya gizli.")
            return

        # 3. Hedefe ekleme başlar
        await info_msg.edit(f"🚀 **{len(members)} kişi bulundu.** Ekleniyor...")
        
        count = 0
        max_add = 3 if status == "free" else 50 # Güvenlik için işlem başına limit
        
        for uid in members:
            if count >= max_add:
                break
            try:
                await worker.add_chat_members(target, uid)
                count += 1
                await asyncio.sleep(2) # Ban yememek için yavaş ekleme
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except (UserPrivacyRestricted, UserAlreadyParticipant, PeerIdInvalid):
                continue
            except Exception:
                continue
        
        # Krediyi düş
        if status == "free":
            new_creds = credits - count
            set_user_data(user_id, "free", max(0, new_creds))
        
        await info_msg.edit(
            f"✅ **İşlem Tamam!**\n"
            f"👤 Eklenen: {count}\n"
            f"📉 Kalan Hak: {get_user_data(user_id)[1]}"
        )

    except Exception as e:
        await message.reply(f"❌ Hata oluştu: {e}")

# --- BAŞLATMA ---
async def main():
    threading.Thread(target=run_flask).start()
    
    print("Botlar başlatılıyor...")
    await bot.start()
    await worker.start()
    print("Sistem Hazır!")
    
    await idle()
    
    await bot.stop()
    await worker.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    loop.run_until_complete(main())

