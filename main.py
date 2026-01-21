import os
import json
import time
import asyncio
import logging
import datetime
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) 
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")

# GÖRSEL (Hata verirse otomatik devre dışı kalır)
BOT_IMAGE = "https://github.com/YaelSoft/uyecekmebot/raw/a946c9c8f33435a5f6ff9ee65bcfd353f5156d9b/logo.jpeg"

# 💰 FİYATLANDIRMA
PRICE_15_TL = "300 TL"
PRICE_15_STARS = "600 ⭐"
PRICE_30_TL = "500 TL"
PRICE_30_STARS = "1000 ⭐"

# SİSTEM
DB_FILE = "users_backup.json" 
BACKUP_INTERVAL = 3600 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV9.5")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V9.5 Active 🟢"
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI ====================
db_cache = {}
is_dirty = False 

async def restore_data():
    if LOG_CHANNEL == 0: return {}
    try:
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=5):
            if msg.document and msg.document.file_name == "yael_db.json":
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f: return json.load(f)
    except: pass
    return {}

async def save_now(reason="Otomatik"):
    global is_dirty
    if LOG_CHANNEL != 0 and db_cache:
        try:
            with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
            await bot.send_document(LOG_CHANNEL, document=DB_FILE, file_name="yael_db.json", caption=f"💾 Yedek ({reason})\n👥 Üye: {len(db_cache)}")
            is_dirty = False
        except: pass

async def backup_task():
    while True:
        await asyncio.sleep(BACKUP_INTERVAL)
        if is_dirty: await save_now(reason="Saatlik")

# ==================== ⏳ EXPIRE KONTROL ====================
async def check_expirations_task():
    while True:
        try:
            now = time.time()
            for uid, data in db_cache.items():
                vip_until = data.get("vip_until", 0)
                if vip_until > 0 and now > vip_until:
                    data["vip_until"] = 0
                    global is_dirty
                    is_dirty = True
                    try:
                        await bot.send_message(int(uid), "⏳ **VIP SÜRENİZ DOLDU!**\nStandart üyeliğe geçtiniz.")
                    except: pass
        except: pass
        await asyncio.sleep(BACKUP_INTERVAL)

async def reload_userbot_cache():
    try:
        async for dialog in userbot.get_dialogs(): pass 
    except: pass

# --- KULLANICI FONKSİYONLARI ---
def get_user(user_id):
    global is_dirty
    uid = str(user_id)
    if uid not in db_cache:
        db_cache[uid] = {"balance": 3, "invited_by": None, "vip_until": 0}
        is_dirty = True
    return db_cache[uid]

def is_user_vip(user_id):
    u = get_user(user_id)
    if u.get("vip_until", 0) > time.time(): return True
    return False

def add_vip_days(user_id, days):
    global is_dirty
    uid = str(user_id)
    if uid not in db_cache: get_user(uid)
    current_expiry = db_cache[uid].get("vip_until", 0)
    now = time.time()
    if current_expiry > now: new_expiry = current_expiry + (days * 86400)
    else: new_expiry = now + (days * 86400)
    db_cache[uid]["vip_until"] = new_expiry
    is_dirty = True
    return new_expiry

def update_balance(user_id, amount):
    global is_dirty
    uid = str(user_id)
    if uid in db_cache:
        if is_user_vip(user_id) and amount < 0: return 
        db_cache[uid]["balance"] += amount
        is_dirty = True

def add_ref(user_id, referrer_id):
    global is_dirty
    uid = str(user_id)
    rid = str(referrer_id)
    if uid == rid or uid not in db_cache: return False
    if db_cache[uid].get("invited_by") is None:
        db_cache[uid]["invited_by"] = rid
        if rid in db_cache: db_cache[rid]["balance"] += 2
        is_dirty = True
        return True
    return False

# ==================== 🛠️ AKILLI MENÜ ====================
async def smart_edit(message, text, reply_markup=None):
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup, disable_web_page_preview=True)
    except: pass

# ==================== 👑 YÖNETİCİ PANELİ ====================
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    total = len(db_cache)
    active_vips = sum(1 for u in db_cache.values() if u.get("vip_until", 0) > time.time())
    status = "⚠️ Kayıt Bekliyor" if is_dirty else "✅ Güncel"
    text = (
        f"👑 **PATRON PANELİ**\n\n👥 Üye: `{total}`\n🌟 VIP: `{active_vips}`\n💾 Durum: {status}\n\n"
        f"⚙️ `/addvip ID GÜN`\n⚙️ `/delvip ID`\n⚙️ `/add ID MİKTAR`\n⚙️ `/duyuru MESAJ`"
    )
    await message.reply(text)

@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def add_vip_cmd(client, message):
    try:
        uid = message.command[1]
        days = int(message.command[2])
        new_expiry = add_vip_days(uid, days)
        date_str = datetime.datetime.fromtimestamp(new_expiry).strftime('%d.%m.%Y')
        await message.reply(f"✅ `{uid}` -> {days} Gün eklendi.\nBitiş: {date_str}")
        try: await client.send_message(int(uid), f"🎉 **TEBRİKLER!**\n\n{days} Günlük PRO PAKET tanımlandı.\n📅 Bitiş: {date_str}\n🚀 İyi kullanımlar!")
        except: pass
    except: await message.reply("❌ Hata: `/addvip ID GÜN`")

@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def del_vip_cmd(client, message):
    try:
        uid = message.command[1]
        if uid in db_cache:
            db_cache[uid]["vip_until"] = 0
            global is_dirty
            is_dirty = True
            await message.reply(f"❌ `{uid}` VIP iptal edildi.")
    except: pass

@bot.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_bal_cmd(client, message):
    try:
        _, uid, amt = message.text.split()
        get_user(uid)
        update_balance(uid, int(amt))
        await message.reply(f"✅ `{uid}` -> +{amt} Hak.")
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broadcast_cmd(client, message):
    if len(message.command) < 2: return await message.reply("❌ Mesaj yaz.")
    text = message.text.split(None, 1)[1]
    msg = await message.reply("📢 Gönderiliyor...")
    c = 0
    for uid in db_cache.keys():
        try:
            await client.send_message(int(uid), f"📢 **DUYURU**\n\n{text}")
            c += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.edit(f"✅ **{c} Kişiye ulaştı.**")

# ==================== 🚀 ARAYÜZ ====================
def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Linki Gönder ve İndir", callback_data="manual_dl")],
        [InlineKeyboardButton("👤 Profilim", callback_data="my_account"), InlineKeyboardButton("🎁 Referans", callback_data="invite_friend")],
        [InlineKeyboardButton("❓ Yardım", callback_data="how_to"), InlineKeyboardButton("💎 Paketler", callback_data="buy_vip")]
    ])

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    print(f"✅ START KOMUTU GELDİ: {message.from_user.id}") # Log için
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name
        get_user(user_id) 
        if len(message.command) > 1:
            try:
                ref_id = message.command[1]
                if add_ref(user_id, ref_id):
                    try: await client.send_message(int(ref_id), f"🔥 **Yeni Referans!**\nArkadaşın katıldı, +2 Hak kazandın!")
                    except: pass
            except: pass
        
        # 🔥 GARANTİLİ START (Resim bozuksa yazı atar)
        caption_text = (
            f"👋 **Merhaba, {first_name}!**\n\n"
            f"🤖 **Yael Saver'a Hoş Geldin.**\n"
            f"Telegram'ın en gelişmiş gizli içerik indirme asistanıyım.\n\n"
            f"🔻 **Ne yapmak istersin?**"
        )
        try:
            await message.reply_photo(photo=BOT_IMAGE, caption=caption_text, reply_markup=get_main_menu())
        except Exception as img_err:
            print(f"⚠️ Resim Hatası: {img_err} -> Yazı gönderiliyor.")
            await message.reply(text=caption_text, reply_markup=get_main_menu())

    except Exception as e:
        print(f"❌ KRTİK HATA: {e}")

@bot.on_callback_query()
async def cb_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    u = get_user(user_id)
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]])

    if data == "back_home":
        await callback.message.delete()
        try: await client.send_photo(user_id, photo=BOT_IMAGE, caption="👋 **Ana Menüdesin.**\n👇 İşlem seç:", reply_markup=get_main_menu())
        except: await client.send_message(user_id, "👋 **Ana Menüdesin.**\n👇 İşlem seç:", reply_markup=get_main_menu())
        return
    
    elif data == "my_account":
        vip_status = is_user_vip(user_id)
        if vip_status:
            expiry = u.get("vip_until", 0)
            days_left = int((expiry - time.time()) / 86400)
            date_str = datetime.datetime.fromtimestamp(expiry).strftime('%d.%m.%Y')
            status_text = "✨ **PRO PAKET**"
            info_text = f"📅 **Bitiş:** {date_str}\n⏳ **Kalan:** {days_left} Gün"
            bal_text = "♾️ Sınırsız"
        else:
            status_text = "👤 **Starter**"
            info_text = "⚡ _Sınırsız için paket yükseltin_"
            bal_text = f"{u['balance']} Dosya"
        
        text = (
            f"👤 **PROFİL BİLGİLERİ**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"🏷️ **İsim:** {callback.from_user.first_name}\n\n"
            f"🛡 **Üyelik:** {status_text}\n"
            f"{info_text}\n\n"
            f"💰 **Mevcut Hak:** `{bal_text}`"
        )
        await smart_edit(callback.message, text, back_btn)

    elif data == "invite_friend":
        link = f"https://t.me/{client.me.username}?start={user_id}"
        share_text = f"🔥 **Yael Saver ile gizli içerikleri indir!**\n\nÜcretsiz deneme hakkı veriyor. Kaliteyi bozmadan indiriyor.\n\n👇 Hemen dene:\n{link}"
        url = f"https://t.me/share/url?url={share_text}"
        
        text = (
            f"🎁 **DAVET ET KAZAN**\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Arkadaşlarını davet et, her arkadaşın için **+2 İndirme Hakkı** kazan!\n\n"
            f"🔗 **Davet Linkin:**\n`{link}`\n\n"
            f"👇 **Paylaş:**"
        )
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Gönder (WhatsApp/TG)", url=url)], [InlineKeyboardButton("🔙 Geri Dön", callback_data="back_home")]])
        await smart_edit(callback.message, text, btns)

    elif data == "manual_dl":
        text = f"📥 **İNDİRME EKRANI**\n\n1️⃣ İçerik linkini kopyala.\n2️⃣ Buraya yapıştır.\n\n🛑 **Önemli:** Eğer bot 'Erişim Yok' derse, önce o grubun **Davet Linkini** at."
        await smart_edit(callback.message, text, back_btn)

    elif data == "buy_vip":
        text = (
            f"💎 **ABONELİK PAKETLERİ**\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🥈 **STARTER (15 Gün)**\n"
            f"💸 {PRICE_15_TL} / {PRICE_15_STARS}\n"
            f"🔹 Kısa süreli kullanım.\n\n"
            f"🥇 **PRO PAKET (30 Gün) 🔥**\n"
            f"💸 {PRICE_30_TL} / {PRICE_30_STARS}\n"
            f"🚀 **En Popüler Seçim!**\n\n"
            f"💬 Satın almak için yönetici ile görüşün:"
        )
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👤 Yöneticiye Mesaj At", url=f"https://t.me/{OWNER_USERNAME}")],
            [InlineKeyboardButton("🔙 İptal", callback_data="back_home")]
        ])
        await smart_edit(callback.message, text, btns)

    elif data == "how_to":
        text = "❓ **YARDIM**\n\n1. İçeriğin linkini kopyala.\n2. Bota gönder.\n3. Bot indirip sana atsın.\n\n⚠️ Hata alırsan önce grubun **Davet Linkini** at."
        await smart_edit(callback.message, text, back_btn)

# ==================== 🔗 İŞLEM MERKEZİ ====================
@bot.on_message(filters.regex(r"https://t.me/\+") | filters.regex(r"https://t.me/joinchat/"))
async def join_handler(client, message):
    status = await message.reply("🔓 **Gizli Link!** Userbot deniyor...")
    try:
        await userbot.join_chat(message.text)
        await status.edit("✅ **GİRDİM!** Şimdi içerik linkini atabilirsin.")
        await reload_userbot_cache()
    except UserAlreadyParticipant:
        await status.edit("✅ **Zaten içerideyim.** Linki at.")
    except Exception as e:
        await status.edit(f"❌ **Giremedim:** {e}")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    if "joinchat" in message.text or "+" in message.text: return
    user_id = message.from_user.id
    u = get_user(user_id)
    vip_status = is_user_vip(user_id)

    if not vip_status and u["balance"] <= 0 and user_id != OWNER_ID:
        return await message.reply(f"⛔ **HAKKIN BİTTİ!**\n\nBakiyen sıfırlandı.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Abonelik Al", callback_data="buy_vip")]]))

    status = await message.reply("⏳ **İşleniyor...**")
    try:
        link = message.text
        if "t.me/c/" in link:
            parts = link.split("t.me/c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1].split("?")[0])
        else:
            parts = link.split("t.me/")[1].split("/")
            chat_id = parts[0]
            msg_id = int(parts[1].split("?")[0])

        target_msg = None
        try:
            target_msg = await userbot.get_messages(chat_id, msg_id)
        except (PeerIdInvalid, ChannelInvalid, ChannelPrivate):
            try:
                await reload_userbot_cache()
                target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                return await status.edit("❌ **ERİŞİM YOK!**\nÖnce **Davet Linkini** at.")
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status.edit("❌ İçerik yok.")

        path = await userbot.download_media(target_msg)
        caption_on_media = "" if vip_status or user_id == OWNER_ID else "✅ **@YaelSaverBot ile indirildi.**"

        if target_msg.video: await client.send_video(user_id, path, caption=caption_on_media, duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo: await client.send_photo(user_id, path, caption=caption_on_media)
        elif target_msg.document: await client.send_document(user_id, path, caption=caption_on_media)

        if not vip_status and user_id != OWNER_ID:
            update_balance(user_id, -1)
            await client.send_message(user_id, f"📉 **Kalan Hakkın:** `{u['balance']}`\n⚡ _Sınırsız için PRO PAKET al!_")

        if os.path.exists(path): os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")
        if 'path' in locals() and os.path.exists(path): os.remove(path)

# ==================== BAŞLATMA ====================
async def main():
    global db_cache
    print("🤖 Başlatılıyor...")
    try: await bot.start()
    except: pass
    try: await userbot.start()
    except: pass
    db_cache = await restore_data()
    await reload_userbot_cache()
    asyncio.create_task(backup_task())
    asyncio.create_task(check_expirations_task())
    print("✅ YAEL SAVER V9.5 ACTIVE")
    try: await idle()
    except: pass
    finally:
        await save_now(reason="Kapanış")
        await bot.stop()
        await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
