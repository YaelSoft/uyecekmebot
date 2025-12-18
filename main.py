import os
import asyncio
import threading
import sqlite3
import time
import sys
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V4.0 Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []
OWNER_CONTACT = "@yasin33" 

FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 

START_TIME = time.time()

# --- 3. DİL VE METİNLER ---
TEXTS = {
    "en": {
        "welcome": "👋 **Welcome!**\nSelect Language:",
        "lang_set": "✅ Language set to **English**.",
        "menu_vip": "💎 **VIP DASHBOARD**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNLIMITED**\n\n🔥 **Features:**\n• `/range link 100-200` -> Batch DL\n• `/topic_copy link limit` -> Topic DL\n• `/transfer src dst limit` -> Topic Transfer\n• **Note:** Text captions are removed automatically.",
        "menu_free": "👤 **FREE DASHBOARD**\n\nStatus: Free\nLimit: {limit}/3\n\nUsage: Send Link.",
        "vip_only": "🔒 **VIP Feature Only!**",
        "limit_reached": "⛔ **Limit Reached!** Contact Owner.",
        "processing": "🔄 **Processing...**",
        "downloading": "⬇️ **Downloading Media...**",
        "uploading": "⬆️ **Uploading (No Caption)...**",
        "error_access": "❌ Access Denied / Invalid Link"
    },
    "tr": {
        "welcome": "👋 **Hoş Geldiniz!**\nDil seçiniz:",
        "lang_set": "✅ Dil: **Türkçe**.",
        "menu_vip": "💎 **VIP PANELİ**\n\n🆔 ID: `{uid}`\n⚡ **Durum: SINIRSIZ**\n\n🔥 **Özellikler:**\n• `/range link 100-200` -> Aralıklı İndir\n• `/topic_copy link adet` -> Kategori İndir\n• `/transfer kaynak hedef adet` -> Kategori Transferi\n• **Not:** Orijinal metinler silinir, sadece medya aktarılır.",
        "menu_free": "👤 **ÜCRETSİZ PANEL**\n\nDurum: Ücretsiz\nHak: {limit}/3\n\nKullanım: Link gönder.",
        "vip_only": "🔒 **Sadece VIP!**",
        "limit_reached": "⛔ **Günlük Hak Bitti!**",
        "processing": "🔄 **İşleniyor...**",
        "downloading": "⬇️ **Medya İndiriliyor...**",
        "uploading": "⬆️ **Yükleniyor (Yazısız)...**",
        "error_access": "❌ Erişilemedi veya Link Hatalı"
    }
}

def get_text(lang, key):
    return TEXTS.get(lang, TEXTS['en']).get(key, TEXTS['en'].get(key, ""))

# --- 4. İSTEMCİLER ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 5. VERİTABANI ---
def init_db():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0, daily_limit INTEGER DEFAULT 3, last_reset TEXT, lang TEXT DEFAULT 'en')''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    today = datetime.now().strftime("%Y-%m-%d")
    if user is None:
        c.execute("INSERT INTO users (user_id, last_reset, lang) VALUES (?, ?, ?)", (user_id, today, 'en'))
        conn.commit(); conn.close(); return (user_id, 0, 3, today, 'en')
    if user[3] != today and user[1] == 0:
        c.execute("UPDATE users SET daily_limit=3, last_reset=? WHERE user_id=?", (today, user_id))
        conn.commit(); conn.close(); return (user_id, 0, 3, today, user[4])
    conn.close(); return user

def update_lang(user_id, lang_code):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang_code, user_id))
    conn.commit(); conn.close()

def use_right(user_id):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET daily_limit = daily_limit - 1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

def set_vip(user_id, status):
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    conn.execute("UPDATE users SET is_vip=? WHERE user_id=?", (status, user_id))
    conn.commit(); conn.close()

async def check_fsub(uid, lang):
    if not FSUB_CHANNEL or uid in ADMINS: return True
    try:
        await bot(GetParticipantRequest(FSUB_CHANNEL, uid))
        return True
    except UserNotParticipantError:
        link = f"https://t.me/{FSUB_CHANNEL.replace('@','')}" if str(FSUB_CHANNEL).startswith("@") else f"https://t.me/joinchat/{FSUB_CHANNEL}"
        buttons = [[Button.url("📢 Join Channel", link)], [Button.inline("✅ I Joined!", b"check_fsub")]]
        await bot.send_message(uid, TEXTS[lang].get('fsub_msg', "Join First"), buttons=buttons)
        return False
    except: return True

# --- 6. MENU ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    buttons = [[Button.inline("🇺🇸 English", b"set_lang_en"), Button.inline("🇹🇷 Türkçe", b"set_lang_tr")]]
    await event.respond(TEXTS['en']['welcome'], buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"set_lang_"))
async def callback_handler(event):
    lang_code = event.data.decode().split("_")[-1]
    uid = event.sender_id
    update_lang(uid, lang_code)
    u = get_user(uid)
    msg = get_text(lang_code, 'menu_vip').format(uid=uid) if (uid in ADMINS or u[1] == 1) else get_text(lang_code, 'menu_free').format(uid=uid, limit=u[2])
    await event.edit(msg)

# --- 7. ADMIN TOOLS ---
@bot.on(events.NewMessage(pattern='/vip'))
async def vip_add(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 1); await event.respond(f"✅ {t} VIP.")
    except: pass

@bot.on(events.NewMessage(pattern='/unvip'))
async def vip_rem(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 0); await event.respond(f"❌ {t} Normal.")
    except: pass

@bot.on(events.NewMessage(pattern='/broadcast'))
async def broadcast(event):
    if event.sender_id not in ADMINS: return
    try: msg = event.message.text.split(' ', 1)[1]
    except: return
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    for user in users:
        try: await bot.send_message(int(user[0]), msg)
        except: pass
    await event.respond("✅ Broadcast Done.")

# --- 8. YARDIMCI: ENTITY VE TOPIC ÇÖZÜCÜ (DÜZELTİLEN KISIM) ---
async def get_entity_and_topic(link):
    parts = link.rstrip('/').split('/')
    topic_id = None
    entity = None
    
    # Kanal ID'sini bul (t.me/c/KANAL_ID/...)
    if 't.me/c/' in link:
        c_index = parts.index('c')
        channel_id_part = parts[c_index + 1]
        group_id = int('-100' + channel_id_part)
        entity = await userbot.get_entity(group_id)
        
        # Topic ID Tespiti (HATA ÇÖZÜLDÜ)
        # Link: t.me/c/3610650322/10 -> parts[-1] = 10
        # channel_id_part = 3610650322
        
        # Sondaki parça sayıysa ve Kanal ID'ye eşit DEĞİLSE -> Topic ID'dir
        if parts[-1].isdigit():
            possible_id = int(parts[-1])
            if str(possible_id) != channel_id_part:
                topic_id = possible_id
                
        # Bazen link: .../TOPIC_ID/MSG_ID olur. O zaman sondan ikinciye bak
        if len(parts) > c_index + 2 and parts[-1].isdigit() and parts[-2].isdigit():
             possible_topic = int(parts[-2])
             if str(possible_topic) != channel_id_part:
                 topic_id = possible_topic

    else:
        # Public link: t.me/username/10
        username = parts[parts.index('t.me') + 1]
        entity = await userbot.get_entity(username)
        if parts[-1].isdigit():
            topic_id = int(parts[-1])

    return entity, topic_id

# --- 9. TRANSFER (TOPIC TO TOPIC) ---
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only'))
        return
    
    try:
        args = event.message.text.split()
        src_link = args[1]
        dst_link = args[2]
        # Limiti 100.000'e sabitle (Hata vermesin)
        limit = min(int(args[3]), 100000)
        
        status = await event.respond(f"🔄 **Transfer Başlıyor...**\nLimit: {limit}")

        src_entity, src_topic = await get_entity_and_topic(src_link)
        dst_entity, dst_topic = await get_entity_and_topic(dst_link)

        msgs = await userbot.get_messages(src_entity, limit=limit, reply_to=src_topic)
        
        count = 0
        for msg in reversed(msgs):
            if msg.media:
                try:
                    await userbot.send_message(
                        dst_entity, 
                        file=msg.media, 
                        message="", 
                        reply_to=dst_topic 
                    )
                    count += 1
                    await asyncio.sleep(2)
                except Exception as e: 
                    continue
                    
        await status.edit(f"✅ **Transfer Tamam!**\n📦 {count} Medya Taşındı.")

    except Exception as e: await event.respond(f"❌ Error: {e}")

# --- 10. DİĞER KOMUTLAR ---
@bot.on(events.NewMessage(pattern='/range'))
async def range_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if not await check_fsub(uid, lang): return
    if uid not in ADMINS and u[1] == 0: await event.respond(get_text(lang, 'vip_only')); return
    try:
        args = event.message.text.split(); link = args[1]; start, end = map(int, args[2].split('-'))
        status = await event.respond(f"Processing {start}-{end}...")
        entity, _ = await get_entity_and_topic(link)
        count = 0
        for i in range(start, end + 1):
            try:
                msg = await userbot.get_messages(entity, ids=i)
                if msg and msg.media:
                    path = await userbot.download_media(msg)
                    await bot.send_file(event.chat_id, path, caption="")
                    os.remove(path); count += 1
            except: continue
        await status.edit(f"✅ Range Done: {count}")
    except: await event.respond("❌ Error.")

@bot.on(events.NewMessage(pattern='/topic_copy'))
async def topic_copy(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0: await event.respond(get_text(lang, 'vip_only')); return
    try:
        args = event.message.text.split(); link = args[1]
        limit = min(int(args[2]), 100000) # Sabitleme
        
        status = await event.respond(f"🔍 Topic Scan ({limit} max)...")
        entity, topic_id = await get_entity_and_topic(link)
        
        if not topic_id: await status.edit("❌ No Topic ID detected."); return
        
        count = 0
        async for msg in userbot.iter_messages(entity, limit=limit, reply_to=topic_id):
            if not msg.media: continue
            try:
                path = await userbot.download_media(msg)
                await bot.send_file(event.chat_id, path, caption="")
                os.remove(path); count += 1; await asyncio.sleep(1)
            except: continue
        await status.edit(f"✅ Topic Done: {count}")
    except Exception as e: await event.respond(f"❌ Error: {e}")

@bot.on(events.NewMessage(pattern='/full_copy'))
async def full_copy(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0: await event.respond(get_text(lang, 'vip_only')); return
    try:
        args = event.message.text.split(); link = args[1]
        limit = min(int(args[2]), 100000) # Sabitleme
        
        status = await event.respond(f"🌍 Full Scan...")
        entity, _ = await get_entity_and_topic(link)
        count = 0
        async for msg in userbot.iter_messages(entity, limit=limit):
            if not msg.media: continue
            try:
                path = await userbot.download_media(msg)
                await bot.send_file(event.chat_id, path, caption="")
                os.remove(path); count += 1; await asyncio.sleep(1)
            except: continue
        await status.edit(f"✅ Full Done: {count}")
    except: await event.respond("❌ Error.")

@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    vip = u[1] == 1
    if not await check_fsub(uid, lang): return
    if uid not in ADMINS and not vip and u[2] <= 0: await event.respond(get_text(lang, 'limit_reached')); return
    
    status = await event.respond(get_text(lang, 'processing'))
    text = event.message.text.strip()
    try:
        if "t.me/+" in text: 
            try: await userbot(ImportChatInviteRequest(text.split('+')[-1])); await status.edit("✅ Joined.")
            except: await status.edit("✅ Joined/Fail.")
            return
        
        entity, _ = await get_entity_and_topic(text)
        parts = text.rstrip('/').split('/')
        msg_id = int(parts[-1])
        
        msg = await userbot.get_messages(entity, ids=msg_id)
        if msg.media:
            await status.edit(get_text(lang, 'downloading'))
            path = await userbot.download_media(msg)
            await status.edit(get_text(lang, 'uploading'))
            await bot.send_file(event.chat_id, path, caption="")
            os.remove(path)
            if uid not in ADMINS and not vip: use_right(uid)
            await status.delete()
        else: await status.edit("No media.")
    except: await status.edit(get_text(lang, 'error_access'))

def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
