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
def home(): return "YaelSaver Ultimate Active!"
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
        "menu_free": "👤 **FREE DASHBOARD**\n\n🆔 ID: `{uid}`\n📊 Limit: **{limit}/3**\n💎 Status: **Free**\n\n📥 **Usage:**\n1. **Public:** Send Link.\n2. **Private:** Send Invite Link -> Then Post Link.",
        "menu_vip": "💎 **VIP DASHBOARD**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNLIMITED**\n\n🔥 **VIP Features:**\n• `/range link 100-150` -> Batch DL\n• `/topic_copy link count` -> Topic DL\n• `/transfer src dst count` -> Clone",
        "menu_admin": "👑 **BOSS PANEL**\n\n⚡ **Status: GOD MODE**\n\n👥 **Manage:**\n• `/vip ID`\n• `/unvip ID`\n• `/stats`\n• `/broadcast`\n\n🛠 **Tools:**\n• `/transfer`\n• `/topic_copy`\n• `/killall`",
        "limit_reached": f"⛔ **Limit Reached!**\nContact **{OWNER_CONTACT}** for VIP.",
        "queue": "⏳ **Queued (5s)...**",
        "processing": "🔄 **Processing...**",
        "downloading": "⬇️ **Downloading...**",
        "uploading": "⬆️ **Uploading...**",
        "join_success": "✅ **Joined!** Now send link.",
        "join_fail": "❌ Failed to join.",
        "error_access": "❌ **Access Denied!**\nPrivate Channel. Send **Invite Link** (`t.me/+...`) first.",
        "vip_only": "🔒 **VIP Feature Only!**",
        "fsub_msg": "⛔ **Access Denied!**\nJoin our channel first.",
        "fsub_btn": "📢 Join Channel",
        "fsub_done": "✅ I Joined!",
        "vip_promoted": "🌟 **You are now VIP!**",
        "restart_msg": "🔴 **System Restarting...**"
    },
    "tr": {
        "welcome": "👋 **Hoş Geldiniz!**\nDil seçiniz:",
        "lang_set": "✅ Dil: **Türkçe**.",
        "menu_free": "👤 **ÜCRETSİZ PANEL**\n\n🆔 ID: `{uid}`\n📊 Hak: **{limit}/3**\n💎 Durum: **Ücretsiz**\n\n📥 **Kullanım:**\n1. **Normal:** Link gönder.\n2. **Gizli:** Önce Davet Linki -> Sonra Mesaj Linki.",
        "menu_vip": "💎 **VIP PANELİ**\n\n🆔 ID: `{uid}`\n⚡ **Durum: SINIRSIZ**\n\n🔥 **VIP Komutları:**\n• `/range link 100-150` -> Toplu İndir\n• `/topic_copy link adet` -> Kategori İndir\n• `/transfer` -> Kanal Kopyala",
        "menu_admin": "👑 **PATRON PANELİ**\n\n⚡ **Durum: YÖNETİCİ**\n\n👥 **Yönetim:**\n• `/vip ID`\n• `/unvip ID`\n• `/stats`\n• `/broadcast`\n\n🛠 **Araçlar:**\n• `/transfer`\n• `/topic_copy`\n• `/killall`",
        "limit_reached": f"⛔ **Günlük Hak Bitti!**\nSınırsız için **{OWNER_CONTACT}** ile görüşün.",
        "queue": "⏳ **Sırada (5sn)...**",
        "processing": "🔄 **İşleniyor...**",
        "downloading": "⬇️ **İndiriliyor...**",
        "uploading": "⬆️ **Yükleniyor...**",
        "join_success": "✅ **Girdim!** Şimdi linki at.",
        "join_fail": "❌ Gruba girilemedi.",
        "error_access": "❌ **Erişemiyorum!**\nBu gizli bir grup.\n💡 Önce **Davet Linkini** (`t.me/+...`) at.",
        "vip_only": "🔒 **Sadece VIP!**",
        "fsub_msg": "⛔ **Erişim Engellendi!**\nBotu kullanmak için kanala katılmalısınız.",
        "fsub_btn": "📢 Kanala Katıl",
        "fsub_done": "✅ Katıldım!",
        "vip_promoted": "🌟 **Artık VIP Üyesiniz!**",
        "restart_msg": "🔴 **Sistem Yeniden Başlatılıyor...**"
    }
}

# Varsayılan dil fallback
def get_text(lang, key):
    return TEXTS.get(lang, TEXTS['en']).get(key, TEXTS['en'][key])

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

def get_stats():
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_vip=1")
    vips = c.fetchone()[0]
    conn.close()
    return total, vips

async def check_fsub(uid, lang):
    if not FSUB_CHANNEL or uid in ADMINS: return True
    try:
        await bot(GetParticipantRequest(FSUB_CHANNEL, uid))
        return True
    except UserNotParticipantError:
        link = f"https://t.me/{FSUB_CHANNEL.replace('@','')}" if str(FSUB_CHANNEL).startswith("@") else f"https://t.me/joinchat/{FSUB_CHANNEL}"
        buttons = [[Button.url(get_text(lang, 'fsub_btn'), link)], [Button.inline(get_text(lang, 'fsub_done'), b"check_fsub")]]
        await bot.send_message(uid, get_text(lang, 'fsub_msg'), buttons=buttons)
        return False
    except: return True

# --- 6. MENU & SETUP ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    buttons = [[Button.inline("🇺🇸 English", b"set_lang_en"), Button.inline("🇹🇷 Türkçe", b"set_lang_tr")]]
    await event.respond(TEXTS['en']['welcome'], buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"set_lang_"))
async def callback_handler(event):
    lang_code = event.data.decode().split("_")[-1]
    uid = event.sender_id
    update_lang(uid, lang_code)
    if not await check_fsub(uid, lang_code): return
    u = get_user(uid)
    msg = get_text(lang_code, 'menu_admin') if uid in ADMINS else (get_text(lang_code, 'menu_vip').format(uid=uid) if u[1] == 1 else get_text(lang_code, 'menu_free').format(uid=uid, limit=u[2]))
    await event.edit(msg)

@bot.on(events.CallbackQuery(pattern=b"check_fsub"))
async def fsub_check_handler(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if await check_fsub(uid, lang):
        msg = get_text(lang, 'menu_admin') if uid in ADMINS else (get_text(lang, 'menu_vip').format(uid=uid) if u[1] == 1 else get_text(lang, 'menu_free').format(uid=uid, limit=u[2]))
        await event.edit(msg)
    else: await event.answer("❌ Not Joined!", alert=True)

# --- 7. ADMIN TOOLS ---
@bot.on(events.NewMessage(pattern='/vip'))
async def vip_add(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 1)
        await bot.send_message(t, TEXTS['en']['vip_promoted'])
        await event.respond(f"✅ {t} VIP.")
    except: await event.respond("Usage: `/vip ID`")

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
    except: await event.respond("Usage: `/broadcast Msg`"); return
    status = await event.respond("📢 Sending...")
    conn = sqlite3.connect('musteri.db', check_same_thread=False)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    done = 0
    for user in users:
        try:
            await bot.send_message(int(user[0]), msg)
            done += 1
            await asyncio.sleep(0.1)
        except: pass
    await status.edit(f"✅ Done: {done}")

# --- 8. VIP FEATURES (RANGE, TRANSFER, TOPIC) ---

# A) TOPIC COPY (YENİ ÖZELLİK)
@bot.on(events.NewMessage(pattern='/topic_copy'))
async def topic_copy(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only'))
        return

    try:
        # /topic_copy [Link] [Adet]
        args = event.message.text.split()
        if len(args) < 3:
            await event.respond("⚠️ Usage: `/topic_copy [Link] [Limit]`")
            return
        
        full_link = args[1]
        limit = int(args[2])
        status = await event.respond(f"🔍 Scanning Topic ({limit} msgs)...")

        # Linkten ID'leri sök
        parts = full_link.rstrip('/').split('/')
        # Link tipi: t.me/c/123/858/900 veya t.me/username/858/900
        
        # Topic ID (Kategori ID) genelde sondan bir önceki veya sondan iki önceki olur
        # Eğer link bir mesaja işaret ediyorsa (örn: /893)
        if parts[-1].isdigit() and parts[-2].isdigit():
             topic_id = int(parts[-2])
        elif parts[-1].isdigit():
             topic_id = int(parts[-1])
        else:
            await status.edit("❌ Topic ID not found in link.")
            return

        if 't.me/c/' in full_link:
            group_id = int('-100' + parts[parts.index('c') + 1])
            entity = await userbot.get_entity(group_id)
        else:
            username = parts[parts.index('t.me') + 1]
            entity = await userbot.get_entity(username)

        count = 0
        async for msg in userbot.iter_messages(entity, limit=limit, reply_to=topic_id):
            if not msg.media: continue # Sadece medya
            try:
                path = await userbot.download_media(msg)
                await bot.send_file(event.chat_id, path, caption=f"📂 Topic: {topic_id}")
                os.remove(path)
                count += 1
                await asyncio.sleep(1)
            except: continue
        
        await status.edit(f"✅ **Done!** Extracted {count} media from Topic {topic_id}.")

    except Exception as e:
        await event.respond(f"❌ Error: {e}")

# B) RANGE DOWNLOAD
@bot.on(events.NewMessage(pattern='/range'))
async def range_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if not await check_fsub(uid, lang): return
    if uid not in ADMINS and u[1] == 0:
        await event.respond(get_text(lang, 'vip_only'))
        return
    
    try:
        args = event.message.text.split()
        link = args[1]
        start, end = map(int, args[2].split('-'))
        status = await event.respond(f"🎯 Processing {start}-{end}...")
        
        if 't.me/c/' in link: entity = await userbot.get_entity(int('-100' + link.split('/')[-2]))
        else: entity = await userbot.get_entity(link.split('/')[-1])
        
        count = 0
        for i in range(start, end + 1):
            try:
                msg = await userbot.get_messages(entity, ids=i)
                if msg and msg.media:
                    path = await userbot.download_media(msg)
                    await bot.send_file(event.chat_id, path)
                    os.remove(path)
                    count += 1
            except: continue
        await status.edit(f"✅ Batch Done: {count}")
    except Exception as e: await event.respond(f"❌ Error: {e}")

# C) TRANSFER
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
        limit = int(args[3])
        
        status = await event.respond(f"🔄 Transferring last {limit} msgs...")
        
        # Kaynak
        if 't.me/c/' in src_link: src_entity = await userbot.get_entity(int('-100' + src_link.split('/')[-2]))
        else: src_entity = await userbot.get_entity(src_link.split('/')[-1])
        
        # Hedef
        if 't.me/c/' in dst_link: dst_entity = await userbot.get_entity(int('-100' + dst_link.split('/')[-2]))
        else: dst_entity = await userbot.get_entity(dst_link.split('/')[-1])

        msgs = await userbot.get_messages(src_entity, limit=limit)
        count = 0
        for msg in reversed(msgs):
            if msg.media:
                try:
                    await userbot.send_message(dst_entity, file=msg.media, message=msg.text)
                    count += 1
                    await asyncio.sleep(2)
                except: continue
        await status.edit(f"✅ Transfer Done: {count}")
    except Exception as e: await event.respond(f"❌ Error: {e}")


# --- 9. SINGLE DOWNLOADER ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    vip = u[1] == 1
    limit = u[2]
    
    if not await check_fsub(uid, lang): return

    if uid not in ADMINS:
        if not vip:
            if limit <= 0: await event.respond(get_text(lang, 'limit_reached')); return
            status = await event.respond(get_text(lang, 'queue')); await asyncio.sleep(4)
        else: status = await event.respond(get_text(lang, 'processing'))
    else: status = await event.respond(get_text(lang, 'processing'))

    text = event.message.text.strip()
    try:
        if "t.me/+" in text or "joinchat" in text:
            try:
                await userbot(ImportChatInviteRequest(text.split('+')[-1]))
                await status.edit(get_text(lang, 'join_success'))
            except UserAlreadyParticipantError: await status.edit(get_text(lang, 'join_success'))
            except: await status.edit(get_text(lang, 'join_fail'))
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
                await bot.send_file(event.chat_id, path, caption=msg.text or "")
                os.remove(path)
                if uid not in ADMINS and not vip: use_right(uid)
                await status.delete()
            else: await status.edit("No media.")
    except Exception as e:
        await status.edit(get_text(lang, 'error_access'))

def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
