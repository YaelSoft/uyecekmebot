import os
import asyncio
import threading
import sqlite3
import time
import sys
import shutil
from datetime import datetime
from telethon import TelegramClient, events, Button, functions
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Global Bot System Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []
OWNER_CONTACT = "@yasin33" 

# Başlangıç Zamanı
START_TIME = time.time()

# --- 3. DİL VE METİNLER ---
TEXTS = {
    "en": {
        "welcome": "👋 **Welcome!**\nSelect your language:",
        "menu": "🌟 **Dashboard**\n\n👤 ID: `{uid}`\n📊 Daily Limit: **{limit}/3**\n💎 VIP Status: {vip_status}\n\n📥 **Features:**\n1. Send Link -> Download Post\n2. `/story username` -> Download Stories (VIP)\n\n🆘 **Support:** `/help`",
        "help_msg": (
            "📚 **How to Use?**\n\n"
            "1️⃣ **Restricted Content:**\n"
            "• Send **Invite Link** (`t.me/+...`) first.\n"
            "• Then send the post link.\n\n"
            "2️⃣ **Story Saver (VIP):**\n"
            "• Type `/story username` (e.g. `/story kimkardashian`)\n"
            "• I will download all active stories.\n\n"
            "💎 **Buy VIP:** Contact **{contact}**"
        ),
        "limit_reached": f"⛔ **Limit Reached!**\nContact **{OWNER_CONTACT}** to buy VIP.",
        "vip_active": "✅ Active (Unlimited)",
        "vip_inactive": "❌ Free Plan",
        "queue": "⏳ **Queued (Wait 5s)...**",
        "processing": "🔄 **Processing...**",
        "downloading": "⬇️ **Downloading...**",
        "uploading": "⬆️ **Uploading...**",
        "story_search": "🔍 **Searching Stories for:** `{target}`...",
        "story_found": "✅ Found **{count}** stories. Downloading...",
        "story_none": "❌ No stories found or profile is private.",
        "error_access": "❌ **Access Denied!** Send Invite Link first.",
        "join_success": "✅ **Joined!** Now send the post link.",
        "join_fail": "❌ Failed to join.",
        "vip_only": "🔒 **VIP Only!**\nStories are for VIP members only."
    }
}

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

# --- 6. KOMUTLAR ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    u = get_user(uid)
    
    buttons = [
        [Button.inline("🇺🇸 English", b"set_lang_en"), Button.inline("🇩🇪 Deutsch", b"set_lang_de")],
        [Button.inline("🇹🇷 Türkçe", b"set_lang_tr")]
    ]
    await event.respond(TEXTS['en']['welcome'], buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"set_lang_"))
async def callback_handler(event):
    lang_code = event.data.decode().split("_")[-1]
    uid = event.sender_id
    update_lang(uid, 'en') # Global standart
    
    u = get_user(uid)
    vip_status = TEXTS['en']['vip_active'] if u[1] == 1 else TEXTS['en']['vip_inactive']
    msg = TEXTS['en']['menu'].format(uid=uid, limit=u[2], vip_status=vip_status)
    await event.edit(msg)

@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    await event.respond(TEXTS['en']['help_msg'].format(contact=OWNER_CONTACT))

# --- ADMİN PANELİ ---
@bot.on(events.NewMessage(pattern='/stats'))
async def stats(event):
    if event.sender_id not in ADMINS: return
    total, vips = get_stats()
    uptime = time.time() - START_TIME
    msg = f"📊 **Stats**\nUsers: `{total}`\nVIPs: `{vips}`\nUptime: `{int(uptime//3600)}h {int((uptime%3600)//60)}m`"
    await event.respond(msg)

@bot.on(events.NewMessage(pattern='/killall'))
async def killall(event):
    if event.sender_id not in ADMINS: return
    await event.respond("🔴 Restarting...")
    os._exit(0)

@bot.on(events.NewMessage(pattern='/vip'))
async def vip_add(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 1)
        await event.respond(f"✅ {t} is VIP.")
    except: await event.respond("Usage: `/vip ID`")

@bot.on(events.NewMessage(pattern='/unvip'))
async def vip_rem(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 0)
        await event.respond(f"❌ {t} is Normal.")
    except: pass

# --- YENİ: HİKAYE (STORY) İNDİRME ---
@bot.on(events.NewMessage(pattern='/story'))
async def story_downloader(event):
    uid = event.sender_id
    u = get_user(uid)
    
    # Sadece VIP ve Admin
    if uid not in ADMINS and u[1] == 0:
        await event.respond(TEXTS['en']['vip_only'])
        return

    try:
        args = event.message.text.split()
        if len(args) < 2:
            await event.respond("⚠️ Usage: `/story username`\nExample: `/story elonmusk`")
            return
        
        target = args[1].replace("@", "")
        status = await event.respond(TEXTS['en']['story_search'].format(target=target))
        
        # Userbot ile entityi bul
        try:
            entity = await userbot.get_entity(target)
        except:
            await status.edit("❌ User not found.")
            return

        # Storyleri Çek
        stories = await userbot(functions.stories.GetPeerStoriesRequest(peer=entity))
        
        if not stories.stories:
            await status.edit(TEXTS['en']['story_none'])
            return
            
        await status.edit(TEXTS['en']['story_found'].format(count=len(stories.stories)))
        
        count = 0
        for story in stories.stories:
            if story.media:
                try:
                    path = await userbot.download_media(story.media)
                    await bot.send_file(event.chat_id, path, caption=f"📹 Story from @{target}")
                    os.remove(path)
                    count += 1
                except: continue
        
        await status.delete()
        await event.respond(f"✅ **Done!** Downloaded {count} stories.")

    except Exception as e:
        await event.respond(f"❌ Error: {e}")

# --- TEKİL İNDİRME (RESTRICTED CONTENT) ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    limit = u[2]
    
    if uid not in ADMINS and not vip:
        if limit <= 0:
            await event.respond(TEXTS['en']['limit_reached'])
            return
        status = await event.respond(TEXTS['en']['queue'])
        await asyncio.sleep(4)
    else:
        status = await event.respond(TEXTS['en']['processing'])

    text = event.message.text.strip()

    try:
        # A) DAVET LİNKİ
        if "t.me/+" in text or "joinchat" in text:
            try:
                await userbot(ImportChatInviteRequest(text.split('+')[-1]))
                await status.edit(TEXTS['en']['join_success'])
            except UserAlreadyParticipantError:
                await status.edit(TEXTS['en']['join_success'])
            except:
                await status.edit(TEXTS['en']['join_fail'])
            return

        # B) İÇERİK
        if "t.me/" not in text:
            await status.edit("❌ Invalid Link."); return

        try:
            parts = text.rstrip('/').split('/')
            msg_id = int(parts[-1])
            if 't.me/c/' in text: entity = await userbot.get_entity(int('-100' + parts[-2]))
            else: entity = await userbot.get_entity(parts[-2])
            
            msg = await userbot.get_messages(entity, ids=msg_id)
        except:
            await status.edit(TEXTS['en']['error_access']); return

        if not msg or not msg.media:
            await status.edit("❌ No Media."); return

        await status.edit(TEXTS['en']['downloading'])
        path = await userbot.download_media(msg)
        
        await status.edit(TEXTS['en']['uploading'])
        await bot.send_file(event.chat_id, path, caption=msg.text or "")
        
        if os.path.exists(path): os.remove(path)
        
        if uid not in ADMINS and not vip: use_right(uid)
        
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Error: {e}")
        if 'path' in locals() and path and os.path.exists(path): os.remove(path)

# --- BAŞLATMA ---
def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 Commercial Bot Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
