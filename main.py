import os
import json
import time
import asyncio
import logging
import datetime
import requests
import re
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
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0")) 
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")

# 🔥 BOT KULLANICI ADI (BAŞINDA @ YOK)
FIXED_BOT_USERNAME = "YaelSaverBot"

# 🔗 ABONELİK LİNKLERİ (GRUP GİRİŞLERİ)
LINK_SUB_TRIAL = "https://t.me/+CqcEl_4PUgE1YWFh" # 200 Yıldızlık Grup
LINK_SUB_MID   = "https://t.me/+AxzfBTfLlHVlNWQx" # 750 Yıldızlık Grup
LINK_SUB_HIGH  = "https://t.me/+TM943UrHw-QxNzgx" # 1250 Yıldızlık Grup 

# ==================== 💰 FİYATLAR & LİMİTLER ====================

DEFAULT_CREDIT_PACKS = {
    "c100":  {"name": "🥉 100 KREDİ",  "amount": 100,  "price_amt": 150},
    "c250":  {"name": "🥈 250 KREDİ",  "amount": 250,  "price_amt": 350},
    "c500":  {"name": "🥇 500 KREDİ",  "amount": 500,  "price_amt": 650},
    "c1000": {"name": "💎 1000 KREDİ", "amount": 1000, "price_amt": 1200}
}
CREDIT_PACKS = DEFAULT_CREDIT_PACKS.copy()

SUB_PACKS = {
    "sub_trial": {"name": "⚡ BRONZ (30 Gün)",   "days": 30, "daily_limit": 5,  "desc": "Günde 5 Hak",  "price_lbl": "200 ⭐",  "link": LINK_SUB_TRIAL},
    "sub_mid":   {"name": "🔥 GÜMÜŞ (30 Gün)",   "days": 30, "daily_limit": 25, "desc": "Günde 25 Hak", "price_lbl": "750 ⭐",  "link": LINK_SUB_MID},
    "sub_high":  {"name": "👑 ALTIN (30 Gün)",    "days": 30, "daily_limit": 50, "desc": "Günde 50 Hak", "price_lbl": "1250 ⭐", "link": LINK_SUB_HIGH}
}

LIMIT_FREE = 50 * 1024 * 1024    
LIMIT_VIP  = 500 * 1024 * 1024   

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV72")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V72.0 FINAL FIX Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI ====================
db_cache = {"users": {}, "config": {"prices": DEFAULT_CREDIT_PACKS.copy()}}

async def restore_data():
    global db_cache, CREDIT_PACKS
    if LOG_CHANNEL == 0: return
    try:
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=20):
            if msg.document and msg.document.file_name == DB_FILE:
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f:
                    data = json.load(f)
                    if "users" in data: db_cache = data
                    if "config" in data and "prices" in data["config"]:
                        CREDIT_PACKS = data["config"]["prices"]
                        for k, v in CREDIT_PACKS.items():
                            if "price_amt" in v: v["price_lbl"] = f"{v['price_amt']} ⭐"
                print(f"✅ DATA YÜKLENDİ: {len(db_cache['users'])} kullanıcı.")
                return
    except: pass

async def save_backup(reason="Otomatik"):
    global db_cache, CREDIT_PACKS
    if LOG_CHANNEL == 0: return
    try:
        db_cache["config"] = {"prices": CREDIT_PACKS}
        with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
        total_users = len(db_cache.get("users", {}))
        await bot.send_document(LOG_CHANNEL, document=DB_FILE, caption=f"💾 YEDEK ({reason})\n👥 {total_users}")
    except: pass

async def backup_loop():
    while True:
        await asyncio.sleep(3600) # Sadece saatte bir
        await save_backup(reason="Saatlik")

# 🔥 USERBOT HAFIZA TEMİZLİĞİ (KÖR SORUNU ÇÖZÜMÜ)
async def refresh_userbot_cache():
    print("🔄 Userbot hafızası tazeleniyor... (Kanallar taranıyor)")
    try:
        # Dialogları gezerek Pyrogram'ın peer cache'ini dolduruyoruz
        count = 0
        async for dialog in userbot.get_dialogs(limit=500):
            count += 1
        print(f"✅ Userbot {count} sohbeti hafızaya aldı. Hazır!")
    except Exception as e:
        print(f"⚠️ Hafıza tazeleme hatası: {e}")

# ==================== 🧠 KULLANICI MANTIĞI ====================
def get_user(user_id):
    uid = str(user_id)
    today = datetime.date.today().isoformat()
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "balance": 3, "total_spent": 0, "sub_type": "none", "sub_expiry": 0,
            "daily_usage": 0, "last_reset": today, "invited_by": None
        }
    user = db_cache["users"][uid]
    if user.get("last_reset") != today:
        user["daily_usage"] = 0
        user["last_reset"] = today
        if user["sub_type"] != "none" and time.time() > user["sub_expiry"]:
            user["sub_type"] = "none"
            user["sub_expiry"] = 0
            try: bot.send_message(int(uid), "⚠️ **Aboneliğiniz Sona Erdi!**")
            except: pass
    return user

def check_access(user_id):
    if user_id == OWNER_ID: return True, "Patron"
    u = get_user(user_id)
    # 1. Abonelik
    if u["sub_type"] != "none":
        pkg = SUB_PACKS.get(u["sub_type"])
        if pkg and u["daily_usage"] < pkg["daily_limit"]: return True, "Abonelik"
    # 2. Kredi
    if u["balance"] > 0: return True, "Kredi"
    return False, "Yetersiz"

def get_size_limit(user_id):
    if user_id == OWNER_ID: return 100 * 1024 * 1024 * 1024
    u = get_user(user_id)
    is_vip = False
    if u["sub_type"] != "none": is_vip = True
    elif u["total_spent"] > 0: is_vip = True 
    if is_vip: return LIMIT_VIP
    return LIMIT_FREE

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
            "description": f"{pkg['amount']} Adet İndirme Kredisi (Süresiz)",
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
        try:
            allowed, reason = check_access(user_id)
            if not allowed:
                await status_msg.edit("⛔ **LİMİT DOLDU!**\nKredi veya abonelik alın.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Mağaza", callback_data="shop_home")]]))
                continue

            # 🔥 BASİTLEŞTİRİLMİŞ LİNK ANALİZİ
            chat_id, msg_id = None, None
            link = link.replace("https://", "").replace("http://", "").replace("t.me/", "").replace("telegram.me/", "")
            parts = link.split("/")
            
            try:
                if parts[0] == "c": # Özel Kanal: c/123456789/100
                    chat_id = int("-100" + parts[1])
                    msg_id = int(parts[2].split("?")[0])
                else: # Genel Kanal: username/100
                    chat_id = parts[0]
                    msg_id = int(parts[1].split("?")[0])
            except:
                await status_msg.edit("❌ Link formatı hatalı.")
                continue

            # 🛠️ ERİŞİM KONTROLÜ (CACHE ZORLAMA)
            try:
                # Userbot kanalı tanıyor mu diye bak, yoksa get_chat yap
                if str(chat_id).startswith("-100"): # Sadece ID ise kontrol et
                    try: await userbot.get_chat(chat_id)
                    except: pass 
            except: pass

            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except Exception as e:
                await status_msg.edit(f"🚫 **ERİŞİM YOK!**\n\nBot içeriği göremiyor.\nLütfen kanalın **Davet Linkini** bota atın.\nUserbot kanalda olmalı.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
                continue
                
            if target_msg and (target_msg.video or target_msg.photo or target_msg.document):
                # Kota Kontrol
                file_size = 0
                if target_msg.video: file_size = target_msg.video.file_size
                elif target_msg.document: file_size = target_msg.document.file_size
                elif target_msg.photo: file_size = 1024 
                
                user_limit = get_size_limit(user_id)
                if file_size > user_limit:
                    limit_mb = int(user_limit / 1024 / 1024)
                    is_vip = (user_limit == LIMIT_VIP)
                    if not is_vip:
                        msg_txt = f"⚠️ **LİMİT (50 MB)**\n\nDosya çok büyük.\n🚀 **500 MB** indirmek için Premium alın."
                        btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Premium Al", callback_data="shop_home")]])
                    else:
                        msg_txt = f"🛑 **SİSTEM SINIRI (500 MB)**\nBu dosya teknik sınırı aşıyor."
                        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]])
                    await status_msg.edit(msg_txt, reply_markup=btn)
                    continue

                await status_msg.edit("⬇️ **İndiriliyor...**")
                path = await userbot.download_media(target_msg)
                await status_msg.edit("⬆️ **Yükleniyor...**")
                
                caption = f"📥 **İndirildi:** @{FIXED_BOT_USERNAME}\n🔓 **Premium İndirici**"
                if target_msg.video: await client.send_video(user_id, path, caption=caption)
                elif target_msg.photo: await client.send_photo(user_id, path, caption=caption)
                elif target_msg.document: await client.send_document(user_id, path, caption=caption)
                
                # 🔥 HAKKI BURADA DÜŞÜRÜYORUM (KESİN DÜŞER)
                uid = str(user_id)
                u = db_cache["users"][uid]
                used_type = ""
                
                if u["sub_type"] != "none":
                    u["daily_usage"] += 1
                    used_type = "Abonelik"
                else:
                    u["balance"] -= 1
                    u["total_spent"] += 1
                    used_type = "Kredi"
                
                info = ""
                if used_type == "Abonelik":
                    rem = SUB_PACKS[u["sub_type"]]["daily_limit"] - u["daily_usage"]
                    info = f"📅 Abonelik: **{rem} Hak Kaldı**"
                else:
                    info = f"💰 Kredi: **{u['balance']} Kaldı**"
                
                await status_msg.edit(f"✅ **Tamamlandı!**\n{info}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                
                if os.path.exists(path): os.remove(path)
                # BURADA YEDEK ALMA YOK! (Sadece saatlik alacak)
            else: await status_msg.edit("❌ Medya yok.")
        except Exception as e:
            try: await status_msg.edit(f"❌ Hata: {e}")
            except: pass
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        await asyncio.sleep(2)

# ==================== ⚡ MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Link İndir", callback_data="dl"), InlineKeyboardButton("💰 Hesabım", callback_data="acc")],
        [InlineKeyboardButton("💎 MAĞAZA", callback_data="shop_home")],
        [InlineKeyboardButton("❓ Yardım", callback_data="howto"), InlineKeyboardButton("👥 Referans", callback_data="ref")],
        [InlineKeyboardButton("👨‍💻 Destek", callback_data="service")]
    ])

def shop_home_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 KREDİ (Otomatik)", callback_data="shop_credits")],
        [InlineKeyboardButton("📅 ABONELİK (Yıldızla Gruba Gir)", callback_data="shop_subs")],
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
    await menu_switcher(client, message, f"👋 **Merhaba {message.from_user.first_name}!**\n\nTelegram'ın en hızlı indiricisine hoş geldin.\n🎁 **Hediye:** 3 Kredi Tanımlandı.\n\n👇 **Menü:**", main_menu())

# 👑 ADMIN
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_cmd(client, message):
    tot = len(db_cache["users"])
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Fiyat Listesi", callback_data="admin_prices"), InlineKeyboardButton("🏷️ İndirim Yap", callback_data="admin_discount_info")],
        [InlineKeyboardButton("➕ Kredi Ver", callback_data="admin_addc"), InlineKeyboardButton("➕ Abone Yap", callback_data="admin_adds")],
        [InlineKeyboardButton("📢 Duyuru", callback_data="admin_cast"), InlineKeyboardButton("📊 İstatistik", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Yedek Al", callback_data="admin_backup"), InlineKeyboardButton("🔙 Çıkış", callback_data="back_home")]
    ])
    await menu_switcher(client, message, f"👑 **YÖNETİCİ PANELİ**\n\nAktif Kullanıcı: {tot}", btns)

@bot.on_message(filters.command("setprice") & filters.user(OWNER_ID))
async def set_price(c, m):
    try:
        code = m.command[1]
        price = int(m.command[2])
        if code in CREDIT_PACKS:
            CREDIT_PACKS[code]["price_amt"] = price
            CREDIT_PACKS[code]["price_lbl"] = f"{price} ⭐"
            await m.reply(f"✅ **Güncellendi:** {code} -> {price} ⭐")
            await save_backup("Fiyat Güncelleme")
        else: await m.reply("❌ Paket kodu geçersiz")
    except: await m.reply("❌ `/setprice [KOD] [YENİ_FİYAT]`")

@bot.on_message(filters.command("discount") & filters.user(OWNER_ID))
async def discount_cmd(c, m):
    try:
        percent = int(m.command[1])
        if percent == 0:
            global CREDIT_PACKS
            CREDIT_PACKS = DEFAULT_CREDIT_PACKS.copy()
            await m.reply("✅ İndirimler kaldırıldı.")
        else:
            for k, v in CREDIT_PACKS.items():
                original = DEFAULT_CREDIT_PACKS[k]["price_amt"]
                new_price = int(original - (original * percent / 100))
                CREDIT_PACKS[k]["price_amt"] = new_price
                CREDIT_PACKS[k]["price_lbl"] = f"{new_price} ⭐ (⬇️%{percent})"
            await m.reply(f"✅ %{percent} İndirim Uygulandı!")
        await save_backup("İndirim")
    except: await m.reply("❌ `/discount [YÜZDE]`")

@bot.on_message(filters.command("addcredit") & filters.user(OWNER_ID))
async def manual_c(c, m):
    try:
        t, a = int(m.command[1]), int(m.command[2])
        add_credits(t, a)
        await m.reply(f"✅ `{t}` -> `{a}` kredi.")
        await save_backup("Manuel")
    except: await m.reply("❌ `/addcredit ID MİKTAR`")

@bot.on_message(filters.command("setsub") & filters.user(OWNER_ID))
async def manual_s(c, m):
    try:
        t, p = int(m.command[1]), m.command[2]
        if p not in SUB_PACKS: return await m.reply("❌ Paket yok!")
        activate_subscription(t, p)
        await m.reply(f"✅ `{t}` -> `{p}`.")
        await save_backup("Manuel")
    except: await m.reply("❌ `/setsub ID PAKET`")

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
        return await message.reply("⛔ **HAKKINIZ BİTTİ!**\nDevam etmek için mağazadan satın alım yapın.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Mağaza", callback_data="shop_home")]]))
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
    elif data == "shop_home": await menu_switcher(client, callback.message, "🛒 **MAĞAZA**\nLütfen bir kategori seçiniz:", shop_home_menu())
    
    elif data == "shop_credits":
        txt = "💰 **KREDİ PAKETLERİ (OTOMATİK)**\nSatın al'a basınca fatura çıkar.\n\n"
        btns = []
        for k, v in CREDIT_PACKS.items():
            lbl = v.get("price_lbl", f"{v['price_amt']} ⭐")
            txt += f"🔸 **{v['name']}** -> {lbl}\n"
            btns.append([InlineKeyboardButton(f"Satın Al: {lbl}", callback_data=f"buy_c_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="shop_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
        
    elif data == "shop_subs":
        txt = "📅 **ABONELİK PAKETLERİ**\nLinke tıklayıp Yıldız ile gruba girin.\nYönetici aboneliği manuel tanımlayacaktır.\n\n"
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
        sub_txt = "Yok"
        if u["sub_type"] != "none":
            days = int((u["sub_expiry"] - time.time()) / 86400)
            sub_txt = f"{SUB_PACKS[u['sub_type']]['name']} ({days} Gün)"
        txt = (f"👤 **PROFİLİM**\n\n💰 **Kredi:** {u['balance']}\n📅 **Abonelik:** {sub_txt}\n📉 İndirme: {u.get('total_spent', 0)}")
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "ref":
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS**\nArkadaşını davet et, **+2 Kredi** kazan!\n\n🔗 `{link}`"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("📤 Paylaş", url=f"https://t.me/share/url?url={link}"), InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    
    elif data == "admin_stats":
        t = str(len(db_cache.get("users", {})))
        c = str(sum(x.get("balance", 0) for x in db_cache["users"].values()))
        s = str(sum(1 for x in db_cache["users"].values() if x.get("sub_type") != "none"))
        await menu_switcher(client, callback.message, f"📊 **İSTATİSTİKLER**\n\n👤 Üye Sayısı: **{t}**\n💰 Toplam Kredi: **{c}**\n📅 Aktif Abone: **{s}**", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "admin_backup":
        await save_backup("Manuel")
        await callback.answer("✅ Yedek Kanalına Gönderildi!", show_alert=True)
    elif data == "admin_prices":
        txt = "💰 **MEVCUT FİYATLAR**\n\n"
        for k, v in CREDIT_PACKS.items(): txt += f"🔹 `{k}`: {v.get('price_lbl', v['price_amt'])}\n"
        txt += "\n🛠 **Değiştirmek İçin:**\n`/setprice c100 150`"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
    elif data == "admin_discount_info": await client.send_message(uid, "ℹ️ `/discount 20` (%20 İndirim)\n`/discount 0` (Sıfırla)")
    elif data == "admin_addc": await client.send_message(uid, "ℹ️ `/addcredit ID MİKTAR`")
    elif data == "admin_adds": await client.send_message(uid, "ℹ️ `/setsub ID sub_trial`\nPaketler: sub_trial, sub_mid, sub_high")
    elif data == "admin_cast": await client.send_message(uid, "ℹ️ `/duyuru MESAJ`")
    
    elif data == "howto": await menu_switcher(client, callback.message, "❓ **YARDIM**\n\n1️⃣ İçerik linkini bota at.\n2️⃣ Bot indirip sana yollasın.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_home")]]))
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
    # BURADA YEDEK YOK (LOG KİRLİLİĞİ OLMASIN DİYE)

# ==================== BAŞLATMA ====================
async def main():
    print("🤖 Başlatılıyor...")
    await bot.start()
    await userbot.start()
    
    # 🔥 AÇILIŞTA USERBOTU GÜNCELLE
    await refresh_userbot_cache()
    
    await restore_data()
    asyncio.create_task(backup_loop())
    asyncio.create_task(worker())
    print("✅ V72.0 FINAL FIX ACTIVE")
    await idle()
    await save_backup("Kapanış")
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

