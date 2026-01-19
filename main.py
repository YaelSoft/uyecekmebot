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
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

MAX_CONCURRENT_JOBS = 4  # Render için ideal hız

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# ==================== WEB SUNUCUSU (UPTIME) ====================
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

# ==================== BOT İSTEMCİLERİ ====================
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================

async def refresh_cache():
    global CHAT_CACHE
    try:
        async for dialog in userbot.get_dialogs():
            raw_id = str(dialog.chat.id)
            clean_id = raw_id.replace("-100", "").replace("-", "")
            CHAT_CACHE[raw_id] = dialog.chat
            CHAT_CACHE[clean_id] = dialog.chat
            if dialog.chat.username:
                CHAT_CACHE[dialog.chat.username.lower()] = dialog.chat
    except Exception as e:
        logger.error(f"Cache Hatası: {e}")

async def get_chat_smart(chat_input):
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0]
    
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    try: return await userbot.get_chat(int(target))
    except: pass
    try: return await userbot.get_chat(int("-100" + target))
    except: pass
    try: return await userbot.get_chat(target)
    except: return None

def parse_link(link):
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

# ==================== ARAYÜZ VE MENÜLER ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply(
            "🚫 **Yetkisiz Erişim!**\n\n"
            "Bu bot kişiye özeldir.\n"
            "Satın almak veya kendi botunuzu yaptırmak için:\n"
            "👉 **@yasin33** ile iletişime geçin."
        )
        return

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Tekli İndirme", callback_data="help_single"),
            InlineKeyboardButton("🚀 Toplu Transfer", callback_data="help_transfer")
        ],
        [InlineKeyboardButton("⛔ İŞLEMİ DURDUR", callback_data="stop_process")]
    ])
    
    await message.reply(
        f"👋 **Hoş Geldiniz, {message.from_user.first_name}**\n\n"
        f"**Yael Saver** sistemi kullanıma hazırdır. "
        f"Aşağıdaki komutlarla kısıtlı içerikleri (Restricted Content) indirebilir veya kopyalayabilirsiniz.\n\n"
        f"📋 **HIZLI KULLANIM REHBERİ**\n\n"
        f"🔹 **Tekli İndirme:**\n"
        f"Bir fotoğraf veya videoyu indirmek için:\n"
        f"`/getmedia <Link>`\n\n"
        f"🔹 **Toplu Transfer:**\n"
        f"Bir kanalı başka bir kanala kopyalamak için:\n"
        f"`/transfer <Kaynak_Link> <Hedef_Link>`\n"
        f"*(İpucu: Kaynak linkin sonuna `/500` gibi sayı eklerseniz o mesajdan başlar)*\n\n"
        f"⚡ **Sistem Durumu:** `Aktif ({MAX_CONCURRENT_JOBS}x)`\n"
        f"👇 **İşlem seçmek için butonları kullanın:**",
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Yetkisiz işlem!", show_alert=True)
        return

    data = callback.data
    
    if data == "help_single":
        await callback.answer()
        await callback.message.reply("**📥 TEKLİ İNDİRME**\n`/getmedia <LINK>`")
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply("**🚀 TRANSFER**\n`/transfer <KAYNAK> <HEDEF>`")
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("Durduruluyor...", show_alert=True)
        await callback.message.reply("🛑 **İşlemler durduruluyor...**")

# ==================== TEKLİ İNDİRME ====================
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
        
        cap = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TRANSFER İŞÇİSİ ====================
async def transfer_worker(sem, mid, src, dst, args):
    if ABORT_FLAG: return (False, 0)
    
    async with sem:
        path = None
        try:
            msg = await userbot.get_messages(src, mid)
            if not msg or not (msg.video or msg.photo or msg.document): return (False, 0)
            
            size = 0
            if msg.video: size = msg.video.file_size
            elif msg.photo: size = msg.photo.file_size
            elif msg.document: size = msg.document.file_size
            
            path = await userbot.download_media(msg)
            if not path: return (False, 0)
            
            while True:
                try:
                    if msg.video: await userbot.send_video(dst, video=path, caption=msg.caption or "", duration=msg.video.duration, **args)
                    elif msg.photo: await userbot.send_photo(dst, photo=path, caption=msg.caption or "", **args)
                    elif msg.document: await userbot.send_document(dst, document=path, caption=msg.caption or "", **args)
                    break
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 2)
                except: break
            
            if os.path.exists(path): os.remove(path)
            return (True, size / 1024 / 1024)
            
        except: 
            if path and os.path.exists(path): os.remove(path)
            return (False, 0)

# ==================== TRANSFER KOMUTU ====================
@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("⚠️ Kullanım: `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)
        
        src_chat = await get_chat_smart(src_data["id"])
        dst_chat = await get_chat_smart(dst_data["id"])
        
        if not src_chat or not dst_chat:
            await status.edit("❌ Kanal bulunamadı.")
            return

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            if m.video or m.photo or m.document: msg_list.append(m.id)
        
        msg_list.reverse()
        total = len(msg_list)
        if total == 0: await status.edit("❌ İçerik yok."); return
        
        sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        tasks = []
        processed = 0
        success = 0
        total_size = 0.0
        
        await status.edit(f"🚀 **Transfer Başladı**\n📂 Dosya: `{total}`\n⚡ Mod: `{MAX_CONCURRENT_JOBS}x`")
        
        for mid in msg_list:
            if ABORT_FLAG: break
            
            dst_args = {}
            if dst_data["msg_id"]: dst_args["reply_to_message_id"] = dst_data["msg_id"]
            
            tasks.append(asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args)))
            
            if len(tasks) >= MAX_CONCURRENT_JOBS + 1:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                for t in done:
                    res, size = t.result()
                    processed += 1
                    if res: success += 1; total_size += size
                
                try:
                    percent = int((processed / total) * 100)
                    await status.edit(
                        f"🔄 **Sürüyor...**\n"
                        f"📈 İlerleme: %{percent} (`{processed}/{total}`)\n"
                        f"✅ Başarılı: {success}"
                    )
                except: pass

        if tasks: await asyncio.wait(tasks)
        
        await status.edit(
            f"✅ **TAMAMLANDI**\n"
            f"📂 Toplam: `{total}`\n"
            f"✅ Başarılı: `{success}`\n"
            f"💾 Boyut: `{int(total_size)} MB`"
        )
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== MAIN ====================
async def main():
    keep_alive()
    print("Bot Başlatılıyor...")
    await bot.start()
    await userbot.start()
    await refresh_cache()
    print("✅ YAEL SAVER PRO AKTİF")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
