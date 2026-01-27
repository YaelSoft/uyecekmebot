import os
import json
import time
import asyncio
import logging
import datetime
import requests
import re
import gc
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant, FloodWait
from pyrogram.raw.types import UpdateBotPrecheckoutQuery
from pyrogram.raw.functions.messages import SetBotPrecheckoutResults

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# 🔥 LOG KANAL ID
MANUAL_LOG_ID = -1003695289737 
ENV_LOG = os.environ.get("LOG_CHANNEL", "0")
LOG_CHANNEL = int(ENV_LOG) if ENV_LOG != "0" else MANUAL_LOG_ID

OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")
FIXED_BOT_USERNAME = "YaelSaverBot"

# 🔗 VIP GRUP LİNKİ
LINK_VIP_GROUP = "https://t.me/+ww1jYq7Ww7xlOTIx" 

# 📢 İSTEK / ÖNERİ KANALI
LINK_SUGGESTION = "https://t.me/+5qvMHy1yDb85Nzk5"

# ==================== 💰 FİYATLAR & LİMİTLER (3 KADEMELİ) ====================

DEFAULT_CREDIT_PACKS = {
    "c10":  {"name": "🥉 10 KREDİ",  "amount": 10,  "price_amt": 40, "price_lbl": "40 ⭐"},
    "c25":  {"name": "🥈 25 KREDİ",  "amount": 25,  "price_amt": 90, "price_lbl": "90 ⭐"},
    "c50":  {"name": "🥇 50 KREDİ",  "amount": 50,  "price_amt": 160, "price_lbl": "160 ⭐"},
    "c100": {"name": "💎 100 KREDİ", "amount": 100, "price_amt": 280, "price_lbl": "280 ⭐"}
}
CREDIT_PACKS = DEFAULT_CREDIT_PACKS.copy()

SUB_PACKS = {
    "vip_month": {
        "name": "👑 VIP AYLIK",   
        "days": 30, 
        "daily_limit": 10, 
        "desc": "Günde 10 Hak + 1.5 GB Limit",  
        "price_lbl": "300 ⭐",  
        "link": LINK_VIP_GROUP
    }
}

# 🔥 LİMİT AYARLARI (Render Dostu)
LIMIT_FREE = 100 * 1024 * 1024   # 100 MB (Beleşçi)
LIMIT_PAID = 500 * 1024 * 1024   # 500 MB (Kredi Alan)
LIMIT_VIP  = 1500 * 1024 * 1024  # 1.5 GB (VIP Abone)

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV102")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V102.0 PRO COMMERCE Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI & YEDEKLEME ====================
db_cache = {"users": {}, "config": {"prices": DEFAULT_CREDIT_PACKS.copy()}}

async def restore_data():
    global db_cache, CREDIT_PACKS
    print(f"📥 YEDEK ARANIYOR (Kanal: {LOG_CHANNEL})...")
    if LOG_CHANNEL == 0 or LOG_CHANNEL == -100123456789: return

    try:
        found = False
        async for msg in userbot.get_chat_history(LOG_CHANNEL, limit=50):
            if msg.document and msg.document.file_name == DB_FILE:
                path = await userbot.download_media(msg)
                with open(path, "r") as f:
                    data = json.load(f)
                    if "users" in data: db_cache = data
                    if "config" in data and "prices" in data["config"]:
                        CREDIT_PACKS = data["config"]["prices"]
                print(f"✅ YEDEK YÜKLENDİ: {len(db_cache['users'])} kullanıcı.")
                found = True
                break
        if not found:
            async for msg in bot.get_chat_history(LOG_CHANNEL, limit=50):
                if msg.document and msg.document.file_name == DB_FILE:
                    path = await bot.download_media(msg)
                    with open(path, "r") as f:
                        data = json.load(f)
                        if "users" in data: db_cache = data
                    print(f"✅ YEDEK YÜKLENDİ (Bot): {len(db_cache['users'])} kullanıcı.")
                    found = True
                    break
    except Exception as e: 
        print(f"❌ YEDEK YÜKLEME HATASI: {e}")

async def save_backup(reason="Otomatik", silent=False):
    global db_cache, CREDIT_PACKS
    try:
        db_cache["config"] = {"prices": CREDIT_PACKS}
        with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
    except: pass

    if silent: return
    if LOG_CHANNEL == 0 or LOG_CHANNEL == -100123456789: return

    total_users = len(db_cache.get("users", {}))
    caption = f"💾 YEDEK ({reason})\n👥 {total_users}\n📅 {datetime.datetime.now()}"

    try:
        await bot.send_document(LOG_CHANNEL, document=DB_FILE, caption=caption)
        return
    except:
        try: await userbot.send_document(LOG_CHANNEL, document=DB_FILE, caption=f"{caption}\n(Userbot)")
        except: pass

async def backup_loop():
    await asyncio.sleep(10)
    await save_backup(reason="Bot Başlatıldı", silent=False)
    while True:
        await asyncio.sleep(7200) 
        await save_backup(reason="2 Saatlik Oto-Yedek", silent=False)

async def force_cache_refresh():
    try:
        async for dialog in userbot.get_dialogs(): pass
    except: pass

@bot.on_message(filters.document & filters.user(OWNER_ID) & filters.private)
async def manual_restore(c, m):
    if m.document.file_name == DB_FILE:
        msg = await m.reply("📥 **YEDEK DOSYASI ALINIYOR...**")
        try:
            path = await m.download()
            global db_cache, CREDIT_PACKS
            with open(path, "r") as f:
                new_data = json.load(f)
                if "users" in new_data: db_cache = new_data 
                if "config" in new_data and "prices" in new_data["config"]:
                    CREDIT_PACKS = new_data["config"]["prices"]
            with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
            os.remove(path)
            await msg.edit(f"✅ **YEDEK YÜKLENDİ!**\n👥 {len(db_cache['users'])}")
            await save_backup("Manuel Restore", silent=False)
        except Exception as e: await msg.edit(f"❌ HATA: {e}")

# ==================== 🧠 KULLANICI YÖNETİMİ ====================
def get_user(user_id, first_name=None):
    uid = str(user_id)
    today = datetime.date.today().isoformat()
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "balance": 3, "total_spent": 0, "sub_type": "none", "sub_expiry": 0,
            "daily_usage": 0, "last_reset": today, "invited_by": None,
            "first_name": first_name or "Kullanıcı"
        }
    user = db_cache["users"][uid]
    if first_name: user["first_name"] = first_name
    
    if user.get("last_reset") != today:
        user["daily_usage"] = 0
        user["last_reset"] = today
        if user["sub_type"] != "none" and time.time() > user["sub_expiry"]:
            user["sub_type"] = "none"
            user["sub_expiry"] = 0
            try: bot.send_message(int(uid), "⚠️ **Aboneliğiniz Sona Erdi!**")
            except: pass
    if user["balance"] < 0: user["balance"] = 0
    return user

def check_access(user_id):
    if user_id == OWNER_ID: return True, "Patron"
    u = get_user(user_id)
    if u["sub_type"] != "none":
        pkg = SUB_PACKS.get(u["sub_type"])
        if pkg and u["daily_usage"] < pkg["daily_limit"]: return True, "Abonelik"
    if u["balance"] > 0: return True, "Kredi"
    return False, "Yetersiz"

# 🔥 KADEMELİ LİMİT SİSTEMİ 🔥
def get_size_limit(user_id):
    if user_id == OWNER_ID: return 100 * 1024 * 1024 * 1024
    u = get_user(user_id)
    
    # 1. VIP ABONE -> 1.5 GB
    if u["sub_type"] != "none":
        return LIMIT_VIP
    
    # 2. KREDİ ALAN / ESKİ MÜŞTERİ -> 500 MB
    # (Bakiyesi var veya daha önce harcama yapmış)
    if u["balance"] > 0 or u["total_spent"] > 0:
        return LIMIT_PAID
        
    # 3. BELEŞÇİ -> 100 MB
    return LIMIT_FREE

def reserve_credit(user_id):
    if user_id == OWNER_ID: return "Admin"
    uid = str(user_id)
    u = db_cache["users"][uid]
    if u["sub_type"] != "none":
        pkg = SUB_PACKS.get(u["sub_type"])
        if pkg and u["daily_usage"] < pkg["daily_limit"]:
            u["daily_usage"] += 1; return "Abonelik"
    if u["balance"] > 0:
        u["balance"] -= 1; u["total_spent"] += 1; return "Kredi"
    return False

def refund_credit(user_id, source):
    if user_id == OWNER_ID: return
    uid = str(user_id)
    u = db_cache["users"][uid]
    if source == "Abonelik":
        if u["daily_usage"] > 0: u["daily_usage"] -= 1
    elif source == "Kredi":
        u["balance"] += 1
        if u["total_spent"] > 0: u["total_spent"] -= 1

def add_credits(user_id, amount):
    uid = str(user_id)
    get_user(uid)
    db_cache["users"][uid]["balance"] += amount
    return db_cache["users"][uid]["balance"]

def activate_subscription(user_id, sub_key):
    uid = str(user_id)
    get_user(uid)
    pkg = SUB_PACKS[sub_key]
    db_cache["users"][uid]["sub_type"] = sub_key
    db_cache["users"][uid]["sub_expiry"] = time.time() + (pkg["days"] * 86400)
    db_cache["users"][uid]["daily_usage"] = 0
    return pkg["name"]

def send_invoice_via_http(chat_id, package_key):
    try:
        pkg = CREDIT_PACKS[package_key]
        price_amt = pkg["price_amt"]
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        payload = {
            "chat_id": chat_id,
            "title": pkg["name"],
            "description": f"{pkg['amount']} Kredi + 500MB Limit", 
            "payload": f"cred_{package_key}",
            "provider_token": "", 
            "currency": "XTR",
            "prices": json.dumps([{"label": pkg["name"], "amount": price_amt}])
        }
        requests.post(url, data=payload)
    except: pass

# ==================== 🏭 İŞÇİ ====================
download_queue = asyncio.PriorityQueue()

async def worker():
    print("👷 İşçi Hazır...")
    while True:
        priority, task = await download_queue.get()
        client, status_msg, link, user_id = task
        used_source = None
        
        try:
            allowed, reason = check_access(user_id)
            if not allowed:
                btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 KREDİ/VİP AL", callback_data="shop_home")], [InlineKeyboardButton("👥 REFERANS KAS", callback_data="ref")]])
                await status_msg.edit("❌ **HAKKINIZ BİTTİ!**\n\nKredi/Vip alarak veya referans kasarak hak kazanabilirsiniz.\n\n✨ _İyi kullanımlar dileriz.._", reply_markup=btn)
                continue
            
            # 🔥 PEŞİN DÜŞME (Baban gelse acıma)
            used_source = reserve_credit(user_id)
            if not used_source:
                await status_msg.edit("⛔ Bakiye hatası.")
                continue
            
            asyncio.create_task(save_backup(reason="Harcama", silent=True))

            chat_id, msg_id = None, None
            clean_link = link.replace("https://", "").replace("http://", "").replace("t.me/", "").replace("telegram.me/", "").split("?")[0]
            parts = clean_link.split("/")
            try:
                if parts[0] == "c": chat_id = int("-100" + parts[1]); msg_id = int(parts[2])
                else: chat_id = parts[0]; msg_id = int(parts[1])
            except:
                refund_credit(user_id, used_source)
                await status_msg.edit("❌ Link formatı hatalı.")
                continue

            try:
                if isinstance(chat_id, int): await userbot.get_chat(chat_id)
            except:
                refund_credit(user_id, used_source)
                btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]])
                await status_msg.edit(f"🚫 **ERİŞİM YOK!**\n\nKanalın **Davet Linkini** bota atın.", reply_markup=btn)
                continue

            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except: 
                refund_credit(user_id, used_source) 
                await status_msg.edit("❌ Mesaj alınamadı.")
                continue
            
            if not target_msg or target_msg.empty:
                refund_credit(user_id, used_source) 
                await status_msg.edit("❌ **MESAJ BOŞ!**")
                continue

            media = (target_msg.video or target_msg.photo or target_msg.document or target_msg.audio or target_msg.voice or target_msg.video_note or target_msg.animation)

            if media:
                file_size = 0
                media_type = "doc"
                vid_width, vid_height, vid_duration, vid_thumb = 0, 0, 0, None
                
                if target_msg.video: file_size = target_msg.video.file_size; media_type = "video"; vid_width = target_msg.video.width; vid_height = target_msg.video.height; vid_duration = target_msg.video.duration
                elif target_msg.document: file_size = target_msg.document.file_size; media_type = "doc"
                elif target_msg.photo: file_size = 1024; media_type = "photo"
                elif target_msg.audio: file_size = target_msg.audio.file_size; media_type = "audio"
                elif target_msg.voice: file_size = target_msg.voice.file_size; media_type = "voice"
                elif target_msg.video_note: file_size = target_msg.video_note.file_size; media_type = "video_note"
                elif target_msg.animation: file_size = target_msg.animation.file_size; media_type = "animation"
                
                user_limit = get_size_limit(user_id)
                if file_size > user_limit:
                    refund_credit(user_id, used_source)
                    limit_mb = int(user_limit / 1024 / 1024)
                    
                    msg_txt = ""
                    if user_limit == LIMIT_FREE: msg_txt = "💎 **LİMİT AŞILDI!**\nKredi alırsanız limitiniz **500 MB** olur."
                    elif user_limit == LIMIT_PAID: msg_txt = "👑 **LİMİT AŞILDI!**\nVIP alırsanız limitiniz **1.5 GB** olur."
                    
                    await status_msg.edit(f"⚠️ **Dosya: {int(file_size/1024/1024)} MB**\nSizin Limit: {limit_mb} MB\n\n{msg_txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 YÜKSELT", callback_data="shop_home")]]))
                    continue

                await status_msg.edit("⬇️ **İndiriliyor...**")
                path = await userbot.download_media(target_msg)
                
                thumb_path = None
                if target_msg.video and target_msg.video.thumbs:
                    try: thumb_path = await userbot.download_media(target_msg.video.thumbs[0].file_id)
                    except: pass

                await status_msg.edit("⬆️ **Yükleniyor...**")
                caption = f"📥 **İndirildi:** @{FIXED_BOT_USERNAME}\n🔓 **Premium İndirici**"
                
                try:
                    if media_type == "video": await client.send_video(user_id, path, caption=caption, width=vid_width, height=vid_height, duration=vid_duration, thumb=thumb_path, supports_streaming=True)
                    elif media_type == "photo": await client.send_photo(user_id, path, caption=caption)
                    elif media_type == "doc": await client.send_document(user_id, path, caption=caption, thumb=thumb_path)
                    elif media_type == "audio": await client.send_audio(user_id, path, caption=caption)
                    elif media_type == "voice": await client.send_voice(user_id, path, caption=caption)
                    elif media_type == "video_note": await client.send_video_note(user_id, path)
                    elif media_type == "animation": await client.send_animation(user_id, path, caption=caption)
                    
                    u = get_user(user_id)
                    rem = 0
                    info_msg = ""
                    if used_source == "Abonelik":
                        rem = SUB_PACKS[u['sub_type']]['daily_limit'] - u['daily_usage']
                        info_msg = f"📅 Kalan Hak: **{rem}**"
                    else:
                        rem = u['balance']
                        info_msg = f"📉 Kalan Hak: **{rem}**"
                    
                    if rem <= 0 and u["sub_type"] == "none":
                         info_msg = "❌ **HAKKINIZ BİTTİ!**\nYeni hak için mağazayı ziyaret edin."
                    
                    await status_msg.edit(f"✅ **İşlem Tamam!**\n{info_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                    
                except Exception as send_e:
                    await status_msg.edit(f"⚠️ Hata: {send_e}")

                try:
                    if os.path.exists(path): os.remove(path)
                    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                    gc.collect()
                except: pass
                
            else:
                refund_credit(user_id, used_source) 
                await status_msg.edit("❌ Desteklenmeyen medya. Kredi iade edildi.")
                
        except Exception as e:
            if used_source: refund_credit(user_id, used_source)
            try: await status_msg.edit(f"❌ Hata: {e}\nKredi iade edildi.")
            except: pass
            try: 
                if 'path' in locals() and os.path.exists(path): os.remove(path)
                gc.collect() 
            except: pass
        await asyncio.sleep(2)

# ==================== ⚡ MENÜLER ====================
def main_menu(user_id):
    u = get_user(user_id)
    name = u.get("first_name", "Kullanıcı")
    sub_txt = "Yok"
    if u["sub_type"] != "none":
        days = int((u["sub_expiry"] - time.time()) / 86400)
        sub_txt = f"{SUB_PACKS[u['sub_type']]['name']} ({days} Gün)"
    
    # 🔥 LİMİT GÖSTERGESİ
    limit_val = get_size_limit(user_id)
    limit_str = "100 MB 🔴"
    if limit_val == LIMIT_PAID: limit_str = "500 MB 🟡"
    elif limit_val == LIMIT_VIP: limit_str = "1.5 GB 🟢"

    txt = (
        f"👋 **Merhaba {name},**\n\n"
        f"📊 **HESAP DURUMU**\n"
        f"💰 Kredi Bakiyesi: `{u['balance']}`\n"
        f"📅 VIP Abonelik: `{sub_txt}`\n"
        f"📂 İndirme Limiti: `{limit_str}`\n\n"
        f"🌟 **AVANTAJLAR**\n"
        f"• **Kredi Al:** 500 MB Limit açılır.\n"
        f"• **VIP Al:** 1.5 GB Limit açılır.\n\n"
        f"🛠 **HİZMETLER (Admin ile Görüşün)**\n"
        f"• Kişiye Özel Bot Yapımı\n"
        f"• Toplu Kanal Kopyalama / Taşıma\n"
        f"• Uygun Fiyata Transfer Hizmeti\n"
        f"👉 İletişim: @{OWNER_USERNAME}\n\n"
    )
    
    return txt, InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 İÇERİK İNDİR", callback_data="dl"), InlineKeyboardButton("💎 MARKET", callback_data="shop_home")],
        [InlineKeyboardButton("👤 PROFİLİM", callback_data="acc"), InlineKeyboardButton("👥 REFERANS", callback_data="ref")],
        [InlineKeyboardButton("📢 İSTEK / ÖNERİ KANALI", url=LINK_SUGGESTION)],
        [InlineKeyboardButton("🆘 DESTEK HATTI", callback_data="service"), InlineKeyboardButton("❓ YARDIM", callback_data="howto")]
    ])

def shop_home_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 KREDİ YÜKLE (500 MB AÇ)", callback_data="shop_credits")],
        [InlineKeyboardButton("📅 VIP ABONELİK (1.5 GB AÇ)", callback_data="shop_subs")],
        [InlineKeyboardButton("🚀 YAEL PRO (ÖZEL KURULUM)", callback_data="shop_pro")], 
        [InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="back_home")]
    ])

async def menu_switcher(client, message, text, reply_markup=None):
    try: await message.delete()
    except: pass
    try: await client.send_message(message.chat.id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    except: pass

@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    u = get_user(user_id, message.from_user.first_name)
    
    # 🔥 GELİŞMİŞ REFERANS SİSTEMİ
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if str(ref_id) != str(user_id) and u["invited_by"] is None:
                # Sadece YENİ kullanıcı ise bonus ver
                # Eğer daha önce kaydı varsa (balance değişmişse) vermiyoruz
                is_new_user = (u["balance"] == 3 and u["total_spent"] == 0)
                
                if is_new_user:
                    db_cache["users"][str(user_id)]["invited_by"] = str(ref_id)
                    db_cache["users"][str(user_id)]["balance"] += 2 # Davet edilene +2 (Toplam 5)
                    
                    if str(ref_id) in db_cache["users"]:
                        db_cache["users"][str(ref_id)]["balance"] += 2
                        asyncio.create_task(save_backup("Referans", silent=True))
                        # Davet edene bildirim
                        try: await client.send_message(int(ref_id), f"👥 **TEBRİKLER!**\nBir arkadaşınız referansınızla katıldı.\n💰 **+2 Kredi** kazandınız!")
                        except: pass
                        # Gelene bildirim
                        try: await message.reply(f"🎁 **HOŞ GELDİNİZ!**\nReferans linkiyle geldiğiniz için **+2 Ekstra Kredi** hediye edildi!\nToplam: 5 Kredi")
                        except: pass
        except: pass
    txt, markup = main_menu(user_id)
    await message.reply(txt, reply_markup=markup)

# 👑 ADMIN PANELİ
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_cmd(client, message):
    try:
        users = db_cache.get("users", {})
        info = f"👑 **PANEL**\n👥 Üye: {len(users)}\n💰 Aktif: {sum(1 for u in users.values() if u.get('balance', 0)>0)}"
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Fiyatlar", callback_data="admin_prices"), InlineKeyboardButton("🏷️ İndirim", callback_data="admin_discount_info")],
            [InlineKeyboardButton("➕ Kredi Ekle", callback_data="admin_addc"), InlineKeyboardButton("➕ Abone Ekle", callback_data="admin_adds")],
            [InlineKeyboardButton("💾 YEDEK AL", callback_data="admin_backup"), InlineKeyboardButton("📂 YEDEK YÜKLE", callback_data="admin_restore_info")],
            [InlineKeyboardButton("📢 Duyuru Yap", callback_data="admin_cast"), InlineKeyboardButton("🔙 Çıkış", callback_data="back_home")]
        ])
        await menu_switcher(client, message, info, btns)
    except: pass

@bot.on_message(filters.command("setprice") & filters.user(OWNER_ID))
async def set_price(c, m):
    try:
        code, price = m.command[1], int(m.command[2])
        if code in CREDIT_PACKS:
            CREDIT_PACKS[code]["price_amt"] = price
            CREDIT_PACKS[code]["price_lbl"] = f"{price} ⭐"
            await m.reply("✅")
            await save_backup("Fiyat", silent=True)
    except: pass

@bot.on_message(filters.command("discount") & filters.user(OWNER_ID))
async def discount_cmd(c, m):
    try:
        percent = int(m.command[1])
        if percent == 0:
            global CREDIT_PACKS
            CREDIT_PACKS = DEFAULT_CREDIT_PACKS.copy()
            await m.reply("✅ İndirim Bitti.")
        else:
            for k, v in CREDIT_PACKS.items():
                original = DEFAULT_CREDIT_PACKS[k]["price_amt"]
                new = int(original - (original * percent / 100))
                CREDIT_PACKS[k]["price_amt"] = new
                CREDIT_PACKS[k]["price_lbl"] = f"{new} ⭐ (⬇️%{percent})"
            await m.reply(f"✅ %{percent} İndirim!")
        await save_backup("İndirim", silent=True)
    except: pass

@bot.on_message(filters.command("addcredit") & filters.user(OWNER_ID))
async def manual_c(c, m):
    try: add_credits(m.command[1], int(m.command[2])); await m.reply("✅")
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broad(c, m):
    txt = m.text.split(None, 1)[1]
    for uid in db_cache["users"]:
        try: await c.send_message(int(uid), f"📢 **DUYURU**\n\n{txt}"); await asyncio.sleep(0.05)
        except: pass
    await m.reply("✅ Bitti.")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_link(client, message):
    if "join" in message.text: return
    user_id = message.from_user.id
    allowed, reason = check_access(user_id)
    if not allowed:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Kredi / VIP Al", callback_data="shop_home")], [InlineKeyboardButton("👥 Referans (+Kredi)", callback_data="ref")]])
        return await message.reply("⛔ **HAKKINIZ BİTTİ!**\n\nKredi/Vip alarak veya referans kasarak hak kazanabilirsiniz.", reply_markup=btn)
    st = await message.reply(f"⏳ **Sıraya Alındı...**")
    u = get_user(user_id, message.from_user.first_name)
    prio = 1 if u["sub_type"] != "none" else 2
    await download_queue.put((prio, (client, st, message.text, user_id)))

@bot.on_callback_query()
async def cb_handler(client, callback):
    try: await callback.answer()
    except: pass
    data = callback.data
    uid = callback.from_user.id
    u = get_user(uid)
    
    if data == "back_home":
        txt, markup = main_menu(uid)
        await menu_switcher(client, callback.message, txt, markup)
    elif data == "shop_home": await menu_switcher(client, callback.message, "🛒 **MAĞAZA**\nLütfen bir kategori seçiniz:", shop_home_menu())
    elif data == "shop_pro":
        txt = (
            "🚀 **YAEL PRO SÜRÜM (ÖZEL KURULUM)**\n\n"
            "Bu botun limitlerine takılmak istemiyor musun?\n"
            "Sana özel, kendi sunucunda çalışan **PRO BOT** kuralım!\n\n"
            "✅ **Sınırsız İndirme**\n"
            "✅ **2 GB Üzeri Dosya Desteği**\n"
            "✅ **Toplu Kanal Kopyalama**\n"
            "✅ **Otomatik Kanal Takip (Leech)**\n\n"
            "💬 **Detaylı bilgi ve fiyat için:** @yasin33"
        )
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("💬 İletişime Geç", url=f"https://t.me/{OWNER_USERNAME}"), InlineKeyboardButton("🔙 Geri", callback_data="shop_home")]]))
    elif data == "shop_credits":
        txt = "💰 **KREDİ PAKETLERİ**\n✅ 500 MB Limit Açılır.\n\n"
        btns = []
        for k, v in CREDIT_PACKS.items():
            lbl = v.get("price_lbl", f"{v['price_amt']} ⭐")
            txt += f"🔸 **{v['name']}** -> {lbl}\n"
            btns.append([InlineKeyboardButton(f"Satın Al: {lbl}", callback_data=f"buy_c_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="shop_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
    elif data == "shop_subs":
        txt = "📅 **VIP ABONELİK**\n✅ 1.5 GB Limit Açılır.\n\n"
        btns = []
        for k, v in SUB_PACKS.items():
            txt += f"🔹 **{v['name']}**\n   └ {v['desc']} -> {v['price_lbl']}\n"
            btns.append([InlineKeyboardButton(f"GRUBA GİR & ÖDE ({v['name']})", url=v['link'])])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="shop_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
    elif data.startswith("buy_c_"):
        key = data.split("_")[2]
        send_invoice_via_http(uid, key)
        await callback.answer("✅ Fatura gönderildi!", show_alert=True)
    elif data == "acc":
        txt, markup = main_menu(uid)
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    elif data == "ref":
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS SİSTEMİ**\n\nBu linki arkadaşlarına at:\n`{link}`\n\n🎁 **Siz:** +2 Kredi\n🎁 **Arkadaşınız:** +2 Ekstra Kredi (Toplam 5)"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("📤 Paylaş", url=f"https://t.me/share/url?url={link}"), InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    elif data == "admin_backup":
        await save_backup("Manuel", silent=False)
        await callback.answer("✅ Yedek Alındı!", show_alert=True)
    elif data == "admin_restore_info": await client.send_message(uid, "ℹ️ users.json dosyasını atın.")
    elif data == "admin_prices": await menu_switcher(client, callback.message, "`/setprice c100 150`", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "admin_discount_info": await client.send_message(uid, "ℹ️ `/discount 20`")
    elif data == "admin_addc": await client.send_message(uid, "ℹ️ `/addcredit ID MİKTAR`")
    elif data == "admin_adds": await client.send_message(uid, "ℹ️ `/setsub ID sub_trial`")
    elif data == "admin_cast": await client.send_message(uid, "ℹ️ `/duyuru MESAJ`")
    elif data == "howto": await menu_switcher(client, callback.message, "❓ **YARDIM**\n\nLink at -> İndir.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "service": await menu_switcher(client, callback.message, f"👨‍💻 **DESTEK**\n@{OWNER_USERNAME}", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "dl": await menu_switcher(client, callback.message, "📂 **İNDİRME MODU**\nLink yapıştır.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))

# 🔥 ÖDEME ONAYI & UPSELL BİLDİRİMİ
@bot.on_raw_update()
async def raw_pay(c, u, us, ch):
    if isinstance(u, UpdateBotPrecheckoutQuery):
        try: await c.invoke(SetBotPrecheckoutResults(query_id=u.query_id, success=True, error=None))
        except: pass

def is_pay(_, __, m): return bool(m.successful_payment)
pay_filter = filters.create(is_pay)

@bot.on_message(pay_filter)
async def success(c, m):
    pl = m.successful_payment.invoice_payload
    if pl.startswith("cred_"):
        key = pl.replace("cred_", "")
        pkg = CREDIT_PACKS.get(key)
        if pkg:
            add_credits(m.from_user.id, pkg["amount"])
            # 🔥 SATIŞ SONRASI UPSELL MESAJI 🔥
            await m.reply(
                f"🎉 **ÖDEME BAŞARILI!**\n"
                f"💰 +{pkg['amount']} Kredi yüklendi.\n"
                f"🟡 **LİMİTİNİZ 500 MB OLDU!**\n\n"
                f"🚀 _Daha büyük dosyalar (1.5 GB) indirmek ister misiniz?_\n"
                f"👑 **VIP Paket** alarak en yüksek limite geçebilirsiniz!", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 VIP AL (1.5 GB)", callback_data="shop_subs")]])
            )
            try: await c.send_message(OWNER_ID, f"💰 SATIŞ: {pkg['name']}")
            except: pass
    await save_backup("Satış", silent=False) 

# ==================== BAŞLATMA ====================
async def main():
    print("🤖 Başlatılıyor...")
    await bot.start()
    await userbot.start()
    await force_cache_refresh()
    await restore_data()
    asyncio.create_task(backup_loop())
    asyncio.create_task(worker())
    try: await idle()
    except: pass
    finally:
        await save_backup("Kapanış", silent=False)
        await bot.stop()
        await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
