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
from telethon.tl.types import MessageMediaStory
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver Ultimate System Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []
OWNER_CONTACT = "@yasin33" 

START_TIME = time.time()

# --- 3. DİL VE METİNLER ---
TEXTS = {
    "en": {
        "welcome": "👋 **Welcome!**\nSelect Language:",
        "lang_set": "✅ Language set to **English**.",
        "menu_free": "👤 **FREE DASHBOARD**\n\n🆔 ID: `{uid}`\n📊 Limit: **{limit}/3**\n💎 Status: **Free**\n\n📥 **Usage:**\n1. **Link:** Send any link.\n2. **Story:** Forward the story to me.\n\n🚀 **VIP:**\n✅ Unlimited Access\n✅ Stories (`/story`)\n✅ Batch (`/range`)\n\n🛒 **Buy VIP:** {contact}",
        "menu_vip": "💎 **VIP DASHBOARD**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNLIMITED**\n\n🔥 **VIP Features:**\n• `/story username` -> All Stories\n• `/range link 100-150` -> Batch DL\n• **Forward Story** -> Instant Download\n\n📥 **Usage:** Send Link or Forward Story!",
        "menu_admin": "👑 **BOSS PANEL**\n\n⚡ **Status: GOD MODE**\n\n👥 **Manage:**\n• `/vip ID`\n• `/unvip ID`\n• `/stats`\n\n🛠 **Tools:**\n• `/transfer`\n• `/leave link`\n• `/killall`",
        "limit_reached": f"⛔ **Limit Reached!**\nContact **{OWNER_CONTACT}** for VIP.",
        "queue": "⏳ **Queued (5s)...**",
        "processing": "🔄 **Processing...**",
        "downloading": "⬇️ **Downloading...**",
        "uploading": "⬆️ **Uploading...**",
        "join_success": "✅ **Joined!** Now send link.",
        "join_fail": "❌ Failed to join.",
        "error_access": "❌ **Access Denied!**\nPrivate Channel. Send **Invite Link** (`t.me/+...`) first.",
        "vip_only": "🔒 **VIP Feature Only!**",
        
        "story_detect": "👁‍🗨 **Story Detected!** Downloading...",
        "story_search": "🔍 **Searching Stories:** `@{target}`...",
        "story_found": "✅ **{count}** stories found. Downloading...",
        "story_dl_status": "⬇️ Downloading {current}/{total}...",
        "story_none": "❌ **No Stories Found.**\nProfile might be private.",
        "story_retry": "🔓 **Profile Hidden.** Trying to bypass...",
        "story_done": "🏁 **All Stories Sent!**",
        
        "vip_promoted": "🌟 **You are now VIP!**",
        "vip_removed": "❌ **VIP Removed.**",
        "restart_msg": "🔴 **System Restarting...**"
    },
    "de": {
        # ... (Almanca Metinler)
        "welcome": "👋 **Willkommen!**",
        "story_detect": "👁‍🗨 **Story erkannt!** Lade herunter...",
        "limit_reached": f"⛔ **Limit erreicht!**",
        "error_access": "❌ **Zugriff verweigert!**"
    },
    "tr": {
        "welcome": "👋 **Hoş Geldiniz!**\nDil seçiniz:",
        "lang_set": "✅ Dil: **Türkçe**.",
        "menu_free": "👤 **ÜCRETSİZ PANEL**\n\n🆔 ID: `{uid}`\n📊 Hak: **{limit}/3**\n💎 Durum: **Ücretsiz**\n\n📥 **Kullanım:**\n1. **Link:** Link gönder.\n2. **Hikaye:** Hikayeyi bana ilet.\n\n🚀 **VIP Özellikleri:**\n✅ Sınırsız İndirme\n✅ Hikaye (`/story`)\n✅ Toplu İndirme (`/range`)\n\n🛒 **VIP Satın Al:** {contact}",
        "menu_vip": "💎 **VIP PANELİ**\n\n🆔 ID: `{uid}`\n⚡ **Durum: SINIRSIZ**\n\n🔥 **VIP Komutları:**\n• `/story kullanıcı` -> Tüm Hikayeler\n• `/range link 100-150` -> Toplu İndir\n• **Hikayeyi İlet** -> Anında İndir\n\n📥 **Kullanım:** Link at veya Hikaye İlet!",
        "menu_admin": "👑 **PATRON PANELİ**\n\n⚡ **Durum: YÖNETİCİ**\n\n👥 **Kullanıcı Yönetimi:**\n• `/vip ID` -> VIP Yap\n• `/unvip ID` -> İptal Et\n• `/stats` -> İstatistikler\n\n🛠 **Araçlar:**\n• `/transfer`\n• `/leave link` -> Gruptan Çık\n• `/killall` -> Yeniden Başlat",
        "limit_reached": f"⛔ **Günlük Hak Bitti!**\nSınırsız için **{OWNER_CONTACT}** ile görüşün.",
        "queue": "⏳ **Sırada (5sn)...**",
        "processing": "🔄 **İşleniyor...**",
        "downloading": "⬇️ **İndiriliyor...**",
        "uploading": "⬆️ **Yükleniyor...**",
        
        "story_detect": "👁‍🗨 **Hikaye Algılandı!** İndiriliyor...",
        "story_search": "🔍 **Hikayeler Aranıyor:** `@{target}`...",
        "story_found": "✅ **{count}** hikaye bulundu. İndiriliyor...",
        "story_dl_status": "⬇️ İndiriliyor: {current}/{total}...",
        "story_none": "❌ **Hikaye Bulunamadı.**\nProfil gizli olabilir.",
        "story_retry": "🔓 **Profil Gizli.** Rehbere ekleyip deneniyor...",
        "story_done": "🏁 **Tüm Hikayeler Gönderildi!**",
        
        "join_success": "✅ **Girdim!** Şimdi linki at.",
        "join_fail": "❌ Gruba girilemedi.",
        "error_access": "❌ **Erişemiyorum!**\nBu gizli bir grup.\n💡 Önce **Davet Linkini** (`t.me/+...`) at.",
        "vip_only": "🔒 **Sadece VIP!**",
        "vip_promoted": "🌟 **Artık VIP Üyesiniz!**",
        "vip_removed": "❌ **VIP İptal Edildi.**",
        "restart_msg": "🔴 **Sistem Yeniden Başlatılıyor...**"
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

# --- 6. GİRİŞ VE MENÜ ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    buttons = [
        [Button.inline("🇺🇸 English", b"set_lang_en"), Button.inline("🇩🇪 Deutsch", b"set_lang_de")],
        [Button.inline("🇹🇷 Türkçe", b"set_lang_tr")]
    ]
    await event.respond(TEXTS['en']['welcome'], buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"set_lang_"))
async def callback_handler(event):
    lang_code = event.data.decode().split("_")[-1] 
    uid = event.sender_id
    update_lang(uid, lang_code)
    u = get_user(uid)
    vip = u[1] == 1
    
    if uid in ADMINS: msg = TEXTS[lang_code]['menu_admin']
    elif vip: msg = TEXTS[lang_code]['menu_vip'].format(uid=uid)
    else: msg = TEXTS[lang_code]['menu_free'].format(uid=uid, limit=u[2], contact=OWNER_CONTACT)
    await event.edit(msg)

@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    await event.respond(f"🆘 **Support:** Contact {OWNER_CONTACT}")

# --- 7. ADMIN KOMUTLARI ---
@bot.on(events.NewMessage(pattern='/stats'))
async def stats(event):
    if event.sender_id not in ADMINS: return
    total, vips = get_stats()
    uptime = time.time() - START_TIME
    msg = f"📊 **Stats**\nUsers: `{total}`\nVIPs: `{vips}`\nUptime: `{int(uptime//3600)}h`"
    await event.respond(msg)

@bot.on(events.NewMessage(pattern='/killall'))
async def killall(event):
    if event.sender_id not in ADMINS: return
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4] if u[4] in TEXTS else 'en'
    await event.respond(TEXTS[lang]['restart_msg'])
    os._exit(0)

@bot.on(events.NewMessage(pattern='/vip'))
async def vip_add(event):
    if event.sender_id not in ADMINS: return
    try:
        t = int(event.message.text.split()[1])
        set_vip(t, 1)
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

@bot.on(events.NewMessage(pattern='/leave'))
async def leave_channel(event):
    if event.sender_id not in ADMINS: return
    try:
        args = event.message.text.split()
        link = args[1]
        if 't.me/c/' in link: entity = await userbot.get_entity(int('-100' + link.split('/')[-2]))
        else: entity = await userbot.get_entity(link.split('/')[-1])
        await userbot(LeaveChannelRequest(entity))
        await event.respond("👋 Left.")
    except: await event.respond("❌ Error.")

# --- 8. VIP HİKAYE (KOMUTLA) ---
@bot.on(events.NewMessage(pattern='/story'))
async def story_cmd(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4] if u[4] in TEXTS else 'en'
    
    if uid not in ADMINS and u[1] == 0:
        await event.respond(TEXTS[lang]['vip_only'])
        return
    
    try:
        args = event.message.text.split()
        if len(args) < 2: 
            await event.respond("⚠️ Usage: `/story username`")
            return
        target = args[1].replace("@", "")
        await download_stories(event, target, lang)
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

async def download_stories(event, target, lang):
    status = await event.respond(TEXTS[lang]['story_search'].format(target=target))
    try:
        entity = await userbot.get_entity(target)
    except:
        await status.edit(TEXTS[lang]['story_none'])
        return

    try:
        stories = await userbot.get_stories(entity)
    except:
        stories = []

    if not stories:
        await status.edit(TEXTS[lang]['story_retry'])
        try:
            await userbot(AddContactRequest(id=entity, first_name="Story", last_name="Temp", phone="", add_phone_privacy_exception=False))
            await asyncio.sleep(2)
            stories = await userbot.get_stories(entity)
        except: pass

    if not stories:
        await status.edit(TEXTS[lang]['story_none'])
        return

    await status.edit(TEXTS[lang]['story_found'].format(count=len(stories)))
    
    for i, story in enumerate(stories):
        if story.media:
            try:
                await status.edit(TEXTS[lang]['story_dl_status'].format(current=i+1, total=len(stories)))
                path = await userbot.download_media(story.media)
                await bot.send_file(event.chat_id, path, caption=f"📹 @{target}")
                os.remove(path)
            except: continue
    
    await status.delete()
    await event.respond(TEXTS[lang]['story_done'])

# --- 9. GENEL İNDİRİCİ (İLETİLEN STORY & LİNKLER) ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    limit = u[2]
    lang = u[4] if u[4] in TEXTS else 'en'
    
    # Hak Kontrolü
    if uid not in ADMINS:
        if not vip:
            if limit <= 0:
                await event.respond(TEXTS[lang]['limit_reached'])
                return
            status = await event.respond(TEXTS[lang]['queue'])
            await asyncio.sleep(4)
        else:
            status = await event.respond(TEXTS[lang]['processing'])
    else:
        status = await event.respond(TEXTS[lang]['processing'])

    # --- ÖNEMLİ: HİKAYE İLETİLİRSE YAKALA ---
    # Eğer mesajda "MessageMediaStory" varsa (İletilen hikaye)
    if event.message.media and isinstance(event.message.media, MessageMediaStory):
        await status.edit(TEXTS[lang]['story_detect'])
        try:
            # Userbot yetkisiyle indir
            path = await userbot.download_media(event.message.media)
            await status.edit(TEXTS[lang]['uploading'])
            await bot.send_file(event.chat_id, path, caption="📹 Saved Story")
            os.remove(path)
            await status.delete()
            
            if uid not in ADMINS and not vip: use_right(uid)
            return
        except Exception as e:
            await status.edit(f"❌ Error: {e}")
            return

    # Normal Metin Linkleri
    text = event.message.text.strip()
    
    try:
        # /s/ Linki (Story Linki)
        if "/s/" in text:
            try:
                parts = text.rstrip('/').split('/')
                # t.me/username/s/123 -> Username ve ID'yi al
                if 't.me' in parts:
                    idx = parts.index('t.me') + 1
                    target_user = parts[idx]
                    story_id = int(parts[-1])
                    
                    await status.edit(TEXTS[lang]['story_search'].format(target=target_user))
                    entity = await userbot.get_entity(target_user)
                    
                    # Tekli Story
                    stories = await userbot.get_stories(entity, ids=[story_id])
                    if stories and stories[0].media:
                        await status.edit(TEXTS[lang]['downloading'])
                        path = await userbot.download_media(stories[0].media)
                        await status.edit(TEXTS[lang]['uploading'])
                        await bot.send_file(event.chat_id, path, caption=f"📹 Story: @{target_user}")
                        os.remove(path)
                        await status.delete()
                        
                        if uid not in ADMINS and not vip: use_right(uid)
                    else:
                        await status.edit(TEXTS[lang]['story_none'])
            except Exception as e:
                await status.edit(f"❌ Error: {e}")
            return

        # Normal Linkler
        if "t.me/+" in text:
            try:
                await userbot(ImportChatInviteRequest(text.split('+')[-1]))
                await status.edit(TEXTS[lang]['join_success'])
            except UserAlreadyParticipantError:
                await status.edit(TEXTS[lang]['join_success'])
            except:
                await status.edit(TEXTS[lang]['join_fail'])
            return

        if "t.me/" in text:
            parts = text.rstrip('/').split('/')
            msg_id = int(parts[-1])
            if 't.me/c/' in text: entity = await userbot.get_entity(int('-100' + parts[-2]))
            else: entity = await userbot.get_entity(parts[-2])
            
            msg = await userbot.get_messages(entity, ids=msg_id)
            if msg.media:
                await status.edit(TEXTS[lang]['downloading'])
                path = await userbot.download_media(msg)
                await status.edit(TEXTS[lang]['uploading'])
                await bot.send_file(event.chat_id, path, caption=msg.text or "")
                os.remove(path)
                
                if uid not in ADMINS and not vip: use_right(uid)
                await status.delete()
            else: await status.edit("No media.")
            
    except Exception as e:
        err_msg = TEXTS[lang].get('error_access', TEXTS['en']['error_access'])
        await status.edit(err_msg)

def main():
    init_db()
    threading.Thread(target=run_web).start()
    print("🚀 System Active!")
    userbot.start()
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
