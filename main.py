import os
import asyncio
import threading
import sqlite3
import time
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Ticari Bot + Transfer Modu Aktif!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")       
SESSION_STRING = os.environ.get("SESSION_STRING", "") # Senin Ana Hesabın
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 3. BAŞLATMA ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 4. VERİTABANI ---
def init_db():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0, daily_limit INTEGER DEFAULT 3, last_reset TEXT)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
        conn.commit(); conn.close(); return (user_id, 0, 3, today)
    
    if user[3] != today and user[1] == 0:
        c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
        conn.commit(); conn.close(); return (user_id, 0, 3, today)
        
    conn.close(); return user

def dusur_hak(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET daily_limit = daily_limit - 1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

def set_vip(user_id, status):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit(); conn.close()

# --- 5. İLERLEME ÇUBUĞU ---
async def progress_bar(current, total, message, start_time, action_text):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        filled = int(percentage / 10)
        bar = '🟩' * filled + '⬜' * (10 - filled)
        try:
            await message.edit(f"**{action_text}**\n\n{bar} **%{round(percentage, 1)}**\n🚀 Hız: {round(speed/1024/1024, 2)} MB/s")
        except: pass

# --- 6. DETAYLI KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    
    if uid in ADMINS:
        msg = (
            "👑 **PATRON PANELİ**\n\n"
            "Sistem senin emrinde. Hem müşteri yönetebilir hem de toplu işlem yapabilirsin.\n\n"
            "👥 **Müşteri Yönetimi:**\n"
            "`/vip ID` ➡️ Kullanıcıyı Sınırsız Yap\n"
            "`/unvip ID` ➡️ Normale Çevir\n\n"
            "📦 **Toplu Transfer (Userbot):**\n"
            "`/transfer kaynak hedef adet`\n"
            "_(Örn: /transfer https://t.me/kaynak https://t.me/hedef 50)_\n\n"
            "🔗 **İndirme Modu:**\n"
            "Herhangi bir link gönder, indireyim."
        )
    elif vip:
        msg = (
            "🌟 **VIP MÜŞTERİ PANELİ**\n\n"
            "Hoş geldiniz! Hesabınız **PREMIUM** statüsündedir.\n"
            "✅ Günlük Limit: **YOK (Sınırsız)**\n"
            "✅ Bekleme Süresi: **YOK**\n"
            "✅ Gizli Kanal Erişimi: **VAR**\n\n"
            "📥 **Nasıl Kullanılır?**\n"
            "1. Eğer kanal gizliyse, önce **Davet Linkini** (t.me/+..) atın.\n"
            "2. Sonra istediğiniz mesajın linkini atın.\n"
            "3. Anında indireyim."
        )
    else:
        msg = (
            f"👋 **Hoş Geldiniz!**\n\n"
            f"Şu an **Deneme Sürümü** kullanıyorsunuz.\n"
            f"📝 Günlük Kalan Hakkınız: **{u[2]}/3**\n\n"
            "🔓 **Neler Yapabilirim?**\n"
            "İletim kapalı (Korumalı) kanallardan fotoğraf ve video indirebilirim.\n\n"
            "💎 **Sınırsız Erişim İçin:**\n"
            "VIP satın alarak limitsiz ve beklemesiz işlem yapabilirsiniz.\n\n"
            "🚀 **Başlamak İçin:** Link gönderin."
        )
    await event.respond(msg)

# Admin Komutları
@bot.on(events.NewMessage(pattern='/vip'))
async def vip_yap(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 1)
        await event.respond(f"✅ {t} ID'li kullanıcı VIP yapıldı!")
    except: await event.respond("❌ Hata! Kullanım: `/vip 12345`")

@bot.on(events.NewMessage(pattern='/unvip'))
async def vip_al(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 0)
        await event.respond(f"❌ {t} Normale döndü.")
    except: await event.respond("❌ Hata! Kullanım: `/unvip 12345`")

# --- 7. TOPLU TRANSFER MODU (YENİ!) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_mode(event):
    if event.sender_id not in ADMINS: return
    
    try:
        args = event.message.text.split()
        if len(args) < 4:
            await event.respond("⚠️ **Kullanım:** `/transfer [KaynakLink] [HedefLink] [Adet]`\n\nÖrn: `/transfer https://t.me/arsivim https://t.me/depom 100`")
            return

        source = args[1]
        target = args[2]
        limit = int(args[3])
        
        status = await event.respond(f"🚀 **Transfer Başlatılıyor...**\n\n📤 Kaynak: {source}\n📥 Hedef: {target}\n📦 Adet: {limit}\n\n_Bu işlem sunucuyu yormamak için yavaş yapılacaktır._")
        
        # Entityleri Çözümle (Userbot Gözüyle)
        try:
            if 't.me/c/' in source: src_entity = await userbot.get_entity(int('-100' + source.split('/')[-2]))
            else: src_entity = await userbot.get_entity(source.split('/')[-1])
            
            if 't.me/c/' in target: dst_entity = await userbot.get_entity(int('-100' + target.split('/')[-2]))
            else: dst_entity = await userbot.get_entity(target.split('/')[-1])
        except Exception as e:
            await status.edit(f"❌ Kanallara erişilemedi. Userbot (Sen) iki kanalda da var mısın?\nHata: {e}")
            return

        count = 0
        error = 0
        
        # Döngü Başlasın
        async for msg in userbot.iter_messages(src_entity, limit=limit):
            if msg.media:
                try:
                    # Direkt İlet (Forward) - Eğer izin varsa en hızlısı
                    # Ama 'İletim Kapalı' ise patlar. O yüzden 'İndir-Yükle' garantidir.
                    # Render diskini doldurmamak için indirip hemen siliyoruz.
                    
                    path = await userbot.download_media(msg)
                    if path:
                        await userbot.send_file(dst_entity, path, caption=msg.text)
                        os.remove(path) # Anında sil
                        count += 1
                        
                        if count % 5 == 0:
                            await status.edit(f"♻️ **Transfer Sürüyor...**\n✅ Başarılı: {count}\n❌ Hata: {error}")
                        
                        await asyncio.sleep(2) # Telegram spam atmasın diye bekleme
                except Exception as e:
                    error += 1
                    continue
        
        await status.edit(f"🏁 **TRANSFER BİTTİ!**\n\n✅ Toplam Aktarılan: {count}\n❌ Başarısız: {error}")

    except Exception as e:
        await event.respond(f"❌ Genel Hata: {e}")

# --- 8. TEKİL İNDİRME MODU ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    limit = u[2]
    
    # Müşteri Hak Kontrolü
    if uid not in ADMINS and not vip:
        if limit <= 0:
            await event.respond("⛔ **Günlük Hakkınız Bitti!**\nYarın tekrar deneyin veya VIP satın alın.")
            return
        status = await event.respond("⏳ **Sıraya Alındı...** (Lütfen Bekleyin)")
        await asyncio.sleep(4)
    else:
        status = await event.respond("🔄 **İşleniyor...**")

    text = event.message.text.strip()

    try:
        # A) DAVET LİNKİ (t.me/+)
        if "t.me/+" in text or "joinchat" in text:
            try:
                await userbot(ImportChatInviteRequest(text.split('+')[-1]))
                await status.edit("✅ **Gizli Kanala Giriş Yapıldı!**\nŞimdi içerik linkini gönderebilirsiniz.")
            except UserAlreadyParticipantError:
                await status.edit("ℹ️ **Zaten Bu Kanaldayım.**\nDirekt mesaj linkini gönderin.")
            except Exception as e:
                # Bazen link formatı farklıdır
                try:
                    await userbot.join_chat(text)
                    await status.edit("✅ **Giriş Başarılı!**")
                except:
                    await status.edit(f"❌ Kanala Girilemedi. Link geçersiz olabilir.\nHata: {e}")
            return

        # B) İÇERİK LİNKİ
        if "t.me/" not in text:
            await status.edit("❌ Geçersiz Link."); return

        try:
            parts = text.rstrip('/').split('/')
            msg_id = int(parts[-1])
            
            if 't.me/c/' in text:
                cid = int('-100' + parts[-2])
                entity = await userbot.get_entity(cid)
            else:
                username = parts[-2]
                entity = await userbot.get_entity(username)
                
            msg = await userbot.get_messages(entity, ids=msg_id)
        except Exception as e:
            await status.edit("❌ **Erişim Engellendi!**\nBot bu kanalda değil. Lütfen önce kanalın **Davet Linkini** (t.me/+..) gönderin.")
            return

        if not msg or not msg.media:
            await status.edit("❌ Medya bulunamadı."); return

        # İndir
        start = time.time()
        path = await userbot.download_media(msg, progress_callback=lambda c, t: progress_bar(c, t, status, start, "⬇️ Sunucuya İniyor"))
        
        # Yükle
        start = time.time()
        await bot.send_file(
            event.chat_id, 
            path, 
            caption=msg.text or "", 
            progress_callback=lambda c, t: progress_bar(c, t, status, start, "⬆️ Size Gönderiliyor")
        )
        
        # Sil & Hak Düş
        if os.path.exists(path): os.remove(path)
        if uid not in ADMINS and not vip: dusur_hak(uid)
        
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {str(e)}")
        if 'path' in locals() and path and os.path.exists(path): os.remove(path)

# --- 9. BAŞLATMA ---
def main():
    # Veritabanını Kur
    init_db()
    
    # Web Sunucusunu Başlat
    threading.Thread(target=run_web).start()
    
    print("🚀 Sistem Başlatılıyor...")
    
    # Userbot'u Başlat
    userbot.start()
    
    # Bot'u Başlat
    print("✅ Sistem Aktif! Bot Dinliyor...")
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
