import os
import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    UserAlreadyParticipant, InviteHashExpired, ChannelPrivate, 
    PeerIdInvalid, FloodWait, UsernameInvalid
)

# ==================== 1. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") # Userbot İçin Şart!
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# ==================== 2. WEB SERVER (7/24) ====================
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V52 Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== 3. VERİTABANI & LİSANS ====================
DB_NAME = "yaelsaver.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT, join_date TEXT)''')
    conn.commit(); conn.close()

def check_user_access(user_id):
    if user_id == OWNER_ID: return True, "👑 Yönetici (Sınırsız)"
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT status, join_date FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if not res: # Yeni kullanıcı
        now = datetime.now().isoformat()
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', ?)", (user_id, now))
        conn.commit(); conn.close()
        return True, "🟢 Deneme (24 Saat)"
    
    status, join_str = res
    conn.close()
    
    if status == "VIP": return True, "💎 VIP Üye (Sınırsız)"
    
    # 24 Saat Kontrolü
    if datetime.now() < datetime.fromisoformat(join_str) + timedelta(hours=24):
        return True, "🟢 Deneme Sürümü"
    return False, "🔴 Süre Doldu"

def set_vip(user_id, is_vip):
    status = "VIP" if is_vip else "FREE"
    with sqlite3.connect(DB_NAME) as conn:
        try: conn.cursor().execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, status, datetime.now().isoformat()))
        except: conn.cursor().execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))

# ==================== 4. İSTEMCİLER ====================
init_db()
# Bot: Müşteriyle konuşan
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
# Userbot: İçeriği çalan (gizli) eleman
userbot = Client("saver_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 5. MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="help_dl"),
         InlineKeyboardButton("🔄 Transfer (VIP)", callback_data="help_trans")],
        [InlineKeyboardButton("👤 Hesabım", callback_data="my_account"),
         InlineKeyboardButton("🛠 Satın Al: @yasin33", url="https://t.me/yasin33")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="main")]])

# ==================== 6. START & EYLEMLER ====================

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    access, status = check_user_access(message.from_user.id)
    if not access:
        await message.reply(f"⛔ **Süreniz Doldu!**\nDevam etmek için: @yasin33")
    else:
        await message.reply(f"👋 **YaelSaver İçerik Botu**\nℹ️ Durum: {status}\n\nLink at, indireyim.", reply_markup=main_menu())

@bot.on_callback_query()
async def cb_handler(client, cb):
    if cb.data == "main": await cb.message.edit_text("👋 **Ana Menü**", reply_markup=main_menu())
    elif cb.data == "help_dl": await cb.message.edit_text("📥 **Nasıl İndirilir?**\n\n1. `t.me/c/...` şeklindeki mesaj linkini at.\n2. Eğer 'Giremiyorum' dersem, grubun **Davet Linkini** at.\n3. Ben girdikten sonra tekrar linki at.", reply_markup=back_btn())
    elif cb.data == "help_trans": await cb.message.edit_text("🔄 **Transfer (VIP):**\n\n`/transfer KaynakID HedefID Adet`\nÖrn: `/transfer -100123 -100456 50`\n(Bot her iki tarafta da olmalı)", reply_markup=back_btn())
    elif cb.data == "my_account": 
        _, status = check_user_access(cb.from_user.id)
        await cb.message.edit_text(f"📊 **Durum:** {status}", reply_markup=back_btn())

# ==================== 7. AKILLI İNDİRME SİSTEMİ (THE BRAIN) ====================

@bot.on_message(filters.regex(r"t\.me/") & filters.private)
async def link_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # 1. Lisans Kontrolü
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ **Süre Doldu!**\nSatın al: @yasin33"); return

    # 2. Link Analizi: Bu bir DAVET mi yoksa MESAJ mı?
    
    # A) DAVET LİNKİ İSE (Join)
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Gizli Gruba Sızılıyor...**")
        try:
            await userbot.join_chat(text)
            await status_msg.edit("✅ **Sızma Başarılı!**\nŞimdi az önce indiremediğin mesaj linkini tekrar gönder.")
        except UserAlreadyParticipant:
            await status_msg.edit("⚠️ **Zaten İçerideyim.**\nLütfen mesaj linkini gönder.")
        except Exception as e:
            await status_msg.edit(f"❌ **Giremedim:** Link geçersiz veya banlanmışım.\nHata: {e}")
        return

    # B) MESAJ LİNKİ İSE (Download)
    status_msg = await message.reply("🔍 **İçerik Aranıyor...**")
    
    try:
        # Linkten ID ve Mesaj ID çıkarma
        clean = text.replace("https://t.me/", "").replace("@", "")
        chat_id = None
        msg_id = None
        
        if "c/" in clean: # Private (c/112233/55)
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else: # Public (username/55)
            parts = clean.split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
            
        # USERBOT İLE ÇEKMEYİ DENE
        msg = await userbot.get_messages(chat_id, msg_id)
        
        if not msg or msg.empty:
            raise ChannelPrivate("Boş mesaj")

        # İNDİRME
        await status_msg.edit("📥 **İndiriliyor...**")
        
        if msg.media:
            # Dosyayı indir
            path = await userbot.download_media(msg)
            if path:
                await status_msg.edit("📤 **Size Gönderiliyor...**")
                
                # REKLAMSIZ CAPTION (Sadece orijinal yazı)
                orj_caption = msg.caption if msg.caption else ""
                
                await client.send_document(user_id, path, caption=orj_caption)
                
                # Temizlik
                os.remove(path)
                await status_msg.delete()
        else:
            # Sadece yazıysa
            await client.send_message(user_id, msg.text)
            await status_msg.delete()

    except (ChannelPrivate, PeerIdInvalid, KeyError, ValueError):
        # Userbot kanalda değilse veya banlıysa buraya düşer
        await status_msg.edit(
            "⛔ **ERİŞİM ENGELİ!**\n\n"
            "Userbot bu gizli grupta değil.\n"
            "👇 **Ne Yapmalısın?**\n"
            "Grubun **Davet Linkini** (`t.me/+...`) bana gönder.\n"
            "Otomatik girip içeriği çekeceğim."
        )
    except Exception as e:
        await status_msg.edit(f"❌ **Hata:** {e}")

# ==================== 8. VIP TRANSFER (KOPYALAMA) ====================
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    
    # Sadece VIP ve Yönetici kullanabilir
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Bu özellik sadece VIP üyelere özeldir!**"); return

    try:
        # /transfer Kaynak Hedef Adet
        args = message.command
        if len(args) < 4:
            await message.reply("⚠️ **Kullanım:** `/transfer [KaynakID] [HedefID] [Adet]`\nÖrn: `/transfer -100123 -100456 50`")
            return
            
        src = int(args[1])
        dst = int(args[2])
        limit = int(args[3])
        
        status_msg = await message.reply(f"🚀 **Transfer Başladı!**\n{limit} mesaj kopyalanıyor...")
        
        count = 0
        async for msg in userbot.get_chat_history(src, limit=limit):
            try:
                # Userbot ile kopyala (Hızlıdır)
                if msg.media: 
                    await msg.copy(dst, caption=msg.caption)
                elif msg.text: 
                    await userbot.send_message(dst, msg.text)
                
                count += 1
                await asyncio.sleep(2) # Flood yememek için 2 saniye bekle
                
                if count % 10 == 0:
                    await status_msg.edit(f"🚀 **Devam Ediyor...**\nTaşınan: {count}")
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
            except Exception:
                pass
        
        await status_msg.edit(f"✅ **Transfer Tamamlandı!**\nToplam {count} içerik taşındı.")

    except Exception as e:
        await message.reply(f"❌ Hata: {e}")

# ==================== 9. ADMİN KOMUTLARI ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅ VIP Yapıldı")

@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌ FREE Yapıldı")

# ==================== 10. BAŞLATMA ====================
async def main():
    print("🚀 Bot Başlatılıyor...")
    keep_alive() # Web server
    
    await bot.start()
    print("✅ Bot Aktif!")
    
    try:
        await userbot.start()
        print("✅ Userbot Aktif!")
    except Exception as e:
        print(f"⚠️ Userbot Hatası: {e}")
        
    await idle()
    await bot.stop()
    try: await userbot.stop()
    except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
