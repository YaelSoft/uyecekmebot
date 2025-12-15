import os
import asyncio
import json
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant, ChannelPrivate
import sqlite3

# Bot ve Userbot API bilgileri
API_ID = int(os.environ.get("37107052"))
API_HASH = os.environ.get("afc7a787cbde453b8fc7134383658b30")
BOT_TOKEN = os.environ.get("7839067076:AAHgC6C-mzQegzVVHLmkVH08vu-jkTBaQlI")

# Session string için (Render'da kullanmak için)
USERBOT_STRING = os.environ.get("USERBOT_STRING", "")

# Admin user ID'leri
ADMINS = list(map(int, os.environ.get("8102629232", "").split(","))) if os.environ.get("ADMINS") else []

# Bot client
bot = Client("content_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Userbot client - Session string kullanarak
if USERBOT_STRING:
    userbot = Client(
        "userbot_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=USERBOT_STRING
    )
else:
    # Local test için session dosyası
    userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH)

# Veritabanı başlatma
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  is_vip INTEGER DEFAULT 0,
                  daily_limit INTEGER DEFAULT 3,
                  last_reset TEXT,
                  total_scraped INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def add_or_update_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    user = get_user(user_id)
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
    else:
        # Günlük limit sıfırlama kontrolü
        if user[3] != today and user[1] == 0:  # VIP değilse
            c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
    
    conn.commit()
    conn.close()

def use_limit(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET daily_limit=daily_limit-1, total_scraped=total_scraped+1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def set_vip(user_id, is_vip):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_vip=? WHERE user_id=?", (1 if is_vip else 0, user_id))
    conn.commit()
    conn.close()

def get_remaining_limit(user_id):
    user = get_user(user_id)
    if user is None:
        return 3
    if user[1] == 1:  # VIP
        return -1  # Sınırsız
    return max(0, user[2])

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    add_or_update_user(user_id)
    
    user = get_user(user_id)
    is_vip = user[1] == 1 if user else False
    
    welcome_text = f"""
👋 **Hoş geldin {message.from_user.first_name}!**

Bu bot ile iletim kapalı Telegram kanallarından ve gruplarından içerik çekebilirsin.

📊 **Senin Durumun:**
{'🌟 **VIP Kullanıcısın** - Sınırsız ve bekleme süresiz erişim!' if is_vip else f'📝 Günlük limit: **{get_remaining_limit(user_id)}/3** içerik'}

**Kullanım:**
Sadece kanalın/grubun linkini veya username'ini gönder:
• `https://t.me/kanal_adi/123`
• `@kanal_adi` veya `@kanal_adi/123`

**Komutlar:**
/start - Bot'u başlat
/stats - İstatistiklerini gör
/help - Yardım

{'🔧 **Admin Komutları:**\n/vip [user_id] - VIP ekle\n/unvip [user_id] - VIP kaldır' if user_id in ADMINS else ''}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Yardım", callback_data="help"),
         InlineKeyboardButton("📊 İstatistikler", callback_data="stats")]
    ])
    
    await message.reply_text(welcome_text, reply_markup=keyboard)

@bot.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user is None:
        await message.reply_text("❌ Önce /start komutunu kullan!")
        return
    
    is_vip = user[1] == 1
    total = user[4]
    limit = get_remaining_limit(user_id)
    
    stats_text = f"""
📊 **Senin İstatistiklerin**

👤 Kullanıcı ID: `{user_id}`
{'🌟 Durum: **VIP** (Sınırsız)' if is_vip else f'📝 Kalan günlük hak: **{limit}/3**'}
📥 Toplam çekilen içerik: **{total}**

{f'🔄 Limit sıfırlanma: **Yarın**' if not is_vip and limit < 3 else ''}
"""
    
    await message.reply_text(stats_text)

@bot.on_message(filters.command("help"))
async def help_command(client, message: Message):
    help_text = """
📚 **Yardım - Nasıl Kullanılır?**

**1️⃣ Link Gönder:**
Telegram mesaj linkini direkt gönder:
`https://t.me/kanal_adi/12345`

**2️⃣ Username Gönder:**
Kanal username'i ile:
`@kanal_adi/12345`

**3️⃣ Bot İşlemi Yapar:**
✅ Kanala userbot ile katılır
✅ İçeriği çeker
✅ Sana gönderir

**⚠️ Önemli Notlar:**
• Kanal açık veya userbot'un katılabileceği türde olmalı
• Bazı kanallar bot girişini engelliyor olabilir
• Çok büyük medya dosyaları zaman alabilir

**Limitler:**
🆓 Ücretsiz: 3 içerik/gün
🌟 VIP: Sınırsız + bekleme yok
💎 Premium VIP: Sınırsız + hızlı
"""
    
    await message.reply_text(help_text)

@bot.on_message(filters.command("vip") & filters.user(ADMINS))
async def vip_command(client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("❌ Kullanım: /vip [user_id]")
            return
        
        target_user_id = int(parts[1])
        add_or_update_user(target_user_id)
        set_vip(target_user_id, True)
        
        await message.reply_text(f"✅ Kullanıcı {target_user_id} VIP yapıldı!")
        
        try:
            await bot.send_message(target_user_id, 
                "🌟 **Tebrikler!** VIP kullanıcı oldun!\n\n"
                "Artık sınırsız ve bekleme süresiz içerik çekebilirsin! 🚀")
        except:
            pass
            
    except ValueError:
        await message.reply_text("❌ Geçerli bir user ID gir!")
    except Exception as e:
        await message.reply_text(f"❌ Hata: {str(e)}")

@bot.on_message(filters.command("unvip") & filters.user(ADMINS))
async def unvip_command(client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("❌ Kullanım: /unvip [user_id]")
            return
        
        target_user_id = int(parts[1])
        set_vip(target_user_id, False)
        
        await message.reply_text(f"✅ Kullanıcı {target_user_id} VIP'liği kaldırıldı!")
        
    except ValueError:
        await message.reply_text("❌ Geçerli bir user ID gir!")
    except Exception as e:
        await message.reply_text(f"❌ Hata: {str(e)}")

@bot.on_message(filters.text & filters.private & ~filters.command(["start", "help", "stats", "vip", "unvip"]))
async def handle_link(client, message: Message):
    user_id = message.from_user.id
    add_or_update_user(user_id)
    
    user = get_user(user_id)
    is_vip = user[1] == 1 if user else False
    remaining = get_remaining_limit(user_id)
    
    # Limit kontrolü
    if not is_vip and remaining <= 0:
        await message.reply_text(
            "❌ **Günlük limitin doldu!**\n\n"
            "Yarın tekrar 3 hakkın olacak.\n"
            "Veya sınırsız erişim için VIP ol! 🌟"
        )
        return
    
    # Link parse etme
    text = message.text.strip()
    
    try:
        # Link formatını parse et
        if "t.me/" in text:
            parts = text.split("t.me/")[1].split("/")
            channel = parts[0]
            msg_id = int(parts[1]) if len(parts) > 1 else None
        elif text.startswith("@"):
            parts = text[1:].split("/")
            channel = parts[0]
            msg_id = int(parts[1]) if len(parts) > 1 else None
        else:
            await message.reply_text("❌ Geçersiz format! Örnek:\n`https://t.me/kanal/123` veya `@kanal/123`")
            return
        
        if msg_id is None:
            await message.reply_text("❌ Mesaj ID'si bulunamadı! Tam linki gönder.")
            return
        
        status_msg = await message.reply_text("⏳ İçerik çekiliyor, lütfen bekle...")
        
        # VIP değilse bekleme süresi ekle
        if not is_vip:
            await asyncio.sleep(3)
        
        # Userbot ile içerik çekme
        try:
            # Kanala katılmayı dene
            try:
                chat = await userbot.get_chat(channel)
            except:
                await userbot.join_chat(channel)
                chat = await userbot.get_chat(channel)
            
            # Mesajı çek
            msg = await userbot.get_messages(chat.id, msg_id)
            
            if msg is None:
                await status_msg.edit_text("❌ Mesaj bulunamadı!")
                return
            
            # Limiti düşür
            if not is_vip:
                use_limit(user_id)
                remaining -= 1
            
            # İçeriği kullanıcıya gönder
            caption = f"✅ İçerik çekildi!\n\n"
            if not is_vip:
                caption += f"📝 Kalan hakkın: {remaining}/3"
            
            if msg.text:
                await message.reply_text(msg.text + "\n\n" + caption)
            elif msg.photo:
                await message.reply_photo(msg.photo.file_id, caption=msg.caption or caption)
            elif msg.video:
                await message.reply_video(msg.video.file_id, caption=msg.caption or caption)
            elif msg.document:
                await message.reply_document(msg.document.file_id, caption=msg.caption or caption)
            elif msg.audio:
                await message.reply_audio(msg.audio.file_id, caption=msg.caption or caption)
            elif msg.voice:
                await message.reply_voice(msg.voice.file_id, caption=caption)
            else:
                await message.reply_text(f"✅ Mesaj çekildi ama desteklenmeyen format.\n\n{caption}")
            
            await status_msg.delete()
            
        except UserNotParticipant:
            await status_msg.edit_text("❌ Kanala katılamadım. Kanal gizli olabilir.")
        except ChannelPrivate:
            await status_msg.edit_text("❌ Bu kanal özel, erişim yok.")
        except FloodWait as e:
            await status_msg.edit_text(f"⏳ Telegram flood koruması devrede. {e.value} saniye bekle.")
        except Exception as e:
            await status_msg.edit_text(f"❌ Hata: {str(e)}")
            
    except Exception as e:
        await message.reply_text(f"❌ Link parse edilemedi: {str(e)}")

@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "help":
        await callback_query.message.edit_text("""
📚 **Yardım - Nasıl Kullanılır?**

**1️⃣ Link Gönder:**
Telegram mesaj linkini direkt gönder:
`https://t.me/kanal_adi/12345`

**2️⃣ Username Gönder:**
Kanal username'i ile:
`@kanal_adi/12345`

**3️⃣ Bot İşlemi Yapar:**
✅ Kanala userbot ile katılır
✅ İçeriği çeker
✅ Sana gönderir
""")
    elif data == "stats":
        user_id = callback_query.from_user.id
        user = get_user(user_id)
        
        if user is None:
            await callback_query.answer("Önce /start komutunu kullan!", show_alert=True)
            return
        
        is_vip = user[1] == 1
        total = user[4]
        limit = get_remaining_limit(user_id)
        
        stats_text = f"""
📊 **Senin İstatistiklerin**

👤 Kullanıcı ID: `{user_id}`
{'🌟 Durum: **VIP** (Sınırsız)' if is_vip else f'📝 Kalan günlük hak: **{limit}/3**'}
📥 Toplam çekilen içerik: **{total}**
"""
        
        await callback_query.message.edit_text(stats_text)
    
    await callback_query.answer()

async def main():
    init_db()
    
    # Her iki client'ı da başlat
    await bot.start()
    await userbot.start()
    
    me = await userbot.get_me()
    print("✅ Bot ve Userbot başlatıldı!")
    print(f"🤖 Bot username: @{(await bot.get_me()).username}")
    print(f"👤 Userbot: {me.first_name} (@{me.username})")
    
    # Botu çalışır durumda tut
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())

