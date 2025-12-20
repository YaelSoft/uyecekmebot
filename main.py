import os
import logging
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==================== 1. WEB SERVER (RENDER'I AYAKTA TUTAR) ====================
# Render bu portu dinlemezsen uygulamayı kapatır.
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Çalışıyor! 🟢 (Lütfen bu linki UptimeRobot'a ekleyin)"

def run_web():
    # Render genelde PORT environment variable'ını otomatik atar (10000)
    port = int(os.environ.get("PORT", 10000))
    print(f"🌍 Web Server {port} portunda başlatılıyor...")
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        print(f"❌ Web Server Hatası: {e}")

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True # Ana program kapanınca bu da kapansın
    t.start()

# ==================== 2. AYARLAR ====================
# Tokeni Render'dan alır, yoksa buradakini kullanır (Test için)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7839067076:AAHgC6C-mzQegzVVHLmkVH08vu-jkTBaQlI")
ADMIN_ID = 7292548110

# Logging Ayarları (Hata tespiti için detaylı)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== 3. BOT KOMUTLARI ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"KOMUT ALINDI: /start - Kullanıcı: {user.id}")
    
    txt = (
        f"👋 **Merhaba {user.first_name}!**\n\n"
        f"Ben aktifim ve çalışıyorum.\n"
        f"🆔 ID'niz: `{user.id}`\n\n"
        f"📥 **Kullanım:**\n"
        f"Bana indirmek istediğin mesajın linkini atman yeterli.\n"
        f"Örnek: `https://t.me/kanal/123`"
    )
    
    # Buton ekleyelim ki botun cevap verdiğini net görelim
    buttons = [[InlineKeyboardButton("✅ Çalışıyor mu?", callback_data="ping")]]
    
    try:
        await update.message.reply_html(txt, reply_markup=InlineKeyboardMarkup(buttons))
        logger.info("Cevap gönderildi.")
    except Exception as e:
        logger.error(f"Mesaj gönderme hatası: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user_id = update.effective_user.id
    logger.info(f"MESAJ GELDİ ({user_id}): {msg}")

    if "t.me/" not in msg:
        await update.message.reply_text("⚠️ Lütfen geçerli bir Telegram linki gönderin.")
        return

    status_msg = await update.message.reply_text("🔎 Link analiz ediliyor...")

    # Basit Link Analizi
    try:
        # Linkten ID ve Mesaj ID çıkarma
        clean = msg.strip().replace("https://t.me/", "").replace("@", "")
        
        chat_id = None
        message_id = None

        # Private Link (c/...)
        if "c/" in clean:
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            message_id = int(parts[1])
        # Public Link
        else:
            parts = clean.split("/")
            chat_id = f"@{parts[0]}"
            message_id = int(parts[1])

        # Kopyalama İşlemi
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=chat_id,
            message_id=message_id
        )
        await status_msg.edit_text("✅ **İndirme Başarılı!**")
        logger.info("Kopyalama başarılı.")

    except Exception as e:
        error_text = str(e)
        logger.error(f"İşlem Hatası: {e}")
        
        if "Chat not found" in error_text:
            await status_msg.edit_text("❌ **Hata:** Bot bu kanalda/grupta değil. Lütfen botu o kanala ekleyin.")
        elif "Message not found" in error_text:
            await status_msg.edit_text("❌ **Hata:** Mesaj bulunamadı veya silinmiş.")
        else:
            await status_msg.edit_text(f"❌ **Hata:** {error_text}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ping":
        await query.edit_message_text("🏓 **Pong!** Bot sapa sağlam çalışıyor.")

# ==================== 4. BAŞLATMA ====================
def main():
    # 1. Web Sunucusunu Başlat (Arka planda)
    keep_alive()
    
    # 2. Botu Kur
    print("🚀 Bot başlatılıyor...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Handler'lar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 3. Botu Çalıştır (Polling)
    # drop_pending_updates=True: Bot kapalıyken gelen eski mesajları yoksayar (Hızlandırır)
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
