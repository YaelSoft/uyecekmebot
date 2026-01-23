import os
import json
import time
import asyncio
import logging
import datetime
import requests
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant, FloodWait

# 🔥 HAM VERİ (Ödeme Onayı İçin)
from pyrogram.raw.types import UpdateBotPrecheckoutQuery
from pyrogram.raw.functions.messages import SetBotPrecheckoutResults

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) 
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")

# 🔥🔥🔥 BOT ADINI YAZ (BAŞINDA @ YOK) 🔥🔥🔥
FIXED_BOT_USERNAME = "YaelSaverBot"

# ==================== 💰 FİYATLANDIRMA ====================
# 1️⃣ KREDİ PAKETLERİ (KULLANDIKÇA BİTER)
CREDIT_PACKS = {
    "c100":  {"name": "🥉 100 KREDİ",  "amount": 100,  "price_lbl": "100 ⭐", "price_amt": 100},
    "c250":  {"name": "🥈 250 KREDİ",  "amount": 250,  "price_lbl": "250 ⭐", "price_amt": 250},
    "c500":  {"name": "🥇 500 KREDİ",  "amount": 500,  "price_lbl": "500 ⭐", "price_amt": 500},
    "c1000": {"name": "💎 1000 KREDİ", "amount": 1000, "price_lbl": "900 ⭐", "price_amt": 900}
}

# 2️⃣ ABONELİK PAKETLERİ (GÜNLÜK YENİLENİR)
SUB_PACKS = {
    "sub_trial": {"name": "⚡ DENEME (30 Gün)", "days": 30, "daily_limit": 5,  "price_lbl": "150 ⭐", "price_amt": 150},
    "sub_mid":   {"name": "🔥 STANDART (30 Gün)", "days": 30, "daily_limit": 25, "price_lbl": "400 ⭐", "price_amt": 400},
    "sub_high":  {"name": "👑 PRO (30 Gün)",    "days": 30, "daily_limit": 50, "price_lbl": "750 ⭐", "price_amt": 750}
}

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV57")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V57.0 FIXED Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI YÖNETİMİ (KAYA GİBİ SAĞLAM) ====================
db_cache = {"users": {}}

async def restore_data():
    global db_cache
    if LOG_CHANNEL == 0: return
    print("📥 VERİLER YÜKLENİYOR...")
    try:
        # Son 50 mesaja bak, en son atılan users.json'u bul
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=50):
            if msg.document and msg.document.file_name == DB_FILE:
                print(f"📥 Yedek bulundu: {msg.id}")
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f:
                    data = json.load(f)
                    if "users" in data:
                        db_cache = data
                        print(f"✅ VERİLER KURTARILDI! {len(db_cache['users'])} kullanıcı yüklendi.")
                        return
    except Exception as e:
        print(f"❌ Veri kurtarma hatası: {e}")

async def save_backup(reason="Otomatik"):
    if LOG_CHANNEL == 0: return
    try:
        with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
        total_users = len(db_cache.get("users", {}))
        total_credits = sum(u.get("balance", 0) for u in db_cache["users"].values())
        
        await bot.send_document(
            LOG_CHANNEL, 
            document=DB_FILE, 
            caption=f"💾 **SİSTEM YEDEĞİ**\n📝 Sebep: {reason}\n⏰ Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}\n👥 Kullanıcı: {total_users}\n💰 Toplam Kredi: {total_credits}"
        )
        print(f"💾 Yedek alındı: {reason}")
    except Exception as e:
        print(f"❌ Yedek hatası: {e}")

async def backup_loop():
    while True:
        await asyncio.sleep(1800) # 30 dakikada bir otomatik yedek
        await save_backup(reason="Periyodik")

# ==================== 🧠 KULLANICI & BAKİYE MANTIĞI ====================
def get_user(user_id):
    uid = str(user_id)
    today = datetime.date.today().isoformat()
    
    # 🎁 YENİ KULLANICIYA 3 HAK
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "balance": 3,
            "total_spent": 0,
            "sub_type": "none",
            "sub_expiry": 0,
            "daily_usage": 0,
            "last_reset": today,
            "invited_by": None
        }
    
    user = db_cache["users"][uid]
    
    # Günlük Sıfırlama (Abonelik için)
    if user.get("last_reset") != today:
        user["daily_usage"] = 0
        user["last_reset"] = today
        # Abonelik bitti mi?
        if user["sub_type"] != "none" and time.time() > user["sub_expiry"]:
            user["sub_type"] = "none"
            user["sub_expiry"] = 0
            try: bot.send_message(int(uid), "⚠️ **Aboneliğiniz Sona Erdi!**")
            except: pass
            
    return user

# YETKİ KONTROLÜ
def check_access(user_id):
    if user_id == OWNER_ID: return True, "Patron"
    u = get_user(user_id)
    
    # 1. Abonelik Var mı?
    if u["sub_type"] != "none":
        pkg = SUB_PACKS.get(u["sub_type"])
        if pkg and u["daily_usage"] < pkg["daily_limit"]:
            return True, "Abonelik"
    
    # 2. Kredi Var mı?
    if u["balance"] > 0:
        return True, "Kredi"
        
    return False, "Yetersiz"

# KREDİ DÜŞÜRME (ARTIK HATA YAPMAZ)
def use_right(user_id):
    if user_id == OWNER_ID: return "Admin"
    uid = str(user_id)
    u = db_cache["users"][uid]
    
    # Abonelikten düş
    if u["sub_type"] != "none":
        pkg = SUB_PACKS.get(u["sub_type"])
        if pkg and u["daily_usage"] < pkg["daily_limit"]:
            u["daily_usage"] += 1
            return "Abonelik"
            
    # Krediden düş
    if u["balance"] > 0:
        u["balance"] -= 1
        u["total_spent"] += 1
        return "Kredi"
    
    return "Hata"

# KREDİ EKLEME
def add_credits(user_id, amount):
    uid = str(user_id)
    get_user(uid)
    db_cache["users"][uid]["balance"] += amount
    return db_cache["users"][uid]["balance"]

# ABONELİK VERME
def activate_subscription(user_id, sub_key):
    uid = str(user_id)
    get_user(uid)
    pkg = SUB_PACKS[sub_key]
    expiry = time.time() + (pkg["days"] * 86400)
    db_cache["users"][uid]["sub_type"] = sub_key
    db_cache["users"][uid]["sub_expiry"] = expiry
    db_cache["users"][uid]["daily_usage"] = 0
    return pkg["name"]

# ==================== 💳 FATURA (HTTP REQUEST) ====================
def send_invoice_via_http(chat_id, payload_key, title, price_amount):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        payload = {
            "chat_id": chat_id,
            "title": title,
            "description": "Otomatik Teslimat | Anında Yükleme",
            "payload": payload_key,
            "provider_token": "", # Stars için boş
            "currency": "XTR",
            "prices": json.dumps([{"label": title, "amount": price_amount}])
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
        try:
            # 🛑 SON DAKİKA BAKİYE KONTROLÜ
            allowed, reason = check_access(user_id)
            if not allowed:
                await status_msg.edit("⛔ **YETERSİZ BAKİYE!**\nİşlem iptal edildi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Mağaza", callback_data="shop_home")]]))
                continue

            chat_id, msg_id = None, None
            if "t.me/c/" in link:
                parts = link.split("t.me/c/")[1].split("/")
                chat_id = int("-100" + parts[0]); msg_id = int(parts[1].split("?")[0])
            else:
                parts = link.split("t.me/")[1].split("/"); chat_id = parts[0]; msg_id = int(parts[1].split("?")[0])
            
            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                await status_msg.edit("🚫 **ERİŞİM YOK!**\nBotun kanalda olduğundan emin olun veya davet linkini gönderin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
                continue
                
            if target_msg and (target_msg.video or target_msg.photo or target_msg.document):
                await status_msg.edit("⬇️ **İndiriliyor...**")
                path = await userbot.download_media(target_msg)
                await status_msg.edit("⬆️ **Yükleniyor...**")
                
                caption = f"📥 **İndirildi:** @{FIXED_BOT_USERNAME}\n🔓 **Premium İndirici**"
                if target_msg.video: await client.send_video(user_id, path, caption=caption, width=target_msg.video.width, height=target_msg.video.height)
                elif target_msg.photo: await client.send_photo(user_id, path, caption=caption)
                elif target_msg.document: await client.send_document(user_id, path, caption=caption)
                
                # 🔥 HAKKI BURADA DÜŞÜRÜYORUZ (KESİN ÇÖZÜM)
                src = use_right(user_id)
                u = get_user(user_id)
                
                info = ""
                if src == "Abonelik":
                    rem = SUB_PACKS[u["sub_type"]]["daily_limit"] - u["daily_usage"]
                    info = f"📅 Abonelik Hakkı: **{rem} Kaldı**"
                else:
                    info = f"💰 Kalan Kredi: **{u['balance']}**"
                
                await status_msg.edit(f"✅ **Tamamlandı!**\n{info}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                if os.path.exists(path): os.remove(path)
                
                # Her indirmede yedeği güncelle (Veri kaybına son)
                asyncio.create_task(save_backup("Otomatik-İndirme"))
            else: await status_msg.edit("❌ Medya bulunamadı.")
        except Exception as e:
            try: await status_msg.edit(f"❌ Hata: {e}")
            except: pass
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        await asyncio.sleep(2)

# ==================== ⚡ MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="dl"), InlineKeyboardButton("💰 Hesabım", callback_data="acc")],
        [InlineKeyboardButton("💎 MAĞAZA (Kredi & Abone)", callback_data="shop_home")],
        [InlineKeyboardButton("❓ Yardım", callback_data="howto"), InlineKeyboardButton("👥 Referans", callback_data="ref")],
        [InlineKeyboardButton("👨‍💻 Admin & Destek", callback_data="service")]
    ])

def shop_home_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 KREDİ PAKETLERİ (Süresiz)", callback_data="shop_credits")],
        [InlineKeyboardButton("📅 AYLIK ABONELİK (Günlük Yenilenir)", callback_data="shop_subs")],
        [InlineKeyboardButton("💳 IBAN / Havale ile Al", callback_data="shop_iban")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="back_home")]
    ])

async def menu_switcher(client, message, text, reply_markup=None):
    try: await message.delete()
    except: pass
    try: await client.send_message(message.chat.id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    except: pass

@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    u = get_user(user_id)
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if str(ref_id) != str(user_id):
                u = get_user(user_id)
                if u["invited_by"] is None:
                    db_cache["users"][str(user_id)]["invited_by"] = str(ref_id)
                    db_cache["users"][str(user_id)]["balance"] += 3 
                    if str(ref_id) in db_cache["users"]:
                        db_cache["users"][str(ref_id)]["balance"] += 2
                        try: await client.send_message(int(ref_id), "🎉 **Referans!** +2 Kredi kazandın.")
                        except: pass
        except: pass
    await menu_switcher(client, message, f"👋 **Merhaba {message.from_user.first_name}!**\n\nTelegram'ın en hızlı indiricisine hoş geldin.\n🎁 **Hediye:** 3 Kredi tanımlandı.\n\n👇 **Menü:**", main_menu())

# 👑 ADMIN PANELİ (DÜZELTİLDİ)
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_cmd(client, message):
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Kredi Ver", callback_data="admin_addc"), InlineKeyboardButton("➕ Abone Yap", callback_data="admin_adds")],
        [InlineKeyboardButton("📢 Duyuru", callback_data="admin_cast"), InlineKeyboardButton("📊 İstatistik", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Yedek Al", callback_data="admin_backup"), InlineKeyboardButton("🔙 Çıkış", callback_data="back_home")]
    ])
    await menu_switcher(client, message, "👑 **YÖNETİCİ PANELİ**", btns)

@bot.on_message(filters.command("addcredit") & filters.user(OWNER_ID))
async def manual_c(c, m):
    try:
        t, a = int(m.command[1]), int(m.command[2])
        add_credits(t, a)
        await m.reply(f"✅ `{t}` kullanıcısına `{a}` kredi eklendi.")
        await save_backup("Admin Kredi")
    except: await m.reply("❌ Kullanım: `/addcredit ID MİKTAR`")

@bot.on_message(filters.command("setsub") & filters.user(OWNER_ID))
async def manual_s(c, m):
    try:
        t, p = int(m.command[1]), m.command[2]
        if p not in SUB_PACKS: return await m.reply(f"❌ Paketler: {', '.join(SUB_PACKS.keys())}")
        activate_subscription(t, p)
        await m.reply(f"✅ `{t}` kullanıcısına `{p}` tanımlandı.")
        await save_backup("Admin Sub")
    except: await m.reply("❌ Kullanım: `/setsub ID PAKET_KODU`")

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broad(c, m):
    if len(m.command)<2: return await m.reply("❌ Mesaj?")
    txt = m.text.split(None, 1)[1]
    cnt = 0
    msg = await m.reply("📢 Gönderiliyor...")
    for uid in db_cache["users"]:
        try: await c.send_message(int(uid), f"📢 **DUYURU**\n\n{txt}"); cnt+=1; await asyncio.sleep(0.05)
        except: pass
    await msg.edit(f"✅ {cnt} kişiye iletildi.")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_link(client, message):
    if "join" in message.text: return
    user_id = message.from_user.id
    allowed, reason = check_access(user_id)
    if not allowed:
        return await message.reply("⛔ **BAKİYENİZ YETERSİZ!**\n\nİndirme yapmak için Mağaza'dan yükleme yapın.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Mağaza", callback_data="shop_home")]]))
    
    st = await message.reply(f"⏳ **Sıraya Alındı...**")
    u = get_user(user_id)
    prio = 1 if u["sub_type"] != "none" else 2
    await download_queue.put((prio, (client, st, message.text, user_id)))

@bot.on_callback_query()
async def cb_handler(client, callback):
    try: await callback.answer()
    except: pass
    data = callback.data
    uid = callback.from_user.id
    u = get_user(uid)
    
    if data == "back_home": await menu_switcher(client, callback.message, f"👋 **Ana Menü**", main_menu())
    elif data == "shop_home": await menu_switcher(client, callback.message, "🛒 **MAĞAZA**\n\nLütfen bir kategori seçiniz:", shop_home_menu())
    
    elif data == "shop_credits":
        txt = "💰 **KREDİ PAKETLERİ (Süresiz)**\nKullandıkça düşer.\n\n"
        btns = []
        for k, v in CREDIT_PACKS.items():
            txt += f"🔸 **{v['name']}** -> {v['price_lbl']}\n"
            btns.append([InlineKeyboardButton(f"Satın Al: {v['price_lbl']}", callback_data=f"buy_c_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="shop_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
        
    elif data == "shop_subs":
        txt = "📅 **AYLIK ABONELİKLER**\nHer gün haklarınız yenilenir.\n\n"
        btns = []
        for k, v in SUB_PACKS.items():
            txt += f"🔹 **{v['name']}** -> {v['price_lbl']}\n"
            btns.append([InlineKeyboardButton(f"Abone Ol: {v['price_lbl']}", callback_data=f"buy_s_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="shop_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
        
    elif data == "shop_iban":
        txt = f"💳 **IBAN / HAVALE İLE ÖDEME**\n\nTelegram Yıldızı kullanmıyorsanız, IBAN ile ödeme yapıp paket tanımlatabilirsiniz.\n\n👤 **İletişim:** @{OWNER_USERNAME}"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("💬 Admine Yaz", url=f"https://t.me/{OWNER_USERNAME}"), InlineKeyboardButton("🔙 Geri", callback_data="shop_home")]]))

    elif data.startswith("buy_c_"):
        key = data.split("_")[2]
        pkg = CREDIT_PACKS[key]
        send_invoice_via_http(uid, f"cred_{key}", pkg["name"], pkg["price_amt"])
        await callback.answer("✅ Fatura Gönderildi!", show_alert=True)
        
    elif data.startswith("buy_s_"):
        key = data.split("_")[2]
        pkg = SUB_PACKS[key]
        send_invoice_via_http(uid, f"subs_{key}", pkg["name"], pkg["price_amt"])
        await callback.answer("✅ Fatura Gönderildi!", show_alert=True)

    elif data == "acc":
        sub_txt = "Yok"
        if u["sub_type"] != "none":
            days = int((u["sub_expiry"] - time.time()) / 86400)
            limit = SUB_PACKS[u["sub_type"]]["daily_limit"]
            sub_txt = f"{SUB_PACKS[u['sub_type']]['name']}\n⏳ {days} Gün Kaldı\n📉 Bugün: {limit - u['daily_usage']} Hak"
        
        txt = (f"👤 **PROFİLİM**\n\n"
               f"💰 **Kredi:** {u['balance']}\n"
               f"📅 **Abonelik:** {sub_txt}\n\n"
               f"📉 Toplam İndirme: {u.get('total_spent', 0)}")
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "ref":
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS**\nArkadaşını davet et, **+2 Kredi** kazan!\n\n🔗 `{link}`"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("📤 Paylaş", url=f"https://t.me/share/url?url={link}"), InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    
    # 👑 ADMIN FONKSİYONLARI (ARTIK ÇALIŞIYOR)
    elif data == "admin_stats":
        t = len(db_cache["users"])
        c = sum(x["balance"] for x in db_cache["users"].values())
        s = sum(1 for x in db_cache["users"].values() if x["sub_type"] != "none")
        await menu_switcher(client, callback.message, f"📊 **İSTATİSTİK**\n\n👤 Toplam Üye: **{t}**\n💰 Dolaşan Kredi: **{c}**\n📅 Aktif Abone: **{s}**", admin_menu())
    elif data == "admin_backup":
        await save_backup("Manuel")
        await callback.answer("✅ Yedek Kanalına Gönderildi!", show_alert=True)
    elif data == "admin_addc": await client.send_message(uid, "ℹ️ Komut: `/addcredit ID MİKTAR`")
    elif data == "admin_adds": await client.send_message(uid, "ℹ️ Komut: `/setsub ID sub_trial`\nPaketler: sub_trial, sub_mid, sub_high")
    elif data == "admin_cast": await client.send_message(uid, "ℹ️ Komut: `/duyuru MESAJ`")
    elif data == "howto": await menu_switcher(client, callback.message, "❓ **YARDIM**\n\nLinki bota atın, indirsin.\nBot kanalda değilse 'Erişim Yok' der, o zaman davet linkini atın.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "service": await menu_switcher(client, callback.message, f"👨‍💻 **DESTEK**\n\n@{OWNER_USERNAME}", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "dl": await menu_switcher(client, callback.message, "📂 **İndirme Modu**\nLink gönderin.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))

# 🔥 ÖDEME ONAYI
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
            await m.reply(f"🎉 **BAŞARILI!**\n💰 +{pkg['amount']} Kredi yüklendi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Cüzdan", callback_data="acc")]]))
            try: await c.send_message(OWNER_ID, f"💰 SATIŞ: {pkg['name']}")
            except: pass
    elif pl.startswith("subs_"):
        key = pl.replace("subs_", "")
        pkg = SUB_PACKS.get(key)
        if pkg:
            activate_subscription(m.from_user.id, key)
            await m.reply(f"🎉 **BAŞARILI!**\n📅 {pkg['name']} tanımlandı.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 Profil", callback_data="acc")]]))
            try: await c.send_message(OWNER_ID, f"📅 SATIŞ: {pkg['name']}")
            except: pass
    await save_backup("Satış")

# ==================== BAŞLATMA ====================
async def main():
    print("🤖 Başlatılıyor...")
    await bot.start()
    await userbot.start()
    await restore_data()
    asyncio.create_task(backup_loop())
    asyncio.create_task(worker())
    print("✅ V57.0 FIXED FINAL ACTIVE")
    await idle()
    await save_backup("Kapanış")
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
