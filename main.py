import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# AYNI ANDA KAÇ DOSYA İŞLENSİN? (Render için 4 idealdir, fazlası patlatır)
MAX_CONCURRENT_JOBS = 4 

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# Web Server (Render'ın uyumaması için)
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver Online 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================

async def refresh_cache():
    """Tüm grupları hafızaya alır"""
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
        print(f"Cache Hatası: {e}")

async def get_chat_smart(chat_input):
    """Hafızadan veya Telegram'dan grubu bulur"""
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0]
    
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    try: return await userbot.get_chat(int(target))
    except: pass
    try: return await userbot.get_chat(int("-100" + target))
    except: pass
    
    await refresh_cache()
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    return None

def parse_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = clean[0]
            if len(clean) == 2: data["msg_id"] = int(clean[1])
            elif len(clean) == 3: 
                data["topic_id"] = int(clean[1])
                data["msg_id"] = int(clean[2])
        else: # Public
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
            if len(parts) >= 3: 
                data["topic_id"] = int(parts[1])
                data["msg_id"] = int(parts[2])
    except: return None
    return data

# ==================== ARAYÜZ VE START ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("🚫 **Yetkisiz Erişim!**\nBu bot kişiye özeldir. Satın almak için: @yasin33")
        return

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İndir (/getmedia)", callback_data="help_single")],
        [InlineKeyboardButton("🚀 Transfer (/transfer)", callback_data="help_transfer")],
        [InlineKeyboardButton("🛑 DURDUR", callback_data="stop_process")],
        [InlineKeyboardButton("👨‍💻 Sahibi", url="https://t.me/yasin33")]
    ])
    
    await message.reply(
        f"👋 **Hoşgeldin, {message.from_user.first_name}!**\n\n"
        "🤖 **Yael Saver Bot v3.5 TURBO**\n"
        f"⚡ **Eşzamanlı İşlem:** {MAX_CONCURRENT_JOBS} Adet\n"
        "🛡️ **Korumalı İçerik:** Aktif\n\n"
        "Komutları görmek için butonları kullan.",
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Yetkiniz yok!", show_alert=True)
        return

    data = callback.data
    if data == "help_single":
        await callback.answer()
        await callback.message.reply("📥 **Tekli İndirme:**\n`/getmedia https://t.me/c/xxxx/123`")
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply("🚀 **Toplu Transfer:**\n`/transfer <KAYNAK> <HEDEF>`\n\nÖrn: `/transfer https://t.me/kaynak/500 https://t.me/hedef`")
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("Durdurma sinyali gönderildi!", show_alert=True)
        await callback.message.reply("🛑 **İşlemler durduruluyor... Mevcut indirmeler bitince duracak.**")

# ==================== TEKLİ İNDİRME ====================
@bot.on_message(filters.command("getmedia") & filters.user(OWNER_ID))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("❌ Link girmelisin."); return

    status = await message.reply("🔍 **Aranıyor...**")
    data = parse_link(link)
    if not data or not data["msg_id"]: await status.edit("❌ Link hatalı."); return

    chat = await get_chat_smart(data["id"])
    if not chat: await status.edit("❌ Kanal bulunamadı! Userbot üye mi?"); return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya yok.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await userbot.download_media(msg)
        
        await status.edit("📤 **Yükleniyor...**")
        cap = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TURBO TRANSFER İŞÇİSİ (WORKER) ====================
async def transfer_worker(sem, mid, src_chat_id, dst_chat_id, dst_args):
    """Her dosya için çalışan bağımsız işçi"""
    if ABORT_FLAG: return False

    async with sem: # Semaphore ile aynı anda sadece X kadar işçiye izin ver
        path = None
        try:
            # Mesajı Çek
            msg = await userbot.get_messages(src_chat_id, mid)
            if not msg: return False

            # Medya Kontrolü
            if not (msg.video or msg.photo or msg.document): return False

            print(f"⬇️ İndiriliyor: {mid}")
            
            # Güvenli İndirme (Timeout ekleyebiliriz istersen)
            path = await userbot.download_media(msg)
            
            if not path: return False

            # Yükleme
            print(f"📤 Yükleniyor: {mid}")
            cap = msg.caption or ""
            
            # FloodWait Koruması
            while True:
                try:
                    if msg.video: 
                        await userbot.send_video(dst_chat_id, video=path, caption=cap, duration=msg.video.duration, **dst_args)
                    elif msg.photo: 
                        await userbot.send_photo(dst_chat_id, photo=path, caption=cap, **dst_args)
                    elif msg.document: 
                        await userbot.send_document(dst_chat_id, document=path, caption=cap, **dst_args)
                    break # Başarılıysa döngüden çık
                except FloodWait as fw:
                    print(f"⚠️ FloodWait: {fw.value} sn bekleniyor...")
                    await asyncio.sleep(fw.value + 2)
                except Exception as e:
                    print(f"❌ Yükleme Hatası ({mid}): {e}")
                    break

            # Temizlik
            if os.path.exists(path): os.remove(path)
            return True

        except Exception as e:
            print(f"❌ UserBot Hatası ({mid}): {e}")
            if path and os.path.exists(path): os.remove(path)
            return False

# ==================== TRANSFER KOMUTU (TURBO MOD) ====================
@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ Kullanım: `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)

        src_chat = await get_chat_smart(src_data["id"])
        dst_chat = await get_chat_smart(dst_data["id"])
        
        if not src_chat or not dst_chat: 
            await status.edit("❌ Kanal bulunamadı!"); return

        start_msg_id = src_data["msg_id"]
        
        await status.edit(f"🚀 ** Transfer Başlıyor!**\n\n📤 {src_chat.title} -> 📥 {dst_chat.title}\n⚡ Hız: {MAX_CONCURRENT_JOBS}x Eşzamanlı")

        # 1. LİSTEYİ HAZIRLA
        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic Filtresi
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            # Başlangıç ID kontrolü (Geriye doğru taradığı için, start_id'den küçükse dur)
            if start_msg_id and m.id < start_msg_id: break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse() # Eskiden Yeniye
        total = len(msg_list)
        if total == 0: await status.edit("❌ İçerik yok."); return

        # 2. İŞÇİLERİ ÇALIŞTIR (TURBO KISMI)
        sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS) # Trafik Polisi
        tasks = []
        count = 0
        
        await status.edit(f"⚡ **İşleniyor: 0/{total}**\n(Aynı anda {MAX_CONCURRENT_JOBS} dosya)")

        for mid in msg_list:
            if ABORT_FLAG: break
            
            # Hedef parametreleri
            dst_args = {}
            target_top = dst_data["msg_id"] or dst_data["topic_id"]
            if target_top: dst_args["reply_to_message_id"] = target_top

            # Görevi oluştur
            task = asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args))
            tasks.append(task)
            
            # RAM şişmesin diye her 20 görevde bir temizlik yap, bitenleri listeden at
            if len(tasks) >= 20:
                finished, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending) # Bitenleri listeden çıkar
                count += len(finished)
                try: await status.edit(f"⚡ **İlerliyor: {count}/{total}**")
                except: pass

        # Kalan son görevleri bekle
        if tasks:
            await asyncio.wait(tasks)

        await bot.send_message(message.chat.id, "✅ **Transfer Tamamlandı!**")

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    await refresh_cache()
    print("YAEL SAVER  ONLINE 🚀")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
