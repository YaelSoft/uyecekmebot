import os, json, time, asyncio, logging, datetime, requests, re, gc
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

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

# ==================== 🧠 SİSTEM FONKSİYONLARI ====================
def get_user(user_id, first_name=None):
    uid = str(user_id)
    if uid not in db_cache["users"]:
        db_cache["users"][uid] = {"sub_type": "none", "sub_expiry": 0, "lang": "tr", "first_name": first_name or "User"}
    return db_cache["users"][uid]

def is_vip(user_id):
    if user_id == OWNER_ID: return True
    u = get_user(user_id)
    if u["sub_type"] == "vip_unlimited": return True
    if u["sub_type"] == "vip_month" and time.time() < u["sub_expiry"]: return True
    return False

# ==================== 🤖 İSTEMCİLER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "🟢 YaelSaver V2.0 Premium Active"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

bot = Client("bot", API_ID, API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("ubot1", API_ID, API_HASH, session_string=SESSION_STRING, in_memory=True)
userbot2 = Client("ubot2", API_ID, API_HASH, session_string=SESSION_STRING_2, in_memory=True) if SESSION_STRING_2 else userbot

# ==================== 👑 ADMIN PANELİ (SADECE SANA ÖZEL) ====================
@bot.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(c, m):
    u_count = len(db_cache["users"])
    v_count = sum(1 for u in db_cache["users"].values() if u.get("sub_type") != "none")
    txt = f"👑 **YAELSOFT YÖNETİM MERKEZİ**\n\n👥 Üye: `{u_count}`\n💎 VIP: `{v_count}`"
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 DUYURU YAP", callback_data="adm_cast")],
        [InlineKeyboardButton("➕ VIP EKLE", callback_data="adm_addvip"), InlineKeyboardButton("➖ VIP SİL", callback_data="adm_delvip")],
        [InlineKeyboardButton("💾 YEDEK YÜKLE", callback_data="adm_restore"), InlineKeyboardButton("🗑️ YEDEK SİL", callback_data="adm_cleardb")],
        [InlineKeyboardButton("❌ PANELİ KAPAT", callback_data="close_admin")]
    ])
    await m.reply(txt, reply_markup=btn)

# ==================== 🎭 PROFESYONEL MENÜ SİSTEMİ ====================
def get_main_menu(uid):
    u = get_user(uid)
    lang = u.get("lang", "tr")
    txt = "🚀 **Yael Saver Premium V2.0**\n\nLütfen yapmak istediğiniz işlemi seçin:" if lang == "tr" else "🚀 **Yael Saver Premium V2.0**\n\nPlease select an action:"
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 TEKLİ MEDYA İNDİR", callback_data="m_single"), InlineKeyboardButton("🚚 TOPLU TRANSFER", callback_data="m_mass")],
        [InlineKeyboardButton("📸 HİKAYE İNDİR", callback_data="m_story"), InlineKeyboardButton("⭐ YILDIZLI İÇERİK", callback_data="m_stars")],
        [InlineKeyboardButton("👤 PROFİLİM", callback_data="m_profile"), InlineKeyboardButton("🆘 DESTEK", url=f"https://t.me/{OWNER_USERNAME}")]
    ])
    return txt, btn

@bot.on_message(filters.command("start"))
async def start(c, m):
    uid = m.from_user.id
    get_user(uid, m.from_user.first_name)
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🇹🇷 TÜRKÇE", callback_data="set_tr"), InlineKeyboardButton("🇺🇸 ENGLISH", callback_data="set_en")]])
    await m.reply("🌐 Dil seçiniz / Choose language:", reply_markup=btn)

@bot.on_callback_query()
async def cb_handler(c, cb):
    uid = cb.from_user.id
    data = cb.data
    u = get_user(uid)
    
    # Dil Seçimi
    if data.startswith("set_"):
        u["lang"] = data.split("_")[1]
        txt, btn = get_main_menu(uid)
        await cb.message.edit(txt, reply_markup=btn)
        return

    # VIP Bariyeri (Admin Komutları Hariç)
    if not is_vip(uid) and data.startswith("m_"):
        await cb.answer("⚠️ Yael Saver artık VIP olmuştur. Ücretsiz versiyon kaldırılmıştır. İletişim: @yasin33", show_alert=True)
        return

    # Menü İşlemleri
    if data == "m_stars":
        await cb.message.reply(f"⭐ Yıldızlı içerikleri kaydetmek için lütfen admin ile iletişime geçin: @{OWNER_USERNAME}")
    elif data == "m_single":
        await cb.message.reply("🔗 Lütfen indirmek istediğiniz medyanın linkini gönderin.")
    elif data == "m_mass":
        await cb.message.reply("🚚 Toplu transfer için kaynak kanalı belirtin: `/transfer @kanaladi` ")
    elif data == "m_story":
        await cb.message.reply("📸 Hikaye linkini gönderin (Örn: t.me/user/s/1)")
    
    # Admin Callbackleri
    elif data == "adm_cast": await cb.message.reply("📢 Duyuru için: `/duyuru MESAJ` ")
    elif data == "adm_addvip": await cb.message.reply("➕ VIP ekle: `/vip_ekle ID GÜN` ")
    elif data == "adm_delvip": await cb.message.reply("➖ VIP sil: `/vip_sil ID` ")
    elif data == "adm_cleardb":
        db_cache["users"] = {}
        await cb.answer("Veritabanı sıfırlandı!", show_alert=True)
    elif data == "close_admin": await cb.message.delete()

# ==================== 🛠️ YÖNETİM KOMUTLARI ====================

@bot.on_message(filters.command("vip_ekle") & filters.user(OWNER_ID))
async def ve(c, m):
    try:
        uid, days = m.command[1], m.command[2]
        u = get_user(uid)
        u["sub_type"] = "vip_month"
        u["sub_expiry"] = time.time() + (int(days) * 86400)
        await m.reply(f"✅ {uid} için {days} gün VIP tanımlandı.")
    except: pass

@bot.on_message(filters.command("vip_sil") & filters.user(OWNER_ID))
async def vs(c, m):
    try:
        uid = m.command[1]
        db_cache["users"][str(uid)]["sub_type"] = "none"
        await m.reply(f"❌ {uid} VIP yetkisi alındı.")
    except: pass

@bot.on_message(filters.command("duyuru") & filters.user(OWNER_ID))
async def dy(c, m):
    txt = m.text.split(None, 1)[1]
    for user_id in db_cache["users"]:
        try:
            await c.send_message(int(user_id), f"📢 **GÜNCELLEME:**\n\n{txt}")
            await asyncio.sleep(0.1)
        except: pass

# ==================== 📥 İNDİRME & YEDEKLEME (LOG) ====================
@bot.on_message(filters.regex(r"https://t.me/") & filters.private)
async def dl(c, m):
    uid = m.from_user.id
    if not is_vip(uid):
        return await m.reply("⚠️ Yael Saver VIP olmuştur. Ücretsiz sürüm kapalıdır. İletişim: @yasin33")
    
    status = await m.reply("⏳ İşlem başlatıldı...")
    try:
        # Link ayrıştırma ve indirme mantığı...
        # ... (Önceki işçi fonksiyonun burada çalışacak) ...
        # Her başarılı indirmede:
        # await m.copy(LOG_CHANNEL) -> LOG kanalına mutlaka yedek atar.
        pass
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== 🚀 BAŞLATMA ====================
async def main():
    await bot.start()
    await userbot.start()
    if SESSION_STRING_2: await userbot2.start()
    print("🚀 YaelSaver V2.0 IMPERIAL MODE ACTIVE")
    await idle()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.get_event_loop().run_until_complete(main())
