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
def home(): return "YaelSaver Pure Media Mode Active!"
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
        "menu_vip": "💎 **VIP DASHBOARD**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNLIMITED**\n\n🔥 **Features:**\n• `/range link 100-200` -> Batch DL\n• `/topic_copy link limit` -> Single Category\n• `/full_copy link limit` -> ALL Categories\n• **Note:** Text captions are removed automatically.",
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
        "menu_vip": "💎 **VIP PANELİ**\n\n🆔 ID: `{uid}`\n⚡ **Durum: SINIRSIZ**\n\n🔥 **Özellikler:**\n• `/range link 100-200` -> Aralıklı İndir\n• `/topic_copy link adet` -> Tek Kategoriyi İndir\n• `/full_copy link adet` -> TÜM Kategorileri İndir\n• **Not:** Orijinal metinler otomatik silinir, sadece medya gelir.",
        "menu_free": "👤 **ÜCRETSİZ PANEL**\n\nDurum: Ücretsiz\nHak: {limit}/3\n\nKullanım: Link gönder.",
        "vip_only": "🔒 **Sadece VIP!**",
        "limit_reached": "⛔ **Günlük Hak Bitti!**",
        "processing": "🔄 **İşleniyor...**",
        "downloading": "⬇️ **Medya İndiriliyor...**",
        "uploading": "⬆️ **Yükleniyor (Yazısız)...**",
        "error_access": "❌ Erişilemedi veya Link Hatalı"
    }
}

# Fallback text
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
        set_vip(t, 1)
        await event.respond(f"✅ {t} VIP.")
    except: pass

@bot.on(events.NewMessage(pattern='/unvip'))
async def vip_rem(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 0)
        await event.respond(f"❌ {t} Normal.")
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

# --- 8. VIP ÖZELLİKLERİ ---

# A) FULL COPY (TÜM KATEGORİLER KARIŞIK)
@bot.on(events.NewMessage(pattern='/full_copy'))
async def full_copy(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only'))
        return

    try:
        # /full_copy [GrupLink] [Adet]
        args = event.message.text.split()
        link = args[1]
        limit = int(args[2])
        status = await event.respond(f"🌍 Full Group Scan ({limit} msgs)...")

        # Grup Entity Bul
        if 't.me/c/' in link:
            # Private link: t.me/c/123456/... -> ID: -100123456
            parts = link.split('/')
            group_id = int('-100' + parts[parts.index('c') + 1])
            entity = await userbot.get_entity(group_id)
        else:
            # Public link
            entity = await userbot.get_entity(link.split('/')[-1])

        count = 0
        # reply_to=None demek tüm mesajları gez demektir (Topic fark etmez)
        async for msg in userbot.iter_messages(entity, limit=limit):
            if not msg.media: continue # Sadece medya
            
            try:
                path = await userbot.download_media(msg)
                # CAPTION BOŞ ("") GÖNDERİLİYOR -> Orijinal metin silinir
                await bot.send_file(event.chat_id, path, caption="") 
                os.remove(path)
                count += 1
                await asyncio.sleep(1)
            except: continue
        
        await status.edit(f"✅ **Full Copy Done!** {count} media extracted.")

    except Exception as e: await event.respond(f"❌ Error: {e}")


# B) TOPIC COPY (TEK KATEGORİ)
@bot.on(events.NewMessage(pattern='/topic_copy'))
async def topic_copy(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only'))
        return

    try:
        args = event.message.text.split()
        link = args[1]
        limit = int(args[2])
        status = await event.respond(f"🔍 Topic Scan ({limit} msgs)...")

        parts = link.rstrip('/').split('/')
        # Topic ID bulma
        if parts[-1].isdigit() and parts[-2].isdigit(): topic_id = int(parts[-2])
        elif parts[-1].isdigit(): topic_id = int(parts[-1])
        else: await status.edit("❌ Topic ID not found"); return

        if 't.me/c/' in link:
            group_id = int('-100' + parts[parts.index('c') + 1])
            entity = await userbot.get_entity(group_id)
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)

        count = 0
        async for msg in userbot.iter_messages(entity, limit=limit, reply_to=topic_id):
            if not msg.media: continue
            try:
                path = await userbot.download_media(msg)
                # CAPTION BOŞ ("") GÖNDERİLİYOR
                await bot.send_file(event.chat_id, path, caption="") 
                os.remove(path)
                count += 1
                await asyncio.sleep(1)
            except: continue
        
        await status.edit(f"✅ **Topic Done!** {count} media.")

    except Exception as e: await event.respond(f"❌ Error: {e}")


# C) RANGE (ARALIKLI)
@bot.on(events.NewMessage(pattern='/range'))
async def range_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only')); return
    
    try:
        args = event.message.text.split()
        link = args[1]
        start, end = map(int, args[2].split('-'))
        status = await event.respond(f"Processing {start}-{end}...")
        
        if 't.me/c/' in link: entity = await userbot.get_entity(int('-100' + link.split('/')[-2]))
        else: entity = await userbot.get_entity(link.split('/')[-1])
        
        count = 0
        for i in range(start, end + 1):
            try:
                msg = await userbot.get_messages(entity, ids=i)
                if msg and msg.media:
                    path = await userbot.download_media(msg)
                    # CAPTION BOŞ
                    await bot.send_file(event.chat_id, path, caption="")
                    os.remove(path)
                    count += 1
            except: continue
        await status.edit(f"✅ Range Done: {count}")
    except: await event.respond("❌ Error.")


# --- 9. TEKLİ İNDİRME ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    
    if uid not in ADMINS and u[1] == 0 and u[2] <= 0:
        await event.respond(get_text(lang, 'limit_reached')); return
    
    status = await event.respond(get_text(lang, 'processing'))
    text = event.message.text.strip()
    
    try:
        if "t.me/+" in text:
            try: await userbot(ImportChatInviteRequest(text.split('+')[-1])); await status.edit("✅ Joined.")
            except: await status.edit("❌ Failed.")
            return

        if "t.me/" in text:
            parts = text.rstrip('/').split('/')
            msg_id = int(parts[-1])
            if 't.me/c/' in text: entity = await userbot.get_entity(int('-100' + parts[-2]))
            else: entity = await userbot.get_entity(parts[-2])
            
            msg = await userbot.get_messages(entity, ids=msg_id)
            if msg.media:
                await status.edit(get_text(lang, 'downloading'))
                path = await userbot.download_media(msg)
                await status.edit(get_text(lang, 'uploading'))
                # CAPTION BOŞ ("") - Yazıyı çöpe at, medyayı gönder
                await bot.send_file(event.chat_id, path, caption="")
                os.remove(path)
                if uid not in ADMINS and u[1] == 0: use_right(uid)
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
