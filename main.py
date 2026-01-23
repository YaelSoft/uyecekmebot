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
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# 💰 KREDİ PAKETLERİ (SÜRESİZ HAK)
PACKAGES = {
    "p100":  {"name": "🥉 100 KREDİ",  "amount": 100,  "price_label": "100 Stars", "price_amount": 100},
    "p250":  {"name": "🥈 250 KREDİ",  "amount": 250,  "price_label": "250 Stars", "price_amount": 250},
    "p500":  {"name": "🥇 500 KREDİ",  "amount": 500,  "price_label": "500 Stars", "price_amount": 500},
    "p1000": {"name": "💎 1000 KREDİ", "amount": 1000, "price_label": "900 Stars", "price_amount": 900}
}

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV50")

# ==================== 🌐 WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V50.0 GIFT MODE Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI ====================
db_cache = {"users": {}}

async def restore_data():
    global db_cache
    if LOG_CHANNEL == 0: return
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

# ==================== 🧠 KULLANICI MANTIĞI ====================
def get_user(user_id):
    uid = str(user_id)
    # EĞER KULLANICI İLK KEZ GELİYORSA -> 3 HAK HEDİYE ET
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "balance": 3,         # 🎁 YENİ GELENE 3 HAK
            "total_spent": 0,
            "invited_by": None
        }
    return db_cache["users"][uid]

def check_rights(user_id):
    if user_id == OWNER_ID: return True, "Patron"
    u = get_user(user_id)
    if u["balance"] > 0: return True, u["balance"]
    return False, 0

def use_right(user_id):
    if user_id == OWNER_ID: return
    uid = str(user_id)
    if db_cache["users"][uid]["balance"] > 0:
        db_cache["users"][uid]["balance"] -= 1
        db_cache["users"][uid]["total_spent"] += 1

def add_credits(user_id, amount):
    uid = str(user_id)
    get_user(uid)
    db_cache["users"][uid]["balance"] += amount
    return db_cache["users"][uid]["balance"]

# ==================== 💳 FATURA (HTTP) ====================
def send_invoice_via_http(chat_id, package_key):
    try:
        pkg = PACKAGES[package_key]
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        payload = {
            "chat_id": chat_id,
            "title": pkg["name"],
            "description": f"{pkg['amount']} Adet İndirme Kredisi (Süresiz)",
            "payload": package_key,
            "provider_token": "", 
            "currency": "XTR",
            "prices": json.dumps([{"label": pkg["name"], "amount": pkg["price_amount"]}])
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
            chat_id, msg_id = None, None
            if "t.me/c/" in link:
                parts = link.split("t.me/c/")[1].split("/")
                chat_id = int("-100" + parts[0]); msg_id = int(parts[1].split("?")[0])
            else:
                parts = link.split("t.me/")[1].split("/"); chat_id = parts[0]; msg_id = int(parts[1].split("?")[0])
            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                txt = "🚫 **ERİŞİM SAĞLANAMADI**\n\nBot bu kanalda yok. Lütfen **Davet Linkini** atın."
                await status_msg.edit(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                continue
                
            if target_msg and (target_msg.video or target_msg.photo or target_msg.document):
                file_size = 0
                if target_msg.video: file_size = target_msg.video.file_size
                elif target_msg.document: file_size = target_msg.document.file_size
                elif target_msg.photo: file_size = 1024
                
                if file_size > 2000 * 1024 * 1024:
                    await status_msg.edit(f"🛑 **DOSYA ÇOK BÜYÜK!**\nMax 2GB indirebilirsiniz.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
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
                await status_msg.edit(f"✅ **İşlem Başarılı!**\n💰 Kalan Kredi: **{u['balance']}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                if os.path.exists(path): os.remove(path)
            else: await status_msg.edit("❌ Medya bulunamadı.")
        except Exception as e:
            try: await status_msg.edit(f"❌ Hata: {e}")
            except: pass
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        await asyncio.sleep(2)

# ==================== ⚡ MENÜLER ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 İçerik İndir", callback_data="dl"), InlineKeyboardButton("💰 Cüzdanım", callback_data="acc")],
        [InlineKeyboardButton("🛒 KREDİ YÜKLE", callback_data="shop")],
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
    # get_user zaten yeni gelene 3 hak veriyor
    u = get_user(user_id)
    
    # Referans
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
                        try: await client.send_message(int(ref_id), "🎉 **Referans!** Cüzdanına +2 Kredi eklendi.")
                        except: pass
        except: pass
    await menu_switcher(client, message, f"👋 **Merhaba {message.from_user.first_name}!**\n\nTelegram'ın en hızlı içerik indirme botuna hoş geldin.\n🎁 **Hoşgeldin hediyesi olarak 3 Kredin tanımlandı!**\n\n👇 **İşleminizi Seçiniz:**", main_menu())

# 🔥🔥🔥 GÜNCELLEME VE HEDİYE KOMUTU (TEK SEFERLİK ÇALIŞTIR) 🔥🔥🔥
@bot.on_message(filters.command("update_bonus") & filters.user(OWNER_ID))
async def update_bonus_gift(client, message):
    await message.reply("🚀 **Güncelleme Dağıtımı Başlıyor...**")
    c = 0
    txt = (
        "🚀 **SİSTEM GÜNCELLEMESİ TAMAMLANDI!**\n\n"
        "Değerli Kullanıcımız,\n"
        "✅ Ödeme sistemi yenilendi.\n"
        "✅ İndirme sorunları giderildi.\n"
        "✅ Bot artık daha hızlı!\n\n"
        "🎁 **TELAFİ HEDİYESİ:**\n"
        "Yaşanan aksaklıklar nedeniyle hesabınıza **+3 KREDİ** tanımlanmıştır.\n\n"
        "İyi kullanımlar dileriz! 🌹"
    )
    
    for uid in db_cache["users"]:
        try:
            db_cache["users"][uid]["balance"] += 3 # Herkese +3 Ekle
            await client.send_message(int(uid), txt)
            c += 1
            await asyncio.sleep(0.05) # Spam olmasın diye minik bekleme
        except: pass
    
    await save_backup("Update Bonus")
    await message.reply(f"✅ **Dağıtım Bitti!**\n🎁 {c} kişiye hediye ve mesaj gönderildi.")

@bot.on_message(filters.command("addcredit") & filters.user(OWNER_ID))
async def manual_credit_add(client, message):
    try:
        parts = message.command
        target_id = int(parts[1])
        amount = int(parts[2])
        new_bal = add_credits(target_id, amount)
        await save_backup("Manuel Kredi")
        await message.reply(f"✅ **Yüklendi!**\n🆔 `{target_id}`\n💰 +{amount} Kredi")
        try: await client.send_message(target_id, f"🎉 **KREDİ YÜKLENDİ!**\n\nHesabınıza **{amount} Kredi** eklendi.\nKeyifli indirmeler!")
        except: pass
    except: await message.reply("❌ Hata: `/addcredit ID MİKTAR`")

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_link(client, message):
    if "join" in message.text: return
    user_id = message.from_user.id
    allowed, left = check_rights(user_id)
    if not allowed:
        return await message.reply("⛔ **BAKİYENİZ YETERSİZ!**\n\nİndirme yapmak için kredi yüklemeniz gerekmektedir.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Kredi Yükle", callback_data="shop")]]))
    
    st = await message.reply(f"⏳ **Sıraya Alındı...**")
    await download_queue.put((1, (client, st, message.text, user_id)))

@bot.on_callback_query()
async def cb_handler(client, callback):
    try: await callback.answer()
    except: pass
    data = callback.data
    uid = callback.from_user.id
    u = get_user(uid)
    
    if data == "back_home": await menu_switcher(client, callback.message, f"👋 **Ana Menü**", main_menu())
    
    elif data == "howto": await menu_switcher(client, callback.message, "❓ **NASIL KULLANILIR?**\n\n1️⃣ Linki kopyala, bota gönder.\n2️⃣ Bot indirip sana göndersin.\n\n🛑 **Erişim Yok Hatası:**\nGrubun **Davet Linkini** bota atın.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    elif data == "service": await menu_switcher(client, callback.message, f"👨‍💻 **ADMİN & YAZILIM HİZMETLERİ**\n\n📞 **İletişim:** @{OWNER_USERNAME}", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    
    elif data == "shop":
        txt = "🛒 **KREDİ MARKETİ**\n\nPaketler süresizdir. Sadece kullandıkça düşer.\n**Telegram Stars (Yıldız)** ile anında satın alabilirsiniz.\n\n"
        btns = []
        for k, v in PACKAGES.items():
            txt += f"🔸 **{v['name']}**\n   └ 💸 Fiyat: {v['price_label']}\n\n"
            btns.append([InlineKeyboardButton(f"{v['name']} SATIN AL", callback_data=f"buy_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="back_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))

    elif data.startswith("buy_"):
        pkg_key = data.split("_")[1]
        send_invoice_via_http(uid, pkg_key)
        await callback.answer("✅ Fatura oluşturuldu, sohbete bak!", show_alert=True)

    elif data == "acc":
        bal = u['balance']
        spent = u.get('total_spent', 0)
        txt = f"💰 **CÜZDANIM**\n\n💳 Mevcut Kredi: **{bal}**\n📉 Harcanan: **{spent}**\n♾️ Krediler süresizdir."
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    elif data == "ref":
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS**\n\nArkadaşını davet et, **+2 Kredi** kazan!\n🔗 `{link}`"
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("📤 Paylaş", url=f"https://t.me/share/url?url={link}"), InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
    elif data == "dl": await menu_switcher(client, callback.message, "📂 **İndirme Modu**\n\nLink gönderebilirsiniz.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

# 🔥 ÖDEME ONAYI (HAM VERİ)
@bot.on_raw_update()
async def raw_payment_handler(client, update, users, chats):
    if isinstance(update, UpdateBotPrecheckoutQuery):
        try:
            await client.invoke(SetBotPrecheckoutResults(query_id=update.query_id, success=True, error=None))
        except: pass

@bot.on_message(filters.successful_payment)
async def success_pay(c, m):
    pkg_key = m.successful_payment.invoice_payload
    pkg = PACKAGES.get(pkg_key)
    if pkg:
        amount = pkg["amount"]
        add_credits(m.from_user.id, amount)
        await m.reply(f"🎉 **Ödeme Başarılı!**\n\nhesabınıza **{amount} Kredi** eklendi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Cüzdanım", callback_data="acc")]]))
        try: await c.send_message(OWNER_ID, f"💰 SATIŞ: {pkg['name']} - {m.from_user.first_name}")
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
    print("✅ V50.0 GIFT MODE ACTIVE")
    await idle()
    await save_backup("Kapanış")
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
