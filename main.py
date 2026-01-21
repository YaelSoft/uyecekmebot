import os
import json
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant, InputUserDeactivated, UserIsBlocked

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) 
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")

# 💰 FİYATLANDIRMA VE ÖDÜLLER
START_BALANCE = 3      # Başlangıç hakkı
REF_REWARD = 2         # Referans ödülü
VIP_PRICE_TL = "250 TL"
VIP_PRICE_STARS = "300 ⭐"

# SİSTEM
DB_FILE = "users_backup.json" 
BACKUP_INTERVAL = 3600 # 1 Saat (Spam yapmaz, güvenli)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelBusiness")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Business System Active 🟢"
def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI & YEDEKLEME ====================
db_cache = {}
is_dirty = False 

async def restore_data():
    """Bot açılınca kanaldan verileri çeker"""
    if LOG_CHANNEL == 0: return {}
    print("📥 Veritabanı yükleniyor...")
    try:
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=5):
            if msg.document and msg.document.file_name == "yael_db.json":
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f: return json.load(f)
    except: pass
    return {}

async def save_now(reason="Otomatik"):
    """Verileri kanala yedekler"""
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
        # Varsayılan Kullanıcı Şablonu
        db_cache[uid] = {
            "balance": START_BALANCE, 
            "invited_by": None,
            "is_vip": False  # VIP durumu
        }
        is_dirty = True
    return db_cache[uid]

def update_balance(user_id, amount):
    global is_dirty
    uid = str(user_id)
    if uid in db_cache:
        # VIP ise bakiye düşmez
        if db_cache[uid].get("is_vip", False) and amount < 0:
            return 
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
        if rid in db_cache: 
            db_cache[rid]["balance"] += REF_REWARD
        is_dirty = True
        return True
    return False

# ==================== 👑 YÖNETİCİ PANELİ (GELİŞMİŞ) ====================

@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    total = len(db_cache)
    vips = sum(1 for u in db_cache.values() if u.get("is_vip"))
    
    text = (
        f"👑 **PATRON PANELİ**\n\n"
        f"👥 Toplam Üye: `{total}`\n"
        f"🌟 Toplam VIP: `{vips}`\n"
        f"💾 Yedek Durumu: {'⚠️ Bekliyor' if is_dirty else '✅ Güncel'}\n\n"
        f"__Komutlar:__\n"
        f"• `/addvip ID` -> VIP Yap\n"
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
        await message.reply(f"✅ `{target_id}` artık **SINIRSIZ VIP!**")
        try: await client.send_message(int(target_id), "🎉 **MÜJDE!**\nHesabın **VIP** üyeliğe yükseltildi.\nArtık sınırsız ve reklamsız indirebilirsin!")
        except: pass
    except: await message.reply("❌ Hata: `/addvip 12345678`")

@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def del_vip_cmd(client, message):
    try:
        target_id = message.command[1]
        set_vip(target_id, False)
        await message.reply(f"❌ `{target_id}` kullanıcısının VIP yetkisi alındı.")
    except: pass

@bot.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_balance_cmd(client, message):
    try:
        _, uid, amt = message.text.split()
        if uid not in db_cache: get_user(uid)
        update_balance(uid, int(amt))
        await message.reply(f"✅ `{uid}` -> +{amt} Hak.")
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broadcast_cmd(client, message):
    if len(message.command) < 2: return await message.reply("❌ Mesaj yazmadın.")
    text = message.text.split(None, 1)[1]
    msg = await message.reply("📢 Duyuru başlatıldı...")
    sent, failed = 0, 0
    for uid in db_cache.keys():
        try:
            await client.send_message(int(uid), f"📢 **DUYURU**\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except: failed += 1
    await msg.edit(f"✅ **Bitti!**\nUlaşan: {sent}\nUlaşmayan: {failed}")

# ==================== 🚀 KULLANICI ARAYÜZÜ ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    get_user(user_id) 

    # Referans (Hype Mesajlı)
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if add_ref(user_id, ref_id):
                try: await client.send_message(int(ref_id), f"🔥 **Yeni Referans!**\nArkadaşın katıldı, +{REF_REWARD} Hak kazandın!")
                except: pass
        except: pass

    # Menü Hazırlığı
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Hesabım", callback_data="my_account"), InlineKeyboardButton("❓ Yardım", callback_data="help")],
        [InlineKeyboardButton("📦 Toplu Transfer", callback_data="bulk"), InlineKeyboardButton("💎 VIP AL (Sınırsız)", callback_data="buy_vip")]
    ])

    await message.reply_photo(
        photo="https://cdn-icons-png.flaticon.com/512/2583/2583166.png",
        caption=f"👋 **Selam {first_name}!**\n\n💎 **Yael Saver'a Hoş Geldin.**\nGizli gruplardan, kilitli kanallardan içerik indiren tek bot!\n\n👇 **Menüden işlem seç:**",
        reply_markup=keyboard
    )

@bot.on_callback_query()
async def cb_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    u = db_cache.get(str(user_id))
    
    # Geri Tuşu
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]])

    if data == "back_home":
        await start_command(client, callback.message)
        await callback.message.delete()

    elif data == "my_account":
        is_vip = u.get("is_vip", False)
        status_text = "👑 **SINIRSIZ VIP**" if is_vip else "👤 Standart Üye"
        balance_text = "♾️ Sınırsız" if is_vip else f"{u['balance']} Dosya"
        
        # ✅ YENİ DÜRÜST VE ETKİLİ PAYLAŞIM MESAJI
        ref_link = f"https://t.me/{client.me.username}?start={user_id}"
        share_text = (
            f"🔓 **Telegram'da 'İndirme Yasak' olan gruplardan video/resim indiren botu buldum!**\n\n"
            f"Görüntü kalitesini bozmuyor ve 3 hak ücretsiz veriyor. Bir dene istersen:\n"
            f"{ref_link}"
        )
        share_url = f"https://t.me/share/url?url={share_text}"

        text = (
            f"👤 **HESAP DURUMU**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"🛡 Üyelik: {status_text}\n"
            f"💰 Hak: `{balance_text}`\n\n"
            f"🔗 **Davet Linkin:**\n`{ref_link}`\n\n"
            f"🎁 **Arkadaşını davet et, +{REF_REWARD} Hak kazan!**"
        )
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Arkadaşlarına Öner", url=share_url)],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_home")]
        ])
        await callback.message.edit(text, reply_markup=btns)

    elif data == "buy_vip":
        text = (
            f"💎 **VIP ÜYELİK AVANTAJLARI**\n\n"
            f"✅ **Sınırsız İndirme** (Hak derdi yok)\n"
            f"✅ **Reklamsız** (Videonun altında yazı olmaz)\n"
            f"✅ **Öncelikli İşlem**\n\n"
            f"👇 **Ödeme Yöntemi Seç:**"
        )
        pay_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ {VIP_PRICE_STARS} (Telegram)", url=f"https://t.me/{OWNER_USERNAME}")],
            [InlineKeyboardButton(f"💳 {VIP_PRICE_TL} (IBAN / Kripto)", url=f"https://t.me/{OWNER_USERNAME}")],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_home")]
        ])
        await callback.message.edit(text, reply_markup=pay_btns)

    elif data == "bulk":
        text = (
            f"📦 **TOPLU TRANSFER / KLONLAMA**\n\n"
            f"Bir kanaldaki 10.000 videoyu kendi kanalına mı çekmek istiyorsun?\n"
            f"Veya özel bir bot mu yazdırmak istiyorsun?\n\n"
            f"👨‍💻 **Admin ile iletişime geç:** @{OWNER_USERNAME}"
        )
        await callback.message.edit(text, reply_markup=back_btn)
    
    elif data == "help":
        await callback.message.edit("❓ **YARDIM**\n\nLinki at, indireyim. Eğer bot hata verirse önce grubun **Davet Linkini** at.", reply_markup=back_btn)

# ==================== 🔗 İNDİRME MOTORU ====================
@bot.on_message(filters.regex(r"https://t.me/\+") | filters.regex(r"https://t.me/joinchat/"))
async def join_handler(client, message):
    user_id = message.from_user.id
    # VIP Kontrolü yok, herkes link atıp botu sokabilir
    status = await message.reply("🔓 **Gizli Link!** Userbot girmeyi deniyor...")
    try:
        await userbot.join_chat(message.text)
        await status.edit("✅ **BAŞARILI!** Girdim. Şimdi içerik linkini at.")
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

    # Bakiye Kontrol (VIP ise bakmaz, Owner ise bakmaz)
    if not is_vip and u["balance"] <= 0 and user_id != OWNER_ID:
        return await message.reply(
            f"⛔ **Hakkın Bitti!**\n\nYa arkadaşını davet et ya da sınırsız VIP al.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 VIP AL", callback_data="buy_vip")]])
        )

    status = await message.reply("⏳ **İşleniyor...**")
    
    try:
        # Link İşleme
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
            return await status.edit("❌ **ERİŞİM YOK!**\nLütfen önce grubun **Davet Linkini** at.")
        except Exception:
            if isinstance(chat_id, str):
                try:
                    await userbot.join_chat(chat_id)
                    target_msg = await userbot.get_messages(chat_id, msg_id)
                except: pass
        
        if not target_msg or not (target_msg.video or target_msg.photo or target_msg.document):
            return await status.edit("❌ İçerik yok.")

        path = await userbot.download_media(target_msg)
        
        # Reklam/İmza Ayarı
        if is_vip or user_id == OWNER_ID:
            caption = "" # VIP'ye temiz video
        else:
            caption = "✅ **@YaelSaverBot ile indirildi.**\n💎 _Sınırsız indirme için VIP al!_"

        if target_msg.video:
            await client.send_video(user_id, path, caption=caption, duration=target_msg.video.duration, width=target_msg.video.width, height=target_msg.video.height)
        elif target_msg.photo:
            await client.send_photo(user_id, path, caption=caption)
        elif target_msg.document:
            await client.send_document(user_id, path, caption=caption)

        # Bakiye Düşme (VIP ise düşmez)
        if not is_vip and user_id != OWNER_ID:
            update_balance(user_id, -1)

        # Hemen Sil (Kota Dostu)
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
    
    print("✅ YAEL BUSINESS SİSTEMİ AKTİF")
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

