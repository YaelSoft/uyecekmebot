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
# Manuel Handler eklemek için gerekli kütüphaneler
from pyrogram.handlers import PreCheckoutQueryHandler, MessageHandler
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, ChannelPrivate, UserAlreadyParticipant, FloodWait

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

# 💰 FİYAT & LİMİT STRATEJİSİ (DÜZELTİLDİ: 750 MB SINIRI)
PACKAGES = {
    "free":   {"name": "ÜCRETSİZ","days": 0,   "limit": 0,   "size_mb": 100, "stars": 0},
    "bronze": {"name": "BRONZ",   "days": 20,  "limit": 5,   "size_mb": 200, "stars": 100},
    "silver": {"name": "GÜMÜŞ",   "days": 30,  "limit": 20,  "size_mb": 350, "stars": 350},
    "gold":   {"name": "ALTIN",   "days": 30,  "limit": 120, "size_mb": 500, "stars": 750},
    # BURAYI DÜZELTTİK: 2000 MB -> 750 MB (Sunucu Güvenliği İçin)
    "elite":  {"name": "ELİT",    "days": 365, "limit": 500, "size_mb": 750, "stars": 3300}
}

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV37")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V37.0 Safe Mode Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI ====================
db_cache = {"users": {}}

async def restore_data():
    global db_cache
    if LOG_CHANNEL == 0: return
    print(f"📥 Veriler geri yükleniyor...")
    try:
        async for msg in bot.get_chat_history(LOG_CHANNEL, limit=10):
            if msg.document and msg.document.file_name == DB_FILE:
                await bot.download_media(msg, file_name=DB_FILE)
                with open(DB_FILE, "r") as f:
                    data = json.load(f)
                    if "users" in data: db_cache = data
                    else: db_cache["users"] = data 
                print(f"✅ VERİLER KURTARILDI! {len(db_cache['users'])} müşteri.")
                return
    except: pass

async def save_backup(reason="Otomatik"):
    if LOG_CHANNEL == 0: return
    try:
        with open(DB_FILE, "w") as f: json.dump(db_cache, f, indent=4)
        total_users = len(db_cache.get("users", {}))
        await bot.send_document(
            LOG_CHANNEL, 
            document=DB_FILE, 
            caption=f"💾 **YEDEK** ({reason})\n⏰ {datetime.datetime.now().strftime('%H:%M')}\n👥 Üye: {total_users}"
        )
    except: pass

async def backup_loop():
    while True:
        await asyncio.sleep(3600)
        await save_backup(reason="Saatlik")

# ==================== 🧠 KULLANICI FONKSİYONLARI ====================
def get_user(user_id):
    uid = str(user_id)
    today = datetime.date.today().isoformat()
    
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "daily_limit": 0,
            "daily_usage": 0,
            "vip_until": 0,
            "package": "free",
            "last_reset": today,
            "invited_by": None,
            "ref_count": 0
        }
    
    user = db_cache["users"][uid]
    
    if user.get("last_reset") != today:
        user["daily_usage"] = 0
        user["last_reset"] = today
        
        if user["vip_until"] > 0 and time.time() > user["vip_until"]:
            user["vip_until"] = 0
            user["package"] = "free"
            try: bot.send_message(int(uid), "⚠️ **Paket Süreniz Doldu!**")
            except: pass
        
        if user["package"] == "free":
            user["daily_limit"] = 0 
        else:
            pkg_name = user.get("package", "bronze")
            if pkg_name not in PACKAGES: pkg_name = "bronze"
            user["daily_limit"] = PACKAGES[pkg_name]["limit"]
            
    return user

def check_rights(user_id):
    if user_id == OWNER_ID: return True, "Patron"
    u = get_user(user_id)
    limit = u["daily_limit"]
    usage = u["daily_usage"]
    if limit > 0 and usage < limit: return True, limit - usage
    return False, 0

def use_right(user_id):
    if user_id == OWNER_ID: return
    db_cache["users"][str(user_id)]["daily_usage"] += 1

def add_vip(user_id, pkg_key):
    uid = str(user_id)
    pkg = PACKAGES[pkg_key]
    get_user(uid)
    now = time.time()
    current_exp = db_cache["users"][uid]["vip_until"]
    if current_exp > now: new_exp = current_exp + (pkg["days"] * 86400)
    else: new_exp = now + (pkg["days"] * 86400)
    db_cache["users"][uid]["vip_until"] = new_exp
    db_cache["users"][uid]["daily_limit"] = pkg["limit"]
    db_cache["users"][uid]["package"] = pkg_key
    return new_exp

def get_user_size_limit(user_id):
    if user_id == OWNER_ID: return 750 * 1024 * 1024 # Admin de 750 MB
    u = get_user(user_id)
    pkg_key = u.get("package", "free")
    limit_mb = PACKAGES.get(pkg_key, PACKAGES["free"])["size_mb"]
    return limit_mb * 1024 * 1024

# ==================== 🏭 İŞÇİ (WORKER) ====================
download_queue = asyncio.PriorityQueue()

async def worker():
    print("👷 İşçi Hazır...")
    while True:
        priority, task = await download_queue.get()
        client, status_msg, link, user_id = task
        try:
            chat_id, msg_id = None, None
            if "t.me/c/" in link:
                parts = link.split("t.me/c/")[1].split("/")
                chat_id = int("-100" + parts[0]); msg_id = int(parts[1].split("?")[0])
            else:
                parts = link.split("t.me/")[1].split("/"); chat_id = parts[0]; msg_id = int(parts[1].split("?")[0])

            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                txt = "🚫 **ERİŞİM SAĞLANAMADI**\n\n1️⃣ Grubun **Davet Linkini** atın.\n2️⃣ Link yoksa özel bot gerekir.\n👨‍💻 Destek: 'Admin & Hizmetler' butonu."
                await status_msg.edit(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                continue

            if target_msg and (target_msg.video or target_msg.photo or target_msg.document):
                file_size = 0
                if target_msg.video: file_size = target_msg.video.file_size
                elif target_msg.document: file_size = target_msg.document.file_size
                elif target_msg.photo: file_size = 1024
                
                user_limit_bytes = get_user_size_limit(user_id)
                if file_size > user_limit_bytes:
                    await status_msg.edit(
                        f"🛑 **LİMİT AŞIMI!**\nDosya: {file_size/1024/1024:.1f} MB\nLimitiniz: {user_limit_bytes/1024/1024:.0f} MB\n\nBu dosyayı indirmek için paketinizi yükseltin. (Max 750 MB)",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Yükselt", callback_data="shop"), InlineKeyboardButton("🔙 Menü", callback_data="back_home")]])
                    )
                    continue

                await status_msg.edit("⬇️ **İndiriliyor...**")
                path = await userbot.download_media(target_msg)
                
                await status_msg.edit("⬆️ **Yükleniyor...**")
                caption = "✅ **Yael Saver**"
                if target_msg.video: await client.send_video(user_id, path, caption=caption, width=target_msg.video.width, height=target_msg.video.height)
                elif target_msg.photo: await client.send_photo(user_id, path, caption=caption)
                elif target_msg.document: await client.send_document(user_id, path, caption=caption)
                
                use_right(user_id)
                u = get_user(user_id)
                await status_msg.edit(f"✅ **Tamamlandı!**\n📉 Kalan Hak: **{u['daily_limit'] - u['daily_usage']}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                if os.path.exists(path): os.remove(path)
            else:
                await status_msg.edit("❌ Medya bulunamadı.")

        except Exception as e:
            try: await status_msg.edit(f"❌ Hata: {e}")
            except: pass
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        await asyncio.sleep(2)

# ==================== ⚡ MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 İçerik İndir", callback_data="dl"), InlineKeyboardButton("👤 Hesabım", callback_data="acc")],
        [InlineKeyboardButton("💎 MAĞAZA (Paket Al)", callback_data="shop")],
        [InlineKeyboardButton("❓ Nasıl Kullanılır?", callback_data="howto"), InlineKeyboardButton("👥 Referans", callback_data="ref")],
        [InlineKeyboardButton("👨‍💻 Admin & Bot Hizmetleri", callback_data="service")]
    ])

async def menu_switcher(client, message, text, reply_markup=None):
    try: await message.delete()
    except: pass
    try: await client.send_message(message.chat.id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    except: pass

@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    get_user(user_id)
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if str(ref_id) != str(user_id):
                u = get_user(user_id)
                if u["invited_by"] is None:
                    db_cache["users"][str(user_id)]["invited_by"] = str(ref_id)
                    db_cache["users"][str(user_id)]["daily_limit"] += 3
                    if str(ref_id) in db_cache["users"]:
                        db_cache["users"][str(ref_id)]["daily_limit"] += 2
                        try: await client.send_message(int(ref_id), "🎉 **Referans!** Bugünlük +2 Hak kazandın.")
                        except: pass
        except: pass
    await menu_switcher(client, message, f"👋 **Merhaba {message.from_user.first_name}!**\n\nTelegram'ın en güçlü botuna hoş geldin.\n👇 İşlem Seç:", main_menu())

@bot.on_message(filters.command("giftall") & filters.user(OWNER_ID))
async def gift_all_users(client, message):
    if len(message.command) < 2: return await message.reply("❌ Kullanım: `/giftall 5`")
    amount = int(message.command[1])
    for uid in db_cache["users"]: db_cache["users"][uid]["daily_limit"] += amount
    await save_backup("Hediye")
    await message.reply(f"🎁 Herkese +{amount} hak eklendi.")

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broadcast(client, message):
    if len(message.command) < 2: return await message.reply("❌ Mesaj yaz.")
    text = message.text.split(None, 1)[1]
    msg = await message.reply("📢 Gönderiliyor...")
    c = 0
    for uid in db_cache["users"]:
        try: await client.send_message(int(uid), f"📢 **DUYURU**\n\n{text}"); c+=1; await asyncio.sleep(0.05)
        except: pass
    await msg.edit(f"✅ {c} kişiye ulaştı.")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_link(client, message):
    if "join" in message.text: return
    user_id = message.from_user.id
    allowed, left = check_rights(user_id)
    if not allowed:
        return await message.reply("⛔ **HAKKINIZ BİTTİ!**\n\nPaket almalısınız veya referans kasmalsınız.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Mağaza", callback_data="shop"), InlineKeyboardButton("👥 Referans", callback_data="ref")]]))
    
    prio = 1 if get_user(user_id)["vip_until"] > time.time() else 5
    st = await message.reply(f"⏳ **Sıraya Alındı...**")
    await download_queue.put((prio, (client, st, message.text, user_id)))

# 🛒 CALLBACKS
@bot.on_callback_query()
async def cb_handler(client, callback):
    try: await callback.answer()
    except: pass
    data = callback.data
    uid = callback.from_user.id
    u = get_user(uid)

    if data == "back_home":
        await menu_switcher(client, callback.message, f"👋 **Ana Menü**", main_menu())

    elif data == "howto":
        txt = "❓ **NASIL KULLANILIR?**\n\n1️⃣ Linki kopyala, bota gönder.\n2️⃣ Bot indirip sana göndersin.\n\n🛑 **Erişim Yok Hatası:**\nGrubun **Davet Linkini** bota atın, sonra tekrar deneyin."
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "service":
        txt = f"👨‍💻 **ADMİN & YAZILIM HİZMETLERİ**\n\n✅ Özel Bot Yazılımı\n✅ Toplu Veri Çekme\n✅ Otomasyon\n\n📞 **İletişim:** @{OWNER_USERNAME}"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "shop":
        txt = "💎 **PREMIUM PAKETLER**\n\nHer gece haklarınız yenilenir.\n\n"
        pkgs = ["bronze", "silver", "gold", "elite"]
        btns = []
        for k in pkgs:
            v = PACKAGES[k]
            txt += f"🔸 **{v['name']} ({v['stars']} ⭐)**\n   └ 📅 {v['days']} Gün | 📥 {v['limit']} Hak | 📦 {v['size_mb']} MB\n\n"
            btns.append([InlineKeyboardButton(f"{v['name']} SATIN AL", callback_data=f"buy_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="back_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))

    elif data.startswith("buy_"):
        from pyrogram.types import LabeledPrice
        pkg = data.split("_")[1]
        p = PACKAGES[pkg]
        await client.send_invoice(
            chat_id=uid,
            title=f"{p['name']} PAKET",
            description=f"{p['days']} Gün | {p['limit']} Dosya/Gün",
            payload=pkg,
            currency="XTR", prices=[LabeledPrice(label=p['name'], amount=p['stars'])], provider_token=""
        )

    elif data == "acc":
        days = int((u["vip_until"] - time.time())/86400) if u["vip_until"] > time.time() else 0
        pkg_name = u.get("package", "free")
        size_limit = PACKAGES.get(pkg_name, PACKAGES["free"])["size_mb"]
        txt = f"👤 **HESABIM**\n\n📦 Paket: **{pkg_name.upper()}**\n⏳ Kalan: **{days} Gün**\n📉 Kalan Hak: **{u['daily_limit'] - u['daily_usage']}**\n🛑 Boyut: **{size_limit} MB**"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "ref":
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS**\n\nArkadaşını davet et, günlük **+2 Hak** kazan!\n🔗 `{link}`"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("📤 Paylaş", url=f"https://t.me/share/url?url={link}"), InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

    elif data == "dl":
        await menu_switcher(client, callback.message, "📂 **Link gönder, indireyim.**", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

# ✅ ÖDEME HANDLER (MANUEL)
async def checkout_handler(c, q):
    await q.answer(ok=True)

async def success_handler(c, m):
    pkg = m.successful_payment.invoice_payload
    add_vip(m.from_user.id, pkg)
    await m.reply("🎉 **Ödeme Başarılı!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menü", callback_data="back_home")]]))
    try: await c.send_message(OWNER_ID, f"💰 SATIŞ: {pkg} - {m.from_user.id}")
    except: pass
    await save_backup("Satış")

# ==================== BAŞLATMA ====================
async def main():
    print("🤖 Başlatılıyor...")
    # Handlerları manuel ekliyoruz (Hata çözümü)
    bot.add_handler(PreCheckoutQueryHandler(checkout_handler))
    bot.add_handler(MessageHandler(success_handler, filters.successful_payment))
    
    await bot.start()
    await userbot.start()
    await restore_data()
    asyncio.create_task(backup_loop())
    asyncio.create_task(worker())
    print("✅ V37.0 SAFE LIMITS ACTIVE")
    await idle()
    await save_backup("Kapanış")
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
