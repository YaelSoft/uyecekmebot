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
    PeerIdInvalid, FloodWait
)

# ==================== 1. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") # Userbot İçin
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# ==================== 2. WEB SERVER (7/24) ====================
logging.basicConfig(level=logging.INFO)
# Gereksiz logları sustur
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSystem V51 Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== 3. VERİTABANI ====================
DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Kullanıcılar ve Lisans
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT, join_date TEXT)''')
    # Kanal Yönetim Ayarları
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, channel_id INTEGER, auto_approve INTEGER DEFAULT 0, welcome_msg TEXT)''')
    # Zamanlayıcı
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled_posts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, channel_id INTEGER, message_id INTEGER, run_time TEXT)''')
    conn.commit()
    conn.close()

# --- DB Yardımcıları ---
def check_user_access(user_id):
    if user_id == OWNER_ID: return True, "👑 Yönetici"
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT status, join_date FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not res:
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', ?)", (user_id, datetime.now().isoformat()))
        conn.commit(); conn.close()
        return True, "🟢 Deneme (24 Saat)"
    status, join_str = res
    conn.close()
    if status == "VIP": return True, "💎 VIP Üye"
    if datetime.now() < datetime.fromisoformat(join_str) + timedelta(hours=24): return True, "🟢 Deneme Sürümü"
    return False, "🔴 Süre Doldu"

def set_vip(user_id, is_vip):
    status = "VIP" if is_vip else "FREE"
    with sqlite3.connect(DB_NAME) as conn:
        try: conn.cursor().execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, status, datetime.now().isoformat()))
        except: conn.cursor().execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))

def set_user_channel(user_id, channel_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        conn.cursor().execute("UPDATE user_settings SET channel_id=? WHERE user_id=?", (channel_id, user_id))

def get_user_channel(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT channel_id FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    return res[0] if res else None

def set_approve_status(user_id, status):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        conn.cursor().execute("UPDATE user_settings SET auto_approve=? WHERE user_id=?", (status, user_id))

def get_settings_by_channel(channel_id):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.cursor().execute("SELECT auto_approve, welcome_msg FROM user_settings WHERE channel_id=?", (channel_id,)).fetchone()
    return res if res else (0, None)

def add_schedule(user_id, channel_id, message_id, run_time):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute("INSERT INTO scheduled_posts (user_id, channel_id, message_id, run_time) VALUES (?, ?, ?, ?)", (user_id, channel_id, message_id, run_time.isoformat()))

def get_due_posts():
    posts = []
    with sqlite3.connect(DB_NAME) as conn:
        now = datetime.now().isoformat()
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM scheduled_posts WHERE run_time <= ?", (now,)).fetchall()
        for row in rows:
            posts.append(row)
            cursor.execute("DELETE FROM scheduled_posts WHERE id=?", (row[0],))
        conn.commit()
    return posts

# ==================== 4. İSTEMCİLER ====================
init_db()
# Bot (Yönetim İçin)
bot = Client("manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
# Userbot (İçerik Çekmek İçin)
userbot = Client("saver_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 5. MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="info_dl"),
         InlineKeyboardButton("🔄 Transfer Yap", callback_data="info_transfer")],
        [InlineKeyboardButton("💣 Süreli Mesaj", callback_data="info_flash"),
         InlineKeyboardButton("⏳ Zamanlayıcı", callback_data="info_schedule")],
        [InlineKeyboardButton("🔘 Butonlu Post", callback_data="info_buton"),
         InlineKeyboardButton("📢 Direkt Post", callback_data="info_post")],
        [InlineKeyboardButton("🔐 Oto Onay", callback_data="info_approve"),
         InlineKeyboardButton("👤 Hesabım", callback_data="info_account")],
        [InlineKeyboardButton("⚙️ KANAL DEĞİŞTİR", callback_data="change_channel")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]])

# ==================== 6. START & KURULUM ====================

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access:
        await message.reply(f"⛔ **{status}**\nDevam etmek için: @yasin33")
        return

    channel_id = get_user_channel(user_id)
    if not channel_id:
        await message.reply("👋 **Hoşgeldin!**\n\nÖnce yönetmek istediğin kanaldan bana bir mesaj ilet (forward yap) ki orayı hafızaya alayım.")
    else:
        await message.reply(f"👋 **Sistem Hazır!**\nℹ️ Durum: {status}\n📺 Kanal: `{channel_id}`", reply_markup=main_menu())

@bot.on_message(filters.forwarded & filters.private)
async def set_channel(client, message):
    if not message.forward_from_chat:
        await message.reply("❌ Bu bir kanal mesajı değil.")
        return
    if message.forward_from_chat.type not in [enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP, enums.ChatType.GROUP]:
        await message.reply("❌ Sadece Kanal/Grup bağlayabilirsin.")
        return
    
    set_user_channel(message.from_user.id, message.forward_from_chat.id)
    await message.reply(f"✅ **Kanal Bağlandı!**\nID: `{message.forward_from_chat.id}`\n\nMenüden işlemlere başla.", reply_markup=main_menu())

# ==================== 7. İÇERİK ÇEKME (AKILLI SİSTEM) ====================

# Kullanıcı link attığında (Komutsuz)
@bot.on_message(filters.regex(r"t\.me/") & filters.private)
async def smart_downloader(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Hak Kontrolü
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ Süreniz Doldu!"); return

    # A) DAVET LİNKİ Mİ? (Join)
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Sızılıyor...**")
        try:
            # Userbot ile gir
            join_link = text.strip()
            await userbot.join_chat(join_link)
            await status_msg.edit("✅ **Girdim!**\nŞimdi içerik linkini (mesaj linkini) tekrar at, indireyim.")
        except UserAlreadyParticipant:
            await status_msg.edit("⚠️ **Zaten içerideyim.** Linki gönder indireyim.")
        except Exception as e:
            await status_msg.edit(f"❌ **Giremedim:** {e}")
        return

    # B) İÇERİK LİNKİ Mİ? (Download)
    status_msg = await message.reply("🔍 **Analiz ediliyor...**")
    
    chat_id = None
    msg_id = None
    
    try:
        # Link Çözümleme
        clean = text.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean: # Private (c/123456/789)
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else: # Public (username/789)
            parts = clean.split("/")
            chat_id = parts[0] # Username
            msg_id = int(parts[1])
    except:
        await status_msg.edit("❌ Geçersiz Link."); return

    # Userbot ile çekmeyi dene
    try:
        msg = await userbot.get_messages(chat_id, msg_id)
        
        if not msg or msg.empty:
            raise ChannelPrivate # Mesaj boşsa erişim yok demektir

        await status_msg.edit("📥 **İndiriliyor...**")
        
        # Dosya mı Yazı mı?
        if msg.media:
            path = await userbot.download_media(msg)
            if path:
                await status_msg.edit("📤 **Yükleniyor...**")
                # REKLAMSIZ CAPTION (Yasin33 yazısı yok)
                caption = msg.caption if msg.caption else ""
                await client.send_document(user_id, path, caption=caption)
                os.remove(path)
                await status_msg.delete()
        else:
            await client.send_message(user_id, msg.text)
            await status_msg.delete()
            
    except (ChannelPrivate, PeerIdInvalid, KeyError):
        # Userbot içeride değilse buraya düşer
        await status_msg.edit(
            "⛔ **ERİŞİM YOK!**\n\n"
            "Userbot bu gizli grupta değil.\n"
            "👇 **Çözüm:**\n"
            "Grubun **Davet Linkini** (`t.me/+...`) bana at, otomatik gireyim."
        )
    except Exception as e:
        await status_msg.edit(f"❌ Hata: {e}")

# ==================== 8. KANAL YÖNETİM KOMUTLARI ====================

async def ensure_channel(client, message):
    cid = get_user_channel(message.from_user.id)
    if not cid: await message.reply("⚠️ Önce kanal bağla."); return None
    return int(cid)

@bot.on_message(filters.command("flash") & filters.private)
async def flash(c, m):
    cid = await ensure_channel(c, m)
    if not cid or not m.reply_to_message: return
    try:
        raw = m.command[1]
        sec = int(raw.replace("m", "")) * 60 if "m" in raw else int(raw)
        sent = await m.reply_to_message.copy(cid)
        alrt = await c.send_message(cid, f"⏳ {raw} sonra silinecek!", reply_to_message_id=sent.id)
        await m.reply("✅")
        await asyncio.sleep(sec)
        try: await sent.delete(); await alrt.delete()
        except: pass
    except: await m.reply("❌ Bot yetkisiz veya format yanlış.")

@bot.on_message(filters.command("buton") & filters.private)
async def buton(c, m):
    cid = await ensure_channel(c, m)
    if not cid or not m.reply_to_message: return
    try:
        nm, ur = m.text.split(None, 1)[1].split("|")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton(nm.strip(), url=ur.strip())]])
        await m.reply_to_message.copy(cid, reply_markup=btn)
        await m.reply("✅")
    except: await m.reply("⚠️ `/buton İsim | Link`")

@bot.on_message(filters.command("zamanla") & filters.private)
async def schedule(c, m):
    cid = await ensure_channel(c, m)
    if not cid or not m.reply_to_message: return
    try:
        raw = m.command[1]
        d = int(raw.replace("h", "")) * 3600 if "h" in raw else int(raw.replace("m", "")) * 60
        add_schedule(m.from_user.id, cid, m.reply_to_message.id, datetime.now()+timedelta(seconds=d))
        await m.reply(f"✅ Planlandı: {raw}")
    except: await m.reply("❌ Hata")

@bot.on_message(filters.command("post") & filters.private)
async def post(c, m):
    cid = await ensure_channel(c, m)
    if not cid or not m.reply_to_message: return
    try: await m.reply_to_message.copy(cid); await m.reply("✅")
    except: await m.reply("❌ Yetki yok.")

# --- TRANSFER (Geri Döndü!) ---
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(c, m):
    user_id = m.from_user.id
    access, status = check_user_access(user_id)
    if not access: await m.reply("⛔ Süre Doldu"); return
    
    # Sadece VIP'ler kullanabilsin (İstersen kaldırabilirsin)
    if "VIP" not in status and user_id != OWNER_ID:
        await m.reply("🔒 Transfer sadece VIP üyelere özeldir."); return

    try:
        # /transfer Kaynak Hedef Limit
        args = m.command
        src = int(args[1])
        dst = int(args[2])
        limit = int(args[3])
        
        status_msg = await m.reply(f"🚀 **Transfer Başladı!**\n{limit} mesaj taşınıyor...")
        
        count = 0
        async for msg in userbot.get_chat_history(src, limit=limit):
            try:
                if msg.media: await msg.copy(dst, caption=msg.caption)
                elif msg.text: await userbot.send_message(dst, msg.text)
                count += 1
                await asyncio.sleep(2) # Flood yememek için yavaşlatma
            except: pass
            
        await status_msg.edit(f"✅ **Tamamlandı!**\nToplam: {count} mesaj.")
    except Exception as e:
        await m.reply(f"❌ Hata: {e}\nKullanım: `/transfer -100Kaynak -100Hedef 10`")

# --- OTO ONAY ---
@bot.on_chat_join_request()
async def auto_approve_handler(client, req: ChatJoinRequest):
    sets = get_settings_by_channel(req.chat.id)
    if sets and sets[0] == 1:
        try: await client.approve_chat_join_request(req.chat.id, req.from_user.id)
        except: pass

@bot.on_message(filters.command("otoonay") & filters.private)
async def set_approve(c, m):
    if not await ensure_channel(c, m): return
    try:
        if m.command[1] == "ac": set_approve_status(m.from_user.id, 1); await m.reply("✅ Açıldı")
        else: set_approve_status(m.from_user.id, 0); await m.reply("❌ Kapatıldı")
    except: await m.reply("`/otoonay ac`")

# --- ADMİN VE CALLBACK ---
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("OK")
@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("OK")

@bot.on_callback_query()
async def cb_handler(client, cb):
    if cb.data == "main": await cb.message.edit_text("👋 **Ana Menü**", reply_markup=main_menu())
    elif cb.data == "change_channel": await cb.message.edit_text("🔄 Kanaldan mesaj ilet.", reply_markup=back_btn())
    elif cb.data == "info_dl": await cb.message.edit_text("📥 **Nasıl İndirilir?**\nDirekt linki atman yeterli.\nÖrn: `t.me/c/123/4`\n\n⚠️ Eğer 'Erişim Yok' dersem davet linki at.", reply_markup=back_btn())
    elif cb.data == "info_transfer": await cb.message.edit_text("🔄 **Transfer (VIP):**\n`/transfer KaynakID HedefID Limit`", reply_markup=back_btn())
    # Diğerleri aynı...
    else: await cb.message.edit_text("Komutu kullanın.", reply_markup=back_btn())

# ==================== 8. BAŞLATMA ====================
async def scheduler_task():
    while True:
        await asyncio.sleep(60)
        try:
            posts = get_due_posts()
            if posts:
                for p in posts:
                    try: await bot.copy_message(p[2], p[1], p[3])
                    except: pass
        except: pass

async def main():
    print("Sistem Başlatılıyor...")
    await bot.start()
    print("✅ Bot Aktif!")
    try:
        await userbot.start()
        print("✅ Userbot Aktif!")
    except Exception as e:
        print(f"⚠️ Userbot Hatası (Session String Kontrol Et): {e}")

    asyncio.create_task(scheduler_task())
    await idle()
    await bot.stop()
    try: await userbot.stop()
    except: pass

if __name__ == '__main__':
    keep_alive()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
