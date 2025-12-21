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
    PeerIdInvalid, FloodWait, UsernameInvalid, ChannelInvalid
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
def home(): return "YaelSaver V55 (Cache Refresh) Active! 🟢"

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
    if datetime.now() < datetime.fromisoformat(join_str) + timedelta(hours=24): return True, "🟢 Deneme Sürümü"
    return False, "🔴 Süre Doldu"

def set_vip(user_id, is_vip):
    status = "VIP" if is_vip else "FREE"
    with sqlite3.connect(DB_NAME) as conn:
        try: conn.cursor().execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, status, datetime.now().isoformat()))
        except: conn.cursor().execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))

def get_stats():
    with sqlite3.connect(DB_NAME) as conn:
        total = conn.cursor().execute("SELECT count(*) FROM users").fetchone()[0]
        vips = conn.cursor().execute("SELECT count(*) FROM users WHERE status='VIP'").fetchone()[0]
    return total, vips

# ==================== 4. İSTEMCİLER ====================
init_db()
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("saver_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 5. MENÜLER ====================
def main_menu(user_id):
    btns = [
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="help_dl"),
         InlineKeyboardButton("👤 Hesabım", callback_data="my_account")],
        [InlineKeyboardButton("👑 VIP Menüsü", callback_data="vip_menu")],
        [InlineKeyboardButton("🛠 Satın Al: @yasin33", url="https://t.me/yasin33")]
    ]
    if user_id == OWNER_ID: btns.append([InlineKeyboardButton("👮‍♂️ Yönetici Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(btns)

def vip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Kanal Kopyala (Transfer)", callback_data="help_trans")],
        [InlineKeyboardButton("✨ VIP Avantajları", callback_data="vip_info")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ VIP Ekle", callback_data="how_add"), InlineKeyboardButton("➖ VIP Sil", callback_data="how_del")],
        [InlineKeyboardButton("📊 İstatistikler", callback_data="stats")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri Dön", callback_data="main")]])

# ==================== 6. START & CALLBACKS ====================
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply(f"⛔ **Süreniz Doldu!**"); return
    await message.reply(f"👋 **YaelSaver V55**\nℹ️ Durum: {status}", reply_markup=main_menu(user_id))

@bot.on_callback_query()
async def cb_handler(client, cb):
    uid = cb.from_user.id
    data = cb.data
    if data == "main": await cb.message.edit_text("👋 **Ana Menü**", reply_markup=main_menu(uid))
    elif data == "help_dl": await cb.message.edit_text("📥 Link at (`t.me/c/...`). Hata verirse davet linki at.", reply_markup=back_btn())
    elif data == "my_account": _, st = check_user_access(uid); await cb.message.edit_text(f"📊 {st}", reply_markup=back_btn())
    elif data == "vip_menu": await cb.message.edit_text("👑 **VIP Bölümü**", reply_markup=vip_menu())
    elif data == "help_trans": await cb.message.edit_text("🔄 `/transfer Kaynak Hedef Adet`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="vip_menu")]]))
    elif data == "vip_info": await cb.message.edit_text("✨ Sınırsız indirme.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="vip_menu")]]))
    elif data == "admin_panel":
        if uid != OWNER_ID: await cb.answer("Yasak!", show_alert=True); return
        await cb.message.edit_text("👮‍♂️ Admin", reply_markup=admin_menu())
    elif data == "stats": t, v = get_stats(); await cb.message.edit_text(f"👥 T: {t} | 💎 V: {v}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))

# ==================== 7. ZEKİ İNDİRİCİ (CACHE REFRESH ÖZELLİĞİ) ====================
async def refresh_dialogs():
    # Userbot'un tüm kanallarını bir kere çeker, böylece hafıza tazelenir
    async for dialog in userbot.get_dialogs(limit=50):
        pass

@bot.on_message(filters.regex(r"t\.me/") & filters.private)
async def link_handler(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ **Süre Doldu!**"); return

    text = message.text.strip()
    
    # A) DAVET LİNKİ
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Sızılıyor...**")
        try:
            await userbot.join_chat(text)
            await status_msg.edit("✅ **Girdim!**\nŞimdi içerik linkini tekrar at.")
        except UserAlreadyParticipant:
            await status_msg.edit("⚠️ **Zaten içerideyim.**\nİçerik linkini gönder.")
        except Exception as e:
            await status_msg.edit(f"❌ **Hata:** {e}")
        return

    # B) MESAJ LİNKİ
    status_msg = await message.reply("🔍 **Aranıyor...**")
    
    try:
        clean = text.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean:
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else:
            parts = clean.split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
            
        # --- KRİTİK FIX: HAFIZA TAZELEME DÖNGÜSÜ ---
        try:
            # 1. Deneme: Direkt çek
            msg = await userbot.get_messages(chat_id, msg_id)
        except (PeerIdInvalid, ChannelInvalid):
            # Hata verirse Hafıza Tazele (Cache Refresh)
            await status_msg.edit("🔄 **Sunucu Hafızası Tazeleniyor...**")
            await refresh_dialogs() # Sihirli satır burası
            try:
                # 2. Deneme: Tazelenmiş hafızayla çek
                msg = await userbot.get_messages(chat_id, msg_id)
            except:
                raise PeerIdInvalid # Yine olmazsa gerçekten yokuzdur.

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

    except (ChannelPrivate, PeerIdInvalid, ChannelInvalid):
        await status_msg.edit("⛔ **ERİŞİM YOK!**\nUserbot bu kanalda değil veya hafızada bulunamadı.\n\n👇 **Çözüm:**\nGrubun **Davet Linkini** at, girip hafızayı yenileyeyim.")
    except Exception as e:
        await status_msg.edit(f"❌ **Hata:** {e}")

# ==================== 8. TRANSFER ====================
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Sadece VIP!**"); return

    try:
        args = message.command
        src, dst, limit = int(args[1]), int(args[2]), int(args[3])
        status_msg = await message.reply("🚀 **Başlıyor...**")
        
        # Transferden önce de hafızayı tazele ki PeerID yemesin
        try:
            await userbot.get_chat(src)
        except:
            await refresh_dialogs()
            
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
        await status_msg.edit(f"✅ **Bitti!** Toplam: {count}")
    except: await message.reply("❌ Hata! `/transfer Kaynak Hedef Limit`")

# ==================== 9. ADMİN ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅")
@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌")

# ==================== 10. BAŞLATMA ====================
async def main():
    print("Sistem Başlatılıyor...")
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
