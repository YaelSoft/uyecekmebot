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

# 🔥 ÖDEME ONAYI İÇİN HAM VERİ MODÜLLERİ
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

# 🔥🔥🔥 BURAYA BOTUN KULLANICI ADINI YAZ (BAŞINDA @ OLMADAN) 🔥🔥🔥
# Örnek: "YaelSaverBot" (Referans linki buna göre oluşur)
FIXED_BOT_USERNAME = "YaelSaverBot"

# 💰 KREDİ PAKETLERİ (YILDIZ İLE SATIŞ)
PACKAGES = {
    "p100":  {"name": "🥉 100 KREDİ",  "amount": 100,  "price_label": "100 Stars", "price_amount": 100},
    "p250":  {"name": "🥈 250 KREDİ",  "amount": 250,  "price_label": "250 Stars", "price_amount": 250},
    "p500":  {"name": "🥇 500 KREDİ",  "amount": 500,  "price_label": "500 Stars", "price_amount": 500},
    "p1000": {"name": "💎 1000 KREDİ", "amount": 1000, "price_label": "900 Stars", "price_amount": 900}
}

DB_FILE = "users.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelV54")

# ==================== 🌐 WEB SERVER (BOT UYUMASIN DİYE) ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver V54.0 PRO FINAL Active 🟢"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ==================== 🤖 İSTEMCİLER ====================
bot = Client("sales_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("sales_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# ==================== 💾 VERİTABANI YÖNETİMİ ====================
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
        # Log kanalına sessizce yedek atar
        await bot.send_document(
            LOG_CHANNEL, 
            document=DB_FILE, 
            caption=f"💾 **SİSTEM YEDEĞİ**\n📝 Sebep: {reason}\n⏰ {datetime.datetime.now().strftime('%d.%m %H:%M')}\n👥 Kullanıcı: {total_users}"
        )
    except: pass

async def backup_loop():
    while True:
        await asyncio.sleep(3600)
        await save_backup(reason="Saatlik")

# ==================== 🧠 KULLANICI & BAKİYE SİSTEMİ ====================
def get_user(user_id):
    uid = str(user_id)
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "balance": 3,         # 🎁 YENİ GELENE 3 HAK HEDİYE
            "total_spent": 0,
            "invited_by": None
        }
    return db_cache["users"][uid]

def add_credits(user_id, amount):
    uid = str(user_id)
    get_user(uid)
    db_cache["users"][uid]["balance"] += amount
    return db_cache["users"][uid]["balance"]

# ==================== 💳 FATURA KESME (HTTP REQUEST) ====================
# Pyrogram kütüphanesini bypass eder, direkt Telegram sunucusuna emir verir. Hata vermez.
def send_invoice_via_http(chat_id, package_key):
    try:
        pkg = PACKAGES[package_key]
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        payload = {
            "chat_id": chat_id,
            "title": pkg["name"],
            "description": f"{pkg['amount']} Adet İndirme Kredisi (Süresiz)",
            "payload": package_key,
            "provider_token": "", # Stars için boş
            "currency": "XTR",    # Telegram Stars
            "prices": json.dumps([{"label": pkg["name"], "amount": pkg["price_amount"]}])
        }
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Fatura Hatası: {e}")

# ==================== 🏭 İŞÇİ (AKILLI KUYRUK & İNDİRME) ====================
download_queue = asyncio.PriorityQueue()

async def worker():
    print("👷 İşçi Hazır...")
    while True:
        # Priority: Düşük sayı = Yüksek öncelik
        priority, task = await download_queue.get()
        client, status_msg, link, user_id = task
        try:
            # 🛑 1. GÜVENLİK DUVARI: Bakiye Kontrolü
            user_data = get_user(user_id)
            if user_data["balance"] <= 0:
                await status_msg.edit(
                    "⛔ **KREDİNİZ BİTTİ!**\n\nİndirme işlemi iptal edildi. Lütfen kredi yükleyiniz.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Kredi Yükle", callback_data="shop")]])
                )
                continue # İşlemi yapmadan geç

            # Link Analizi
            chat_id, msg_id = None, None
            if "t.me/c/" in link:
                parts = link.split("t.me/c/")[1].split("/")
                chat_id = int("-100" + parts[0]); msg_id = int(parts[1].split("?")[0])
            else:
                parts = link.split("t.me/")[1].split("/"); chat_id = parts[0]; msg_id = int(parts[1].split("?")[0])
            
            target_msg = None
            try: target_msg = await userbot.get_messages(chat_id, msg_id)
            except:
                txt = "🚫 **ERİŞİM YOK!**\n\nBot bu kanalda (gizli kanal) değil.\nLütfen kanalın **Davet Linkini** (t.me/+..) bota atın, bot girsin ve indirsin."
                await status_msg.edit(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                continue
                
            if target_msg and (target_msg.video or target_msg.photo or target_msg.document):
                await status_msg.edit("⬇️ **İndiriliyor...**")
                path = await userbot.download_media(target_msg)
                
                await status_msg.edit("⬆️ **Yükleniyor...**")
                
                # 🔥 PROFESYONEL CAPTION (Botun reklamı)
                caption = f"📥 **İndirildi:** @{FIXED_BOT_USERNAME}\n🔓 **Kısıtlamaları Kaldır!**"
                
                if target_msg.video: await client.send_video(user_id, path, caption=caption, width=target_msg.video.width, height=target_msg.video.height)
                elif target_msg.photo: await client.send_photo(user_id, path, caption=caption)
                elif target_msg.document: await client.send_document(user_id, path, caption=caption)
                
                # 📉 HAKKI DÜŞÜR VE KAYDET
                db_cache["users"][str(user_id)]["balance"] -= 1
                db_cache["users"][str(user_id)]["total_spent"] += 1
                new_bal = db_cache["users"][str(user_id)]["balance"]
                
                await status_msg.edit(f"✅ **İşlem Başarılı!**\n💰 Kalan Kredi: **{new_bal}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menü", callback_data="back_home")]]))
                
                if os.path.exists(path): os.remove(path)
                
                # Sık sık yedekle ki veri kaybı olmasın
                if db_cache["users"][str(user_id)]["total_spent"] % 5 == 0:
                    asyncio.create_task(save_backup("Otomatik Kayıt"))
                    
            else: await status_msg.edit("❌ Medya bulunamadı.")
        except Exception as e:
            try: await status_msg.edit(f"❌ Hata: {e}")
            except: pass
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        await asyncio.sleep(2)

# ==================== ⚡ MENÜ SİSTEMİ (PROFESYONEL) ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 İçerik İndir", callback_data="dl"), InlineKeyboardButton("💰 Cüzdanım", callback_data="acc")],
        [InlineKeyboardButton("🛒 KREDİ MAĞAZASI", callback_data="shop")],
        [InlineKeyboardButton("❓ Nasıl Çalışır?", callback_data="howto"), InlineKeyboardButton("👥 Referans", callback_data="ref")],
        [InlineKeyboardButton("👨‍💻 Admin & Bot Hizmetleri", callback_data="service")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Kredi Yükle", callback_data="admin_add_info"), InlineKeyboardButton("📢 Duyuru Yap", callback_data="admin_cast_info")],
        [InlineKeyboardButton("📊 Genel Durum", callback_data="admin_stats"), InlineKeyboardButton("💾 Yedek Al", callback_data="admin_backup")],
        [InlineKeyboardButton("🔙 Çıkış", callback_data="back_home")]
    ])

# Menü Geçiş Fonksiyonu (Hatasız)
async def menu_switcher(client, message, text, reply_markup=None):
    try: await message.delete()
    except: pass
    try: await client.send_message(message.chat.id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    except: pass

@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    u = get_user(user_id) # İlk girişte 3 hak verir
    
    # Referans Kontrolü
    if len(message.command) > 1:
        try:
            ref_id = message.command[1]
            if str(ref_id) != str(user_id):
                u = get_user(user_id)
                if u["invited_by"] is None:
                    db_cache["users"][str(user_id)]["invited_by"] = str(ref_id)
                    db_cache["users"][str(user_id)]["balance"] += 3 # Yeni gelene +3
                    if str(ref_id) in db_cache["users"]:
                        db_cache["users"][str(ref_id)]["balance"] += 2 # Davet edene +2
                        try: await client.send_message(int(ref_id), "🎉 **Tebrikler!** Referansınla biri kayıt oldu.\n💰 Cüzdanına **+2 Kredi** eklendi.")
                        except: pass
        except: pass
    
    txt = (
        f"👋 **Merhaba {message.from_user.first_name}!**\n\n"
        f"Telegram'ın en hızlı **Özel İçerik İndirme Botuna** hoş geldin.\n\n"
        f"🎁 **Hoşgeldin Hediyesi:** Hesabına 3 Kredi tanımlandı!\n"
        f"👇 **Lütfen yapmak istediğin işlemi seç:**"
    )
    await menu_switcher(client, message, txt, main_menu())

# 👑 ADMIN KOMUTLARI
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_cmd(client, message):
    await menu_switcher(client, message, "👑 **YÖNETİCİ KONTROL PANELİ**\n\nHoşgeldiniz efendim.", admin_menu())

@bot.on_message(filters.command("addcredit") & filters.user(OWNER_ID))
async def manual_add(client, message):
    try:
        parts = message.command
        target = int(parts[1])
        amount = int(parts[2])
        new = add_credits(target, amount)
        await save_backup("Manuel Ekleme")
        await message.reply(f"✅ **Yüklendi!**\n👤 ID: `{target}`\n💰 Eklenen: {amount}\n🏦 Yeni Bakiye: {new}")
        try: await client.send_message(target, f"🎉 **TEBRİKLER!**\n\nHesabınıza **{amount} Kredi** yüklendi.\nKeyifli kullanımlar!")
        except: pass
    except: await message.reply("❌ Hata: `/addcredit ID MİKTAR`")

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def broadcast(client, message):
    if len(message.command) < 2: return await message.reply("❌ Mesaj yazın.")
    text = message.text.split(None, 1)[1]
    msg = await message.reply("📢 **Gönderiliyor...**")
    c = 0
    for uid in db_cache["users"]:
        try: await client.send_message(int(uid), f"📢 **DUYURU**\n\n{text}"); c+=1; await asyncio.sleep(0.05)
        except: pass
    await msg.edit(f"✅ **Tamamlandı!**\n👥 {c} kişiye ulaşıldı.")

# 🔗 LİNK YAKALAYICI
@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_link(client, message):
    if "join" in message.text: return
    user_id = message.from_user.id
    u = get_user(user_id)
    
    # 🛑 1. KONTROL (Burada da kontrol ediyoruz, işçide de)
    if u["balance"] <= 0:
        return await message.reply("⛔ **BAKİYENİZ TÜKENDİ!**\n\nDevam etmek için kredi yüklemelisiniz.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Kredi Yükle", callback_data="shop")]]))
    
    # Öncelik Ayarı (Parası çok olan öne geçer)
    prio = 1 if u["balance"] > 20 else 5
    st = await message.reply(f"⏳ **Sıraya Alındı...**\nLütfen bekleyiniz.")
    await download_queue.put((prio, (client, st, message.text, user_id)))

@bot.on_callback_query()
async def cb_handler(client, callback):
    try: await callback.answer()
    except: pass
    data = callback.data
    uid = callback.from_user.id
    u = get_user(uid)
    
    if data == "back_home": await menu_switcher(client, callback.message, f"👋 **Ana Menü**", main_menu())
    
    # 👑 ADMIN
    elif data == "admin_stats":
        tot = len(db_cache.get("users", {}))
        cre = sum(x["balance"] for x in db_cache["users"].values())
        paid_users = sum(1 for x in db_cache["users"].values() if x["total_spent"] > 5)
        await menu_switcher(client, callback.message, f"📊 **İSTATİSTİKLER**\n\n👥 Toplam Üye: **{tot}**\n💰 Dolaşımdaki Kredi: **{cre}**\n💎 Aktif Müşteri: **{paid_users}**", admin_menu())
    elif data == "admin_backup":
        await save_backup("Manuel")
        await callback.answer("✅ Yedeklendi!", show_alert=True)
    elif data == "admin_add_info": await client.send_message(uid, "ℹ️ `/addcredit ID MİKTAR`")
    elif data == "admin_cast_info": await client.send_message(uid, "ℹ️ `/duyuru MESAJ`")

    # 👤 USER MENÜLERİ
    elif data == "shop":
        txt = "🛒 **KREDİ MARKETİ**\n\nPaketler süresizdir. Sadece kullandıkça düşer.\n**Telegram Stars (Yıldız)** ile anında satın alabilirsiniz.\n\n"
        btns = []
        for k, v in PACKAGES.items():
            txt += f"🔸 **{v['name']}**\n   └ 💸 {v['price_label']}\n\n"
            btns.append([InlineKeyboardButton(f"{v['name']} SATIN AL", callback_data=f"buy_{k}")])
        btns.append([InlineKeyboardButton("🔙 Geri", callback_data="back_home")])
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
        
    elif data.startswith("buy_"):
        pkg = data.split("_")[1]
        send_invoice_via_http(uid, pkg)
        await callback.answer("✅ Fatura oluşturuldu, sohbete bak!", show_alert=True)

    elif data == "acc":
        bal = u['balance']
        tot = u.get('total_spent', 0)
        txt = f"💰 **CÜZDANIM**\n\n💳 Mevcut Kredi: **{bal}**\n📉 Toplam Harcanan: **{tot}**\n♾️ Krediler süresizdir."
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
        
    elif data == "howto":
        txt = "❓ **NASIL KULLANILIR?**\n\n1️⃣ İçerik linkini kopyalayın.\n2️⃣ Bu bota gönderin.\n3️⃣ Bot indirip size göndersin.\n\n⚠️ **HATA ALIRSANIZ:**\nBot 'Erişim Yok' derse, o kanalın davet linkini bota atın."
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
        
    elif data == "service":
        txt = f"👨‍💻 **ADMİN & HİZMETLER**\n\nBu botun yazılımı ve yönetimi @{OWNER_USERNAME} aittir.\nBenzer projeler için ulaşabilirsiniz."
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))
        
    # 🔥 DÜZELTİLEN REFERANS SİSTEMİ 🔥
    elif data == "ref":
        # Botun kullanıcı adını kullanarak link oluştur
        link = f"https://t.me/{FIXED_BOT_USERNAME}?start={uid}"
        txt = f"👥 **REFERANS SİSTEMİ**\n\nArkadaşını davet et, **+2 Kredi** kazan!\n\n🔗 **Davet Linkin:**\n`{link}`"
        
        btns = [
            [InlineKeyboardButton("📤 Linki Paylaş", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton("🔙 Geri", callback_data="back_home")]
        ]
        await menu_switcher(client, callback.message, txt, InlineKeyboardMarkup(btns))
        
    elif data == "dl": await menu_switcher(client, callback.message, "📂 **İndirme Modu**\n\nLütfen indirmek istediğiniz linki yapıştırın.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="back_home")]]))

# 🔥 ÖDEME ONAYI (HAM VERİ - HATASIZ)
@bot.on_raw_update()
async def raw_payment_handler(client, update, users, chats):
    if isinstance(update, UpdateBotPrecheckoutQuery):
        try: await client.invoke(SetBotPrecheckoutResults(query_id=update.query_id, success=True, error=None))
        except: pass

# 🔥 EL YAPIMI FİLTRE
def is_successful_payment(_, __, message): return bool(message.successful_payment)
payment_filter = filters.create(is_successful_payment)

@bot.on_message(payment_filter)
async def success_pay(c, m):
    pkg_key = m.successful_payment.invoice_payload
    pkg = PACKAGES.get(pkg_key)
    if pkg:
        amount = pkg["amount"]
        add_credits(m.from_user.id, amount)
        await m.reply(f"🎉 **ÖDEME BAŞARILI!**\n\nHesabınıza **{amount} Kredi** eklendi.\nTeşekkürler!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Cüzdanım", callback_data="acc")]]))
        try: await c.send_message(OWNER_ID, f"💰 **SATIŞ:** {pkg['name']} - {m.from_user.first_name}")
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
    print("✅ V54.0 GRAND FINAL ACTIVE")
    await idle()
    await save_backup("Kapanış")
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    Thread(target=run_web).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
