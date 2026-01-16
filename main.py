import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

# ==================== RENDER AYARLARI ====================
# Bu değerler Render'ın "Environment Variables" kısmından çekilir.
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Hız Ayarı (Aynı anda işlenecek dosya sayısı)
MAX_JOBS = 4

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# ==================== WEB SERVER (Render İçin Şart) ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Yael Saver System Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== BOT KURULUMU ====================
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================

async def get_chat_smart(chat_input):
    """Kanal bulma fonksiyonu"""
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0]
    
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    try: 
        chat = await userbot.get_chat(int(target))
        CHAT_CACHE[target] = chat
        return chat
    except: pass
    
    try: 
        chat = await userbot.get_chat(int("-100" + target))
        CHAT_CACHE[target] = chat
        return chat
    except: pass
    
    try: 
        chat = await userbot.get_chat(target)
        CHAT_CACHE[target] = chat
        return chat
    except: return None

def parse_link(link):
    """Link ayrıştırma fonksiyonu"""
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: 
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = clean[0]
            if len(clean) == 2: data["msg_id"] = int(clean[1])
            elif len(clean) == 3: 
                data["topic_id"] = int(clean[1])
                data["msg_id"] = int(clean[2])
        else: 
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
            if len(parts) >= 3: 
                data["topic_id"] = int(parts[1])
                data["msg_id"] = int(parts[2])
    except: return None
    return data

# ==================== ARAYÜZ VE BUTONLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("⛔ **Yetkisiz Erişim.**\nBu bot özel bir yazılımdır.")
        return

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İndir", callback_data="help_single"),
         InlineKeyboardButton("🚀 Toplu Transfer", callback_data="help_transfer")],
        [InlineKeyboardButton("⛔ İşlemi Durdur", callback_data="stop_process")]
    ])
    
    await message.reply(
        f"👋 **Yael Saver Pro Sistemine Hoş Geldiniz**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Kullanıcı:** {message.from_user.first_name}\n"
        f"🟢 **Sistem:** Aktif\n"
        f"⚡ **Mod:** Hızlı Transfer ({MAX_JOBS}x)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        "Lütfen işlem seçiniz:",
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Yetkiniz yok.", show_alert=True)
        return

    data = callback.data
    
    if data == "help_single":
        await callback.answer()
        await callback.message.reply(
            "**📥 TEKLİ İNDİRME**\n\n"
            "Komut: `/getmedia <LİNK>`\n"
            "Örnek: `/getmedia https://t.me/c/xxxx/123`"
        )
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply(
            "**🚀 TOPLU TRANSFER**\n\n"
            "Komut: `/transfer <KAYNAK> <HEDEF>`\n"
            "Örnek: `/transfer https://t.me/kaynak https://t.me/hedef`"
        )
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("İptal ediliyor...", show_alert=True)
        await callback.message.reply("🛑 **İşlem durduruluyor...**")

# ==================== İNDİRME VE TRANSFER İŞLEMLERİ ====================

@bot.on_message(filters.command("getmedia") & filters.user(OWNER_ID))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("⚠️ Link giriniz."); return

    status = await message.reply("🔍 **Aranıyor...**")
    data = parse_link(link)
    chat = await get_chat_smart(data["id"])
    
    if not chat:
        await status.edit("❌ Kanal bulunamadı.")
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        await status.edit("📥 **İndiriliyor...**")
        path = await userbot.download_media(msg)
        
        if not path:
            await status.edit("❌ İndirme başarısız.")
            return

        await status.edit("📤 **Yükleniyor...**")
        
        caption = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=caption)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=caption)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=caption)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- ARKA PLAN İŞÇİSİ (HIZLI AKTARIM) ---
async def transfer_worker(sem, mid, src, dst, args):
    if ABORT_FLAG: return (False, 0)
    
    async with sem: # Aynı anda işlem limiti
        path = None
        try:
            msg = await userbot.get_messages(src, mid)
            if not msg or not (msg.video or msg.photo or msg.document): return (False, 0)
            
            # Dosya boyutu (İstatistik için)
            size = 0
            if msg.video: size = msg.video.file_size
            elif msg.photo: size = msg.photo.file_size
            elif msg.document: size = msg.document.file_size
            
            path = await userbot.download_media(msg)
            if not path: return (False, 0)
            
            # Yükleme (FloodWait Korumalı)
            while True:
                if ABORT_FLAG: break
                try:
                    if msg.video: await userbot.send_video(dst, video=path, caption=msg.caption or "", duration=msg.video.duration, **args)
                    elif msg.photo: await userbot.send_photo(dst, photo=path, caption=msg.caption or "", **args)
                    elif msg.document: await userbot.send_document(dst, document=path, caption=msg.caption or "", **args)
                    break
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 3)
                except: break
            
            if os.path.exists(path): os.remove(path)
            return (True, size / 1024 / 1024)
            
        except: 
            if path and os.path.exists(path): os.remove(path)
            return (False, 0)

@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("⚠️ **Kullanım:** `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)
        
        src_chat = await get_chat_smart(src_data["id"])
        dst_chat = await get_chat_smart(dst_data["id"])
        
        if not src_chat or not dst_chat:
            await status.edit("❌ Kaynak veya Hedef kanal bulunamadı.")
            return

        # Mesaj Listesini Hazırla
        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            if m.video or m.photo or m.document: msg_list.append(m.id)
        
        msg_list.reverse()
        total = len(msg_list)
        if total == 0: await status.edit("❌ Aktarılacak içerik yok."); return
        
        # İşlemi Başlat
        sem = asyncio.Semaphore(MAX_JOBS)
        tasks = []
        processed = 0
        success = 0
        total_size = 0.0
        
        await status.edit(f"🚀 **Transfer Başlatıldı**\n📂 Dosya Sayısı: `{total}`\n⚡ İşleniyor...")
        
        for mid in msg_list:
            if ABORT_FLAG: break
            
            dst_args = {}
            if dst_data["msg_id"]: dst_args["reply_to_message_id"] = dst_data["msg_id"]
            
            tasks.append(asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args)))
            
            # İlerleme Çubuğu (Bufferlı)
            if len(tasks) >= MAX_JOBS + 1:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                for t in done:
                    res, size = t.result()
                    processed += 1
                    if res: success += 1; total_size += size
                
                try:
                    percent = int((processed / total) * 100)
                    await status.edit(f"🔄 **Sürüyor...**\n📈 İlerleme: %{percent}\n✅ Başarılı: {success}")
                except: pass

        if tasks: await asyncio.wait(tasks)
        
        await status.edit(
            f"✅ **İŞLEM TAMAMLANDI**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 Toplam: `{total}`\n"
            f"✅ Başarılı: `{success}`\n"
            f"💾 Boyut: `{int(total_size)} MB`"
        )
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== MAIN ====================
async def main():
    keep_alive() # Render için şart
    print("Bot Başlatılıyor...")
    await bot.start()
    await userbot.start()
    print("✅ YAEL SAVER PRO AKTİF")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
