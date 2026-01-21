import os
import json
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) 
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")

# GÖRSEL (Yael Saver Özel Tasarım Linki)
BOT_IMAGE = "https://i.ibb.co/3Wnqmq0/robot-cyber-tech.jpg" 

# FİYAT VE ÖDÜL
START_BALANCE = 3
REF_REWARD = 2
VIP_PRICE_TL = "250 TL"
VIP_PRICE_STARS = "300 ⭐"

# SİSTEM
DB_FILE = "users_backup.json" 
BACKUP_INTERVAL = 3600 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelFix")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V7.5 Active 🟢"
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

# --- KULLANICI FONKSİYONLARI ---
def get_user(user_id):
    global is_dirty
    uid = str(user_id)
    if uid not in db_cache:
        db_cache[uid] = {"balance": START_BALANCE, "invited_by": None, "is_vip": False}
        is_dirty = True
    return db_cache[uid]

def update_balance(user_id, amount):
    global is_dirty
    uid = str(user_id)
    if uid in db_cache:
        if db_cache[uid].get("is_vip", False) and amount < 0: return 
        db_cache[uid]["balance"] += amount
        is_dirty = True

def set_vip(user_id, status=True):
    global is_dirty
    uid = str(user_id)
    if uid in db_cache:
        db_cache[uid]["is_vip"] = status
        is_dirty = True

def add_ref(user_id, referrer_id):
    global is_dirty
    uid = str(user_id)
    rid = str(referrer_id)
    if uid == rid or uid not in db_cache: return False
    if db_cache[uid].get("invited_by") is None:
        db_cache[uid]["invited_by"] = rid
        if rid in db_cache: db_cache[rid]["balance"] += REF_REWARD
        is_dirty = True
        return True
    return False

# ==================== 👑 YÖNETİCİ PANELİ (GİZLİ) ====================
# Agam bu menüye sadece sen /admin yazınca ulaşırsın. Normal menüde görünmez.

@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    total = len(db_cache)
    vips = sum(1 for u in db_cache.values() if u.get("is_vip"))
    
    text = (
        f"👑 **PATRON PANELİ**\n\n"
        f"👥 Toplam Üye: `{total}`\n"
        f"🌟 Toplam VIP: `{vips}`\n"
        f"💾 Yedek Durumu: {'⚠️ Bekliyor' if is_dirty else '✅ Güncel'}\n\n"
        f"__Yönetim Komutları:__\n"
        f"• `/addvip ID` -> Sınırsız Yap\n"
        f"• `/delvip ID` -> VIP Al\n"
        f"• `/add ID MİKTAR` -> Hak Ekle\n"
        f"• `/duyuru MESAJ` -> Herkese Mesaj"
    )
    await message.reply(text)

@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def add_vip_cmd(client, message):
    try:
        target_id = message.command[1]
        if target_id not in db_cache: get_user(target_id)
        set_vip(target_id, True)
        await message.reply(f"✅ `{target_id}` kullanıcısı VIP yapıldı.")
    except: await message.reply("❌ Hata: `/addvip ID` şeklinde yaz.")

@bot.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_bal_cmd(client, message):
    try:
        _, uid, amt = message.text.split()
        if uid not in db_cache: get_user(uid)
        update_balance(uid, int(amt))
        await message.reply(f"✅ `{uid}` kullanıcısına +{amt} hak eklendi.")
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broadcast_cmd(client, message):
    if len(message.command) < 2: return await message.reply("❌ Mesaj yazmadın.")
    text = message.text.split(None, 1)[1]
    msg = await message.reply("📢 Duyuru başlatıldı...")
    sent = 0
    for uid in db_cache.keys():
        try:
            await client.send_message(int(uid), f"📢 **DUYURU**\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.edit(f"✅ **Bitti!**\nUlaşan: {sent}")

# ==================== 🚀 KULLANICI ARAYÜZÜ (FIXED) ====================

# ORTAK MENÜ FONKSİYONU (Tekrar tekrar yazmamak için)
def get_main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Hesabım", callback_data="my_account"),
            InlineKeyboardButton("👥 Davet Et (+2 Hak)", callback_data="invite_friend") # 🔥 EKLENDİ
        ],
        [
            InlineKeyboardButton("❓ Nasıl Kullanılır?", callback_data="how_to"),
            InlineKeyboardButton("📦 Toplu Transfer", callback_data="bulk_info")
        ],
        [
            InlineKeyboardButton("💎 VIP AL (Sınırsız)", callback_data="buy_vip")
        ]
    ])

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    get_user(user_id) # Veritabanına işle

    # Referans Kontrolü
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if add_ref(user_id, ref_id):
                try: await client.send_message(int(ref_id), f"🔥 **Yeni Referans!**\nArkadaşın katıldı, +{REF_REWARD} Hak kazandın!")
                except: pass
        except: pass

    await message.reply_photo(
        photo=BOT_IMAGE,
        caption=(
            f"👋 **Hoş Geldin, {first_name}!**\n\n"
            f"🤖 **Yael Saver Pro** sistemine bağlandın.\n"
            f"Telegram'ın en gelişmiş içerik indirme asistanıyım.\n\n"
            f"👇 **Ne yapmak istersin?**"
        ),
        reply_markup=get_main_menu()
    )

@bot.on_callback_query()
async def cb_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    
    # 🔥 KRİTİK DÜZELTME: Veritabanı boşsa bile kullanıcıyı getir
    u = get_user(user_id)
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]])

    try:
        if data == "back_home":
            # Temiz bir sayfa açmak için eskisini silip yeni gönderiyoruz
            await callback.message.delete()
            await client.send_photo(
                user_id,
                photo=BOT_IMAGE,
                caption="👋 **Ana Menüye Döndün.**\n\n👇 İşlem seç:",
                reply_markup=get_main_menu()
            )

        elif data == "my_account":
            is_vip = u.get("is_vip", False)
            status_text = "👑 **SINIRSIZ VIP**" if is_vip else "👤 Standart Üye"
            balance_text = "♾️ Sınırsız" if is_vip else f"{u['balance']} Dosya"
            
            ref_link = f"https://t.me/{client.me.username}?start={user_id}"
            
            text = (
                f"👤 **HESAP BİLGİLERİ**\n\n"
                f"🆔 ID: `{user_id}`\n"
                f"🛡 Üyelik: {status_text}\n"
                f"💰 Bakiye: `{balance_text}`\n\n"
                f"🔗 **Davet Linkin:**\n`{ref_link}`"
            )
            # Burada text editi yapıyoruz, fotoğraf kalıyor
            await callback.message.edit_caption(caption=text, reply_markup=back_btn)

        elif data == "invite_friend":
            ref_link = f"https://t.me/{client.me.username}?start={user_id}"
            share_text = (
                f"🔓 **Telegram'da 'İndirme Yasak' olan gruplardan video indiren botu buldum!**\n\n"
                f"Görüntü kalitesini bozmuyor ve 3 hak ücretsiz veriyor. Dene:\n"
                f"{ref_link}"
            )
            share_url = f"https://t.me/share/url?url={share_text}"
            
            text = (
                f"🎁 **BEDAVA HAK KAZAN!**\n\n"
                f"Her davet ettiğin arkadaşın için **+{REF_REWARD} HAK** kazanırsın.\n\n"
                f"👇 Linki arkadaşlarına gönder:"
            )
            btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Arkadaşlarına Gönder", url=share_url)],
                [InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]
            ])
            await callback.message.edit_caption(caption=text, reply_markup=btns)

        elif data == "buy_vip":
            text = (
                f"💎 **VIP ÜYELİK AL**\n\n"
                f"✅ Sınırsız İndirme\n"
                f"✅ Reklamsız İçerik\n"
                f"✅ Öncelikli Destek\n\n"
                f"👇 **Ödeme Yöntemi Seç:**"
            )
            pay_btns = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⭐ {VIP_PRICE_STARS} (Telegram)", url=f"https://t.me/{OWNER_USERNAME}")],
                [InlineKeyboardButton(f"💳 {VIP_PRICE_TL} (IBAN / Kripto)", url=f"https://t.me/{OWNER_USERNAME}")],
                [InlineKeyboardButton("🔙 İptal", callback_data="back_home")]
            ])
            await callback.message.edit_caption(caption=text, reply_markup=pay_btns)

        elif data == "how_to":
            text = (
                f"❓ **NASIL KULLANILIR?**\n\n"
                f"1️⃣ İndirmek istediğin içeriğin **Linkini Kopyala**.\n"
                f"2️⃣ Bota gönder.\n"
                f"3️⃣ Bot indirip sana atsın.\n\n"
                f"⚠️ **Hata Alırsan:** Grubun/Kanalın **Davet Linkini (Invite Link)** bota gönder."
            )
            await callback.message.edit_caption(caption=text, reply_markup=back_btn)

        elif data == "bulk_info":
            text = (
                f"📦 **TOPLU İŞLEMLER**\n\n"
                f"Binlerce videoyu kopyalamak, yedeklemek veya klonlamak mı istiyorsun?\n"
                f"Özel bot yazdırmak için iletişime geçin.\n\n"
                f"👨‍💻 **Admin:** @{OWNER_USERNAME}"
            )
            await callback.message.edit_caption(caption=text, reply_markup=back_btn)

    except Exception as e:
        print(f"Callback Hatası: {e}")
        # Hata olursa kullanıcıyı menüye at
        await start_command(client, callback.message)

# ==================== 🔗 İŞLEM MERKEZİ ====================
@bot.on_message(filters.regex(r"https://t.me/\+") | filters.regex(r"https://t.me/joinchat/"))
async def join_handler(client, message):
    status = await message.reply("🔓 **Gizli Link!** Userbot girmeyi deniyor...")
    try:
        await userbot.join_chat(message.text)
        await status.edit("✅ **GİRDİM!** Şimdi içerik linkini atabilirsin.")
    except UserAlreadyParticipant:
        await status.edit("✅ **Zaten içerideyim.** İçerik linkini gönder.")
    except Exception as e:
        await status.edit(f"❌ **Giremedim:** {e}")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def process_link(client, message):
    if "joinchat" in message.text or "+" in message.text: return
    user_id = message.from_user.id
    u = get_user(user_id)
    is_vip = u.get("is_vip", False)

    if not is_vip and u["balance"] <= 0 and user_id != OWNER_ID:
        return await message.reply(
            f"⛔ **Hakkın Bitti!**\n\nYa arkadaşını davet et (+2 Hak) ya da sınırsız VIP al.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 VIP AL", callback_data="buy_vip")]])
        )

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
            return await status.edit("❌ **ERİŞİM YOK!**\nÖnce grubun **Davet Linkini** at.")
        except Exception:
            if isinstance(chat_id, str):
                try:
                    await userbot.join_chat(chat_id)
                    target_msg = await userbot.get_messages(chat_id, msg_id)
                except: pass
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status.edit("❌ İçerik yok.")

        path = await userbot.download_media(target_msg)
        
        caption = "" if is_vip or user_id == OWNER_ID else "✅ **@YaelSaverBot ile indirildi.**\n💎 _Sınırsız indirme için VIP al!_"

        if target_msg.video:
            await client.send_video(user_id, path, caption=caption, duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, path, caption=caption)

        if not is_vip and user_id != OWNER_ID: update_balance(user_id, -1)
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
    asyncio.create_task(backup_task())
    
    print("✅ YAEL SAVER V7.5 AKTİF")
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
