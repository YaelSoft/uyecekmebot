import os
import asyncio
import threading
import sqlite3
import time
import sys
from datetime import datetime
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from flask import Flask

# --- 1. RENDER WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver System Active!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. AYARLAR ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
ADMINS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []
OWNER_CONTACT = "@yasin33" 

# ZORUNLU ABONELİK KANALI (Kullanıcı Adı veya ID)
# Eğer boş bırakırsan özellik devre dışı kalır.
# Örnek: "@YaelCode" veya "-10012345678"
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 

START_TIME = time.time()

# --- 3. DİL VE METİNLER ---
TEXTS = {
    "en": {
        "welcome": "👋 **Welcome!**\nSelect Language:",
        "lang_set": "✅ Language set to **English**.",
        "menu_free": "👤 **FREE DASHBOARD**\n\n🆔 ID: `{uid}`\n📊 Limit: **{limit}/3**\n💎 Status: **Free**\n\n📥 **Usage:**\n1. **Public:** Send Link.\n2. **Private:** Send Invite Link -> Then Post Link.\n\n🚀 **Upgrade to VIP for:**\n✅ Unlimited Access\n✅ Batch (`/range`)\n✅ Priority Speed\n\n🛒 **Buy VIP:** {contact}",
        "menu_vip": "💎 **VIP DASHBOARD**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNLIMITED**\n\n🔥 **VIP Features:**\n• `/range link 100-150` -> Batch DL\n• `/transfer src dst count` -> Clone\n\n📥 **Usage:** Send any link!",
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
        "left_channel": "👋 **Left the channel.**",
        "fsub_msg": "⛔ **Access Denied!**\n\nYou must join our channel to use this bot.\n\n👇 **Join Here:**",
        "fsub_btn": "📢 Join Channel",
        "fsub_done": "✅ I Joined!",
        "vip_promoted": "🌟 **You are now VIP!**",
        "vip_removed": "❌ **VIP Removed.**",
        "restart_msg": "🔴 **System Restarting...**"
    },
    "de": {
        "welcome": "👋 **Willkommen!**\nSprache wählen:",
        "lang_set": "✅ Sprache: **Deutsch**.",
        "menu_free": "👤 **GRATIS MENÜ**\n\n🆔 ID: `{uid}`\n📊 Limit: **{limit}/3**\n💎 Status: **Gratis**\n\n📥 **Nutzung:**\n1. **Öffentlich:** Link senden.\n2. **Privat:** Einladungslink -> Dann Beitragslink.\n\n🚀 **VIP Vorteile:**\n✅ Unbegrenzt\n✅ Massen-DL (`/range`)\n\n🛒 **VIP Kaufen:** {contact}",
        "menu_vip": "💎 **VIP MENÜ**\n\n🆔 ID: `{uid}`\n⚡ **Status: UNBEGRENZT**\n\n🔥 **VIP Befehle:**\n• `/range link 100-150` -> Massen-DL\n• `/transfer` -> Klonen\n\n📥 **Nutzung:** Link senden!",
        "menu_admin": "👑 **CHEF PANEL**\n\n⚡ **Status: GOD MODE**\n\n👥 **Verwaltung:**\n• `/vip ID`\n• `/unvip ID`\n• `/stats`\n\n🛠 **Tools:**\n• `/transfer`\n• `/leave link`\n• `/killall`",
        "limit_reached": f"⛔ **Limit erreicht!**\nKontaktieren Sie **{OWNER_CONTACT}** für VIP.",
        "queue": "⏳ **Warte (5s)...**",
        "processing": "🔄 **Verarbeitung...**",
        "downloading": "⬇️ **Herunterladen...**",
        "uploading": "⬆️ **Hochladen...**",
        "join_success": "✅ **Beigetreten!** Link senden.",
        "join_fail": "❌ Fehler beim Beitritt.",
        "error_access": "❌ **Zugriff verweigert!**\nPrivat. Senden Sie erst den **Einladungslink** (`t.me/+...`).",
        "vip_only": "🔒 **Nur für VIP!**",
        "left_channel": "👋 **Kanal verlassen.**",
        "fsub_msg": "⛔ **Zugriff verweigert!**\n\nBitte treten Sie unserem Kanal bei.",
        "fsub_btn": "📢 Kanal beitreten",
        "fsub_done": "✅ Beigetreten!",
        "vip_promoted": "🌟 **Sie sind jetzt VIP!**",
        "vip_removed": "❌ **VIP entfernt.**",
        "restart_msg": "🔴 **Neustart...**"
    },
    "tr": {
        "welcome": "👋 **Hoş Geldiniz!**\nDil seçiniz:",
        "lang_set": "✅ Dil: **Türkçe**.",
        "menu_free": "👤 **ÜCRETSİZ PANEL**\n\n🆔 ID: `{uid}`\n📊 Hak: **{limit}/3**\n💎 Durum: **Ücretsiz**\n\n📥 **Kullanım:**\n1. **Normal:** Link gönder.\n2. **Gizli:** Önce Davet Linki -> Sonra Mesaj Linki.\n\n🚀 **VIP Özellikleri:**\n✅ Sınırsız İndirme\n✅ Toplu İndirme (`/range`)\n✅ Öncelikli Hız\n\n🛒 **VIP Satın Al:** {contact}",
        "menu_vip": "💎 **VIP PANELİ**\n\n🆔 ID: `{uid}`\n⚡ **Durum: SINIRSIZ**\n\n🔥 **VIP Komutları:**\n• `/range link 100-150` -> Toplu İndir\n• `/transfer` -> Kanal Kopyala\n\n📥 **Kullanım:** Link göndermen yeterli!",
        "menu_admin": "👑 **PATRON PANELİ**\n\n⚡ **Durum: YÖNETİCİ**\n\n👥 **Kullanıcı Yönetimi:**\n• `/vip ID` -> VIP Yap\n• `/unvip ID` -> İptal Et\n• `/stats` -> İstatistikler\n\n🛠 **Araçlar:**\n• `/transfer`\n• `/leave link` -> Gruptan Çık\n• `/killall` -> Yeniden Başlat",
        "limit_reached": f"⛔ **Günlük Hak Bitti!**\nSınırsız için **{OWNER_CONTACT}** ile görüşün.",
        "queue": "⏳ **Sırada (5sn)...**",
        "processing": "🔄 **İşleniyor...**",
        "downloading": "⬇️ **İndiriliyor...**",
        "uploading": "⬆️ **Yükleniyor...**",
        "join_success": "✅ **Girdim!** Şimdi linki at.",
        "join_fail": "❌ Gruba girilemedi.",
        "error_access": "❌ **Erişemiyorum!**\nBu gizli bir grup.\n💡 Önce **Davet Linkini** (`t.me/+...`) at.",
        "vip_only": "🔒 **Sadece VIP!**",
        "left_channel": "👋 **Kanaldan çıkıldı.**",
        "fsub_msg": "⛔ **Erişim Engellendi!**\n\nBotu kullanmak için kanalımıza katılmalısınız.\n\n👇 **Buradan Katıl:**",
        "fsub_btn": "📢 Kanala Katıl",
        "fsub_done": "✅ Katıldım!",
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

# --- YARDIMCI: ZORUNLU ABONELİK KONTROLÜ ---
async def check_fsub(uid, lang):
    if not FSUB_CHANNEL or uid in ADMINS: return True
    try:
        participant = await bot(GetParticipantRequest(FSUB_CHANNEL, uid))
        return True
    except UserNotParticipantError:
        # Link oluştur (Eğer @kullaniciadi ise direkt link, ID ise davet linki gerekir)
        if str(FSUB_CHANNEL).startswith("@"):
            link = f"https://t.me/{FSUB_CHANNEL.replace('@','')}"
        else:
            # ID ile çalışmak zordur, public username tavsiye edilir.
            link = f"https://t.me/joinchat/{FSUB_CHANNEL}" # Bu kısım değişkendir
            
        buttons = [
            [Button.url(TEXTS[lang]['fsub_btn'], link)],
            [Button.inline(TEXTS[lang]['fsub_done'], b"check_fsub")]
        ]
        await bot.send_message(uid, TEXTS[lang]['fsub_msg'], buttons=buttons)
        return False
    except:
        return True # Hata olursa engelleme (Güvenlik)

# --- 6. GİRİŞ VE MENÜ ---
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
    update_lang(uid, lang_code)
    
    # Dil seçildi, şimdi FSub kontrolü
    if not await check_fsub(uid, lang_code):
        return # Üye değilse durdur

    u = get_user(uid)
    vip = u[1] == 1
    
    if uid in ADMINS: msg = TEXTS[lang_code]['menu_admin']
    elif vip: msg = TEXTS[lang_code]['menu_vip'].format(uid=uid)
    else: msg = TEXTS[lang_code]['menu_free'].format(uid=uid, limit=u[2], contact=OWNER_CONTACT)
    await event.edit(msg)

@bot.on(events.CallbackQuery(pattern=b"check_fsub"))
async def fsub_check_handler(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    
    if await check_fsub(uid, lang):
        # Üye olmuş, menüyü göster
        vip = u[1] == 1
        if uid in ADMINS: msg = TEXTS[lang]['menu_admin']
        elif vip: msg = TEXTS[lang]['menu_vip'].format(uid=uid)
        else: msg = TEXTS[lang]['menu_free'].format(uid=uid, limit=u[2], contact=OWNER_CONTACT)
        await event.edit(msg)
    else:
        # Hala üye değil
        await event.answer("❌ Not Joined!", alert=True)

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

# --- 8. VIP ÖZELLİKLERİ ---

# A) RANGE DOWNLOAD
@bot.on(events.NewMessage(pattern='/range'))
async def range_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    
    # FSub Kontrolü
    if not await check_fsub(uid, lang): return

    if uid not in ADMINS and u[1] == 0:
        await event.respond(TEXTS[lang]['vip_only'])
        return
    await event.respond("Range Active.")

# B) TRANSFER
@bot.on(events.NewMessage(pattern='/transfer'))
async def transfer_dl(event):
    uid = event.sender_id
    u = get_user(uid)
    lang = u[4]
    if uid not in ADMINS and u[1] == 0:
        await event.respond(TEXTS[lang]['vip_only'])
        return
    await event.respond("Transfer Active.")


# --- 9. GENEL İNDİRİCİ ---
@bot.on(events.NewMessage)
async def downloader(event):
    if not event.is_private or event.message.text.startswith('/'): return
    
    uid = event.sender_id
    u = get_user(uid)
    vip = u[1] == 1
    limit = u[2]
    lang = u[4] if u[4] in TEXTS else 'en'
    
    # 1. ZORUNLU ABONELİK KONTROLÜ
    if not await check_fsub(uid, lang): return

    # 2. HAK KONTROLÜ
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

    text = event.message.text.strip()
    
    try:
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


