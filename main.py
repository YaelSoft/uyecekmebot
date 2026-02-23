import os, json, time, asyncio, logging, datetime, requests, re, gc
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageEmpty, PeerIdInvalid

# ==================== ⚙️ AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
SESSION_STRING_2 = os.environ.get("SESSION_STRING_2", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "yasin33")
FIXED_BOT_USERNAME = "YaelSaverBot"
DB_FILE = "users.json"
MAX_FILE_SIZE = 400 * 1024 * 1024 

db_cache = {"users": {}, "config": {}}
download_queue = asyncio.PriorityQueue()

# ==================== 🧠 SİSTEM FONKSİYONLARI ====================
def get_user(user_id, first_name=None):
    uid = str(user_id)
    today = datetime.date.today().isoformat()
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {
            "sub_type": "none", "sub_expiry": 0, "lang": "tr", 
            "first_name": first_name or "User", "daily_transfer": 0, "last_reset": today
        }
    u = db_cache["users"][uid]
    if u.get("last_reset") != today:
        u["daily_transfer"] = 0
        u["last_reset"] = today
    return u

def is_vip(user_id):
    if user_id == OWNER_ID: return True
    u = get_user(user_id)
    return u["sub_type"] == "vip_unlimited" or (u["sub_type"] == "vip_month" and time.time() < u["sub_expiry"])

# ==================== 🤖 İSTEMCİLER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "🟢 YaelSaver V2.0 Premium Online"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

bot = Client("bot", API_ID, API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("ubot1", API_ID, API_HASH, session_string=SESSION_STRING, in_memory=True)
userbot2 = Client("ubot2", API_ID, API_HASH, session_string=SESSION_STRING_2, in_memory=True) if SESSION_STRING_2 else userbot

# ==================== 👷 İŞÇİ (AKILLI İNDİRME & YEDEKLEME) ====================
async def worker():
    while True:
        _, task = await download_queue.get()
        client, status_msg, link, user_id = task
        try:
            # Link Ayrıştırma
            clean_link = link.replace("https://t.me/", "").replace("http://t.me/", "").split("?")[0]
            parts = clean_link.split("/")
            if parts[0] == "c": chat_id, msg_id = int("-100" + parts[1]), int(parts[2])
            else: chat_id, msg_id = parts[0], int(parts[1])

            target_msg = await userbot.get_messages(chat_id, msg_id)
            if not target_msg or target_msg.empty:
                await status_msg.edit("❌ Mesaj bulunamadı.")
                continue

            chat_info = await userbot.get_chat(chat_id)
            is_restricted = chat_info.has_protected_content
            caption = f"📥 @{FIXED_BOT_USERNAME} | Premium Arşiv"

            if not is_restricted:
                # Kısıtlama Yoksa Direkt Kopyala
                await status_msg.edit("⬇️ Medya iletiliyor...")
                sent = await target_msg.copy(user_id, caption=caption)
                try: await sent.copy(LOG_CHANNEL)
                except: pass
                await status_msg.edit("✅ İşlem başarıyla tamamlandı.")
            else:
                # Kısıtlama Varsa İndir Yükle Sil
                media = target_msg.video or target_msg.photo or target_msg.document or target_msg.audio or target_msg.animation
                if media and getattr(media, 'file_size', 0) > MAX_FILE_SIZE:
                    await status_msg.edit("⚠️ 400 MB sınırı aşıldı!")
                    continue

                await status_msg.edit("⬇️ Kısıtlamalı içerik indiriliyor...")
                path = await userbot.download_media(target_msg)
                await status_msg.edit("⬆️ İçerik size yükleniyor...")
                sent = await client.send_document(user_id, path, caption=f"{caption}\n🔓 Kısıtlama Kaldırıldı")
                try: await sent.copy(LOG_CHANNEL)
                except: pass
                if os.path.exists(path): os.remove(path)
                await status_msg.edit("✅ Kısıtlama aşıldı ve yedeklendi.")
        except Exception as e:
            await status_msg.edit(f"❌ Hata: {str(e)}")
        await asyncio.sleep(2)

# ==================== 📸 HİKAYE & ADMIN & MENÜ ====================
async def story_downloader(m, story_link):
    try:
        parts = story_link.split('/')
        username, story_id = parts[-3], int(parts[-1])
        status = await m.reply("📸 Hikaye yakalanıyor...")
        story = await userbot.get_stories(username, story_id)
        path = await userbot.download_media(story)
        sent = await bot.send_document(m.chat.id, path, caption=f"📸 @{username} Story\n📥 @{FIXED_BOT_USERNAME}")
        try: await sent.copy(LOG_CHANNEL)
        except: pass
        if os.path.exists(path): os.remove(path)
        await status.delete()
    except Exception as e: await m.reply(f"❌ Hikaye hatası: {str(e)}")

def get_main_menu(uid):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 TEKLİ MEDYA", callback_data="m_single"), InlineKeyboardButton("🚚 TOPLU TRANSFER", callback_data="m_mass")],
        [InlineKeyboardButton("📸 HİKAYE İNDİR", callback_data="m_story"), InlineKeyboardButton("⭐ YILDIZLI İÇERİK", callback_data="m_stars")],
        [InlineKeyboardButton("👑 ADMIN PANEL", callback_data="adm_home") if uid == OWNER_ID else InlineKeyboardButton("🆘 DESTEK", url=f"https://t.me/{OWNER_USERNAME}")]
    ])
    return "🚀 **Yael Saver Premium V2.0**\n\nLütfen işlem seçin:", btn

@bot.on_message(filters.command("start"))
async def start(c, m):
    uid = m.from_user.id
    get_user(uid, m.from_user.first_name)
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🇹🇷 TÜRKÇE", callback_data="set_tr"), InlineKeyboardButton("🇺🇸 ENGLISH", callback_data="set_en")]])
    await m.reply("🌐 Dil seçiniz / Choose language:", reply_markup=btn)

@bot.on_callback_query()
async def cb_handler(c, cb):
    # 1. KRİTİK: Telegram'a "tıklama alındı" cevabı gönder (Butonun dönmesini durdurur)
    try:
        await cb.answer()
    except:
        pass

    uid = cb.from_user.id
    data = cb.data
    u = get_user(uid)
    lang = u.get("lang", "tr")

    # 2. VIP KONTROLÜ (Admin hariç herkese bariyer)
    # Eğer kullanıcı VIP değilse ve işlemlere basıyorsa (m_ ile başlayanlar)
    if not is_vip(uid) and data.startswith("m_"):
        await cb.message.reply(
            "⚠️ **Yael Saver Artık VIP Sistemindedir.**\n\n"
            "Ücretsiz sürüm kaldırılmıştır. Yeni özellikler (Story, Toplu Transfer) eklenmiştir.\n"
            "Devam etmek için lütfen @yasin33 ile iletişime geçin."
        )
        return

    # 3. BUTON YÖNLENDİRMELERİ
    if data.startswith("set_"):
        u["lang"] = data.split("_")[1]
        txt, btn = get_main_menu(uid)
        await cb.message.edit(txt, reply_markup=btn)
    
    elif data == "m_single":
        await cb.message.reply("🔗 **İndirmek istediğiniz medyanın linkini gönderin.**")
        
    elif data == "m_mass":
        await cb.message.reply("🚚 **Toplu transfer için komutu kullanın:**\n`/transfer @kanaladi` ")
        
    elif data == "m_story":
        await cb.message.reply("📸 **İndirmek istediğiniz hikaye (story) linkini gönderin.**")
        
    elif data == "m_stars":
        await cb.message.reply(f"⭐ **Yıldızlı içerik kaydı için lütfen adminle görüşün:** @{OWNER_USERNAME}")

    elif data == "adm_home" and uid == OWNER_ID:
        # Admin paneli butonları
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 DUYURU YAP", callback_data="adm_cast")],
            [InlineKeyboardButton("➕ VIP EKLE", callback_data="adm_addvip"), InlineKeyboardButton("➖ VIP SİL", callback_data="adm_delvip")],
            [InlineKeyboardButton("💾 YEDEK AL", callback_data="adm_backup")]
        ])
        await cb.message.edit("👑 **ADMIN KOMUTA MERKEZİ**", reply_markup=btn)

    elif data == "adm_backup" and uid == OWNER_ID:
        with open(DB_FILE, "w") as f: json.dump(db_cache, f)
        await bot.send_document(uid, DB_FILE, caption="💾 Güncel Veritabanı Yedeği")

# ==================== 🛠️ KOMUTLAR ====================
@bot.on_message(filters.command("vip_ekle") & filters.user(OWNER_ID))
async def ve(c, m):
    try:
        uid, days = m.command[1], m.command[2]
        u = get_user(uid)
        u["sub_type"] = "vip_month"
        u["sub_expiry"] = time.time() + (int(days) * 86400)
        await m.reply(f"✅ {uid} -> {days} gün VIP."); await save_db()
    except: pass

@bot.on_message(filters.command("vip_sil") & filters.user(OWNER_ID))
async def vs(c, m):
    try:
        db_cache["users"][str(m.command[1])]["sub_type"] = "none"
        await m.reply(f"❌ {m.command[1]} VIP silindi."); await save_db()
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def dy(c, m):
    txt = m.text.split(None, 1)[1]
    for uid in db_cache["users"]:
        try: await c.send_message(int(uid), f"📢 **GÜNCELLEME:**\n\n{txt}"); await asyncio.sleep(0.1)
        except: pass

@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl_handler(c, m):
    uid = m.from_user.id
    if not is_vip(uid): return await m.reply("⚠️ Yael Saver artık VIP sistemindedir. İletişim: @yasin33")
    if "/s/" in m.text: await story_downloader(m, m.text)
    else:
        st = await m.reply("⏳ İşlem sıraya alındı...")
        await download_queue.put((1, (c, st, m.text, uid)))

@bot.on_message(filters.command("transfer") & filters.private)
async def trans_handler(c, m):
    uid = m.from_user.id
    if not is_vip(uid): return
    try:
        source, u = m.command[1], get_user(uid)
        if u["daily_transfer"] >= 100: return await m.reply("❌ Limit doldu.")
        status = await m.reply("🚚 Transfer başladı...")
        done = 0
        async for msg in userbot2.get_chat_history(source, limit=100):
            try:
                await msg.copy(LOG_CHANNEL); done += 1; u["daily_transfer"] += 1
                if done % 10 == 0: await status.edit(f"🚚 {done}/100")
                await asyncio.sleep(3)
            except: continue
        await status.edit(f"✅ {done} yedeklendi.")
    except: pass

async def save_db():
    with open(DB_FILE, "w") as f: json.dump(db_cache, f)

async def main():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: global db_cache; db_cache = json.load(f)
    await bot.start(); await userbot.start()
    if SESSION_STRING_2: await userbot2.start()
    asyncio.create_task(worker()); print("🚀 V2.0 ACTIVE"); await idle()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.get_event_loop().run_until_complete(main())

