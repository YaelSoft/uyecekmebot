import os
import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
from pyrogram.errors import (
    UserAlreadyParticipant, InviteHashExpired, ChannelPrivate, 
    PeerIdInvalid, FloodWait, UsernameInvalid
)

# ==================== 1. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# ==================== 2. WEB SERVER ====================
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
app = Flask(__name__)

@app.route('/')
def home(): return "YaelSaver V53 (VIP Panel) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== 3. VERİTABANI ====================
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
    
    if not res: 
        now = datetime.now().isoformat()
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', ?)", (user_id, now))
        conn.commit(); conn.close()
        return True, "🟢 Deneme (24 Saat)"
    
    status, join_str = res
    conn.close()
    
    if status == "VIP": return True, "💎 VIP Üye (Sınırsız)"
    
    if datetime.now() < datetime.fromisoformat(join_str) + timedelta(hours=24):
        return True, "🟢 Deneme Sürümü"
    return False, "🔴 Süre Doldu"

def set_vip(user_id, is_vip):
    status = "VIP" if is_vip else "FREE"
    with sqlite3.connect(DB_NAME) as conn:
        try: conn.cursor().execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, status, datetime.now().isoformat()))
        except: conn.cursor().execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    total = c.execute("SELECT count(*) FROM users").fetchone()[0]
    vips = c.execute("SELECT count(*) FROM users WHERE status='VIP'").fetchone()[0]
    conn.close()
    return total, vips

# ==================== 4. İSTEMCİLER ====================
init_db()
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("saver_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 5. MENÜLER (GELİŞMİŞ) ====================

def main_menu(user_id):
    btns = [
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="help_dl"),
         InlineKeyboardButton("👤 Hesabım", callback_data="my_account")],
        [InlineKeyboardButton("👑 VIP Menüsü (Transfer)", callback_data="vip_menu")],
        [InlineKeyboardButton("🛠 Satın Al: @yasin33", url="https://t.me/yasin33")]
    ]
    # SADECE SANA GÖRÜNEN BUTON
    if user_id == OWNER_ID:
        btns.append([InlineKeyboardButton("👮‍♂️ Yönetici Paneli", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(btns)

def vip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Kanal Kopyala (Transfer)", callback_data="help_trans")],
        [InlineKeyboardButton("✨ VIP Avantajları", callback_data="vip_info")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ VIP Ekle", callback_data="how_add"),
         InlineKeyboardButton("➖ VIP Sil", callback_data="how_del")],
        [InlineKeyboardButton("📊 İstatistikler", callback_data="stats")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri Dön", callback_data="main")]])

# ==================== 6. START & CALLBACKS ====================

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access:
        await message.reply(f"⛔ **Süreniz Doldu!**\nDevam etmek için: @yasin33")
    else:
        await message.reply(f"👋 **YaelSaver Paneline Hoşgeldiniz**\nℹ️ Durum: {status}", reply_markup=main_menu(user_id))

@bot.on_callback_query()
async def cb_handler(client, cb):
    uid = cb.from_user.id
    data = cb.data

    if data == "main":
        await cb.message.edit_text("👋 **Ana Menü**", reply_markup=main_menu(uid))
    
    # --- İÇERİK İNDİRME ---
    elif data == "help_dl":
        await cb.message.edit_text(
            "📥 **İçerik İndirme Asistanı**\n\n"
            "1. Bana herhangi bir Telegram mesaj linki at.\n"
            "   `https://t.me/c/12345/678`\n\n"
            "2. Eğer **'Erişim Yok'** dersem, o grubun davet linkini at.\n"
            "3. Ben gruba girdikten sonra linki tekrar at.",
            reply_markup=back_btn()
        )

    # --- HESABIM ---
    elif data == "my_account":
        _, status = check_user_access(uid)
        await cb.message.edit_text(f"👤 **Hesap Bilgileri**\n\n🆔 ID: `{uid}`\n📊 Lisans: **{status}**", reply_markup=back_btn())

    # --- VIP MENÜSÜ ---
    elif data == "vip_menu":
        await cb.message.edit_text("👑 **VIP İşlemleri**", reply_markup=vip_menu())

    elif data == "help_trans":
        await cb.message.edit_text(
            "🔄 **Kanal Transfer (Kopyalama)**\n\n"
            "Bir kanaldaki mesajları başka kanala toplu taşır.\n\n"
            "👇 **Komut:**\n"
            "`/transfer KaynakID HedefID Adet`\n\n"
            "**Örnek:**\n"
            "`/transfer -100987654 -100123456 100`\n\n"
            "⚠️ *Bot her iki kanalda da olmalıdır.*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 VIP Menü", callback_data="vip_menu")]])
        )

    elif data == "vip_info":
        await cb.message.edit_text(
            "✨ **VIP Avantajları**\n\n"
            "✅ Sınırsız İçerik İndirme\n"
            "✅ /transfer ile Toplu Kanal Kopyalama\n"
            "✅ Öncelikli İşlem Hızı\n"
            "✅ 7/24 Destek",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 VIP Menü", callback_data="vip_menu")]])
        )

    # --- YÖNETİCİ PANELİ ---
    elif data == "admin_panel":
        if uid != OWNER_ID: await cb.answer("Yasak!", show_alert=True); return
        await cb.message.edit_text("👮‍♂️ **Yönetici Paneli**", reply_markup=admin_menu())

    elif data == "how_add":
        await cb.message.edit_text("➕ **VIP Ekleme:**\n\n`/addvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))

    elif data == "how_del":
        await cb.message.edit_text("➖ **VIP Silme:**\n\n`/delvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))

    elif data == "stats":
        total, vips = get_stats()
        await cb.message.edit_text(f"📊 **İstatistikler**\n\n👥 Toplam Kullanıcı: {total}\n💎 VIP Kullanıcı: {vips}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]]))


# ==================== 7. İÇERİK ÇEKME (AKILLI SİSTEM) ====================
@bot.on_message(filters.regex(r"t\.me/") & filters.private)
async def link_handler(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ **Süreniz Doldu!**"); return

    text = message.text.strip()
    
    # A) DAVET LİNKİ (Join)
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Sızılıyor...**")
        try:
            await userbot.join_chat(text)
            await status_msg.edit("✅ **Girdim!** Şimdi mesaj linkini at.")
        except UserAlreadyParticipant:
            await status_msg.edit("⚠️ **Zaten İçerideyim.** Linki at.")
        except Exception as e:
            await status_msg.edit(f"❌ **Hata:** {e}")
        return

    # B) MESAJ LİNKİ (Download)
    status_msg = await message.reply("🔍 **Aranıyor...**")
    try:
        clean = text.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean:
            parts = clean.split("c/")[1].split("/")
            chat_id, msg_id = int("-100" + parts[0]), int(parts[1])
        else:
            parts = clean.split("/")
            chat_id, msg_id = parts[0], int(parts[1])
            
        msg = await userbot.get_messages(chat_id, msg_id)
        if not msg or msg.empty: raise ChannelPrivate("Boş")

        await status_msg.edit("📥 **İndiriliyor...**")
        if msg.media:
            path = await userbot.download_media(msg)
            if path:
                await status_msg.edit("📤 **Gönderiliyor...**")
                await client.send_document(user_id, path, caption=msg.caption or "")
                os.remove(path); await status_msg.delete()
        else:
            await client.send_message(user_id, msg.text)
            await status_msg.delete()

    except (ChannelPrivate, PeerIdInvalid, KeyError):
        await status_msg.edit("⛔ **Erişim Yok!**\nLütfen grubun davet linkini at.")
    except Exception as e:
        await status_msg.edit(f"❌ Hata: {e}")

# ==================== 8. VIP TRANSFER ====================
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Bu özellik VIP üyelere özeldir!**", reply_markup=vip_menu()); return

    try:
        args = message.command
        src, dst, limit = int(args[1]), int(args[2]), int(args[3])
        status_msg = await message.reply(f"🚀 **Transfer Başladı!** ({limit} adet)")
        count = 0
        async for msg in userbot.get_chat_history(src, limit=limit):
            try:
                if msg.media: await msg.copy(dst, caption=msg.caption)
                elif msg.text: await userbot.send_message(dst, msg.text)
                count += 1
                await asyncio.sleep(2)
                if count % 10 == 0: await status_msg.edit(f"🚀 Taşınan: {count}...")
            except FloodWait as e: await asyncio.sleep(e.value + 5)
            except: pass
        await status_msg.edit(f"✅ **Tamamlandı!** Toplam: {count}")
    except: await message.reply("❌ Hata! Kullanım: `/transfer Kaynak Hedef Limit`")

# ==================== 9. ADMİN KOMUTLARI ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅ VIP Verildi")

@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌ FREE Yapıldı")

# ==================== 10. BAŞLATMA ====================
async def main():
    print("Bot Başlatılıyor...")
    keep_alive()
    await bot.start()
    try: await userbot.start()
    except Exception as e: print(f"Userbot Hatası: {e}")
    await idle()
    await bot.stop()
    try: await userbot.stop()
    except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
