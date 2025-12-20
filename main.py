import os
import logging
import json
import re
import asyncio
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

# Telegram Kütüphaneleri
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.error import TelegramError, BadRequest, Forbidden

# ==================== WEB SERVER (RENDER İÇİN ŞART) ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Çalışıyor! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ==================== AYARLAR ====================
# Render Environment Variables kısmından çekilecek
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7839067076:AAHgC6C-mzQegzVVHLmkVH08vu-jkTBaQlI")
ADMIN_ID_RAW = os.environ.get("ADMIN_ID", "7292548110")
ADMIN_IDS = [int(x) for x in ADMIN_ID_RAW.split(",")] if ADMIN_ID_RAW else []

# Hız ve Limit Ayarları
SPEED_DELAYS = {"trial": 8.0, "vip": 3.0, "admin": 0.5}
DAILY_LIMITS = {"trial": 100, "vip": 500, "admin": 99999}

USER_DATA_FILE = "bot_users.json"

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== VERİTABANI YÖNETİMİ ====================
class UserDatabase:
    def __init__(self):
        self.users = self.load_data()
    
    def load_data(self):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_data(self):
        try:
            with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Kayıt hatası: {e}")

    def get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "status": "trial", "vip_until": None,
                "daily_downloads": 0, "last_date": datetime.now().strftime("%Y-%m-%d"),
                "total": 0, "transfer_mode": False,
                "transfer_target": None, "transfer_list": []
            }
            self.save_data()
        return self.users[uid]

    def update_user(self, user_id, data):
        uid = str(user_id)
        if uid in self.users:
            self.users[uid].update(data)
            self.save_data()

db = UserDatabase()

# ==================== YARDIMCI FONKSİYONLAR ====================
def get_status(user_id):
    if user_id in ADMIN_IDS: return "admin"
    user = db.get_user(user_id)
    # VIP süresi kontrolü
    if user["status"] == "vip" and user["vip_until"]:
        try:
            if datetime.now() > datetime.fromisoformat(user["vip_until"]):
                db.update_user(user_id, {"status": "trial", "vip_until": None})
                return "trial"
        except: pass
    return user["status"]

def check_limit(user_id):
    user = db.get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Gün sıfırlama
    if user["last_date"] != today:
        db.update_user(user_id, {"daily_downloads": 0, "last_date": today})
        user["daily_downloads"] = 0
    
    limit = DAILY_LIMITS[get_status(user_id)]
    return user["daily_downloads"] < limit, limit - user["daily_downloads"]

def parse_link(link):
    # Regex ile link analizi (Public ve Private kanallar)
    patterns = [
        r'(?:t\.me/c/(\d+)/(\d+))',      # Private: t.me/c/12345/67
        r'(?:t\.me/([^/]+)/(\d+))'       # Public: t.me/kanal/67
    ]
    for p in patterns:
        match = re.search(p, link)
        if match:
            chat, msg_id = match.groups()
            # Private kanal ID düzeltmesi (-100 ekle)
            if chat.isdigit(): chat = f"-100{chat}"
            else: chat = f"@{chat}"
            return chat, int(msg_id)
    return None, None

# ==================== BOT KOMUTLARI ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = get_status(user.id)
    limit = DAILY_LIMITS[status]
    
    txt = (
        f"👋 **Merhaba {user.first_name}!**\n\n"
        f"Ben **Gelişmiş İçerik İndirme Botuyum**.\n"
        f"Telegram kanallarından içerikleri kopyalayabilirim.\n\n"
        f"👤 **Üyelik:** `{status.upper()}`\n"
        f"📊 **Günlük Limit:** `{limit}` mesaj\n\n"
        f"🔻 **Nasıl Kullanılır?**\n"
        f"1. Bana bir mesaj linki gönder.\n"
        f"2. Veya `/transfer` komutu ile toplu taşıma yap.\n\n"
        f"⚠️ _Not: Botun içerik alacağı kanalda bulunması gerekir._"
    )
    
    buttons = [
        [InlineKeyboardButton("📦 Transfer Modu", callback_data="help_transfer")],
        [InlineKeyboardButton("💎 VIP Bilgi", callback_data="help_vip")]
    ]
    
    if user.id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("👑 Admin Paneli", callback_data="admin_panel")])

    await update.message.reply_html(txt, reply_markup=InlineKeyboardMarkup(buttons))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text
    user_data = db.get_user(user_id)
    
    # Transfer modu açıksa listeye ekle
    if user_data["transfer_mode"]:
        links = msg.strip().split()
        added = 0
        for link in links:
            c, m = parse_link(link)
            if c and m:
                user_data["transfer_list"].append({"chat": c, "id": m})
                added += 1
        
        db.update_user(user_id, {"transfer_list": user_data["transfer_list"]})
        await update.message.reply_text(f"✅ {added} link listeye eklendi.\nToplam: {len(user_data['transfer_list'])}\nBaşlatmak için: /basla")
        return

    # Tekil İndirme
    chat_id, msg_id = parse_link(msg)
    if not chat_id:
        await update.message.reply_text("❌ Geçersiz link! Lütfen bir Telegram mesaj linki gönderin.")
        return

    allowed, remaining = check_limit(user_id)
    if not allowed:
        await update.message.reply_text("⛔ Günlük indirme limitiniz doldu!")
        return

    try:
        await context.bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=msg_id)
        db.update_user(user_id, {
            "daily_downloads": user_data["daily_downloads"] + 1,
            "total": user_data["total"] + 1
        })
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: İçerik alınamadı.\nBotun o kanala üye olduğundan emin olun.\nDetay: {e}")

# ==================== TRANSFER SİSTEMİ ====================
async def cmd_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: `/transfer @hedef_kanal` veya `ID`")
        return
    
    target = context.args[0]
    user_id = update.effective_user.id
    
    try:
        # Hedef kontrolü (Bot oraya mesaj atabiliyor mu?)
        test = await context.bot.send_message(target, "🔄 Transfer modu ayarlandı. (Bu mesaj silinecek)")
        await context.bot.delete_message(target, test.message_id)
        
        db.update_user(user_id, {
            "transfer_mode": True,
            "transfer_target": target,
            "transfer_list": []
        })
        await update.message.reply_text(
            f"✅ **Transfer Modu Aktif!**\n\n"
            f"Hedef: `{target}`\n"
            f"Şimdi mesaj linklerini gönderin (tek tek veya liste halinde).\n"
            f"Bitince `/basla` yazın."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Hedef kanala erişilemiyor. Botu o kanalda yönetici yapın.\nHata: {e}")

async def cmd_basla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = db.get_user(user_id)
    
    if not data["transfer_mode"] or not data["transfer_list"]:
        await update.message.reply_text("❌ Transfer listeniz boş veya mod aktif değil.")
        return

    status_msg = await update.message.reply_text("🚀 Transfer başlıyor...")
    
    target = data["transfer_target"]
    items = data["transfer_list"]
    delay = SPEED_DELAYS[get_status(user_id)]
    
    success = 0
    fail = 0
    
    for i, item in enumerate(items):
        allowed, _ = check_limit(user_id)
        if not allowed:
            await update.message.reply_text("⛔ Limit doldu, işlem durduruldu.")
            break
            
        try:
            await context.bot.copy_message(chat_id=target, from_chat_id=item["chat"], message_id=item["id"])
            success += 1
            db.update_user(user_id, {
                "daily_downloads": data["daily_downloads"] + 1,
                "total": data["total"] + 1
            })
            # Veritabanını anlık güncelle ki limitler işlesin
            data = db.get_user(user_id)
            
        except Exception:
            fail += 1
        
        if i % 5 == 0:
            await status_msg.edit_text(f"📦 İşleniyor... {i+1}/{len(items)}\n✅: {success} ❌: {fail}")
        
        await asyncio.sleep(delay)

    await status_msg.edit_text(f"🏁 **Tamamlandı!**\n\n✅ Başarılı: {success}\n❌ Hatalı: {fail}")
    db.update_user(user_id, {"transfer_mode": False, "transfer_list": []})

async def cmd_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.update_user(update.effective_user.id, {"transfer_mode": False, "transfer_list": []})
    await update.message.reply_text("🗑️ Transfer modu ve listesi temizlendi.")

# ==================== ADMIN VE VIP ====================
async def cmd_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        until = (datetime.now() + timedelta(days=days)).isoformat()
        
        db.update_user(user_id, {"status": "vip", "vip_until": until})
        await update.message.reply_text(f"✅ {user_id} ID'li kullanıcıya {days} gün VIP verildi.")
        
        try: await context.bot.send_message(user_id, f"🎉 **Tebrikler!** Hesabınıza {days} gün VIP tanımlandı!")
        except: pass
    except:
        await update.message.reply_text("Kullanım: `/vip KULLANICI_ID GUN`")

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_transfer":
        await query.edit_message_text(
            "📦 **Toplu Transfer Kılavuzu**\n\n"
            "1. `/transfer @kanal` yazarak hedefi seçin.\n"
            "2. Botun o kanalda yönetici olduğundan emin olun.\n"
            "3. Kopyalanacak mesaj linklerini gönderin.\n"
            "4. `/basla` yazarak işlemi başlatın.\n"
            "5. İptal etmek için `/iptal` kullanın."
        )
    elif query.data == "help_vip":
        await query.edit_message_text("💎 **VIP Avantajları**\n\n• Günde 500 İndirme\n• 3 saniyede bir işlem (Çok hızlı)\n• Öncelikli destek")

# ==================== MAIN ====================
def main():
    # Web Sunucusunu Başlat (Render İçin)
    keep_alive()
    
    # Botu Başlat
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("transfer", cmd_transfer))
    app.add_handler(CommandHandler("basla", cmd_basla))
    app.add_handler(CommandHandler("iptal", cmd_iptal))
    app.add_handler(CommandHandler("vip", cmd_vip))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot Aktif!")
    app.run_polling()

if __name__ == "__main__":
    main()
