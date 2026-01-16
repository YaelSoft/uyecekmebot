import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==================== SİSTEM AYARLARI ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Eşzamanlı İşlem Limiti (Performans/Güvenlik Dengesi)
MAX_CONCURRENT_JOBS = 4 

# Loglama Konfigürasyonu
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaverSystem")

# Web Sunucusu (Uptime İçin)
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver Enterprise System Online 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# İstemci Başlatma
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI MODÜLLER ====================

async def refresh_cache():
    """Grup listesini önbelleğe alır."""
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
        logger.error(f"Önbellek Hatası: {e}")

async def get_chat_smart(chat_input):
    """Akıllı grup çözümleme algoritması."""
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
    """Link yapısını analiz eder."""
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
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

# ==================== KULLANICI ARAYÜZÜ ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("⛔ **Yetkisiz Erişim**\n\nBu sistem Yael Saver lisanslı kullanıcılarına özeldir.\nErişim satın almak için: **@yasin33**")
        return

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İndirme (/getmedia)", callback_data="help_single")],
        [InlineKeyboardButton("🚀 Veri Transferi (/transfer)", callback_data="help_transfer")],
        [InlineKeyboardButton("⛔ İşlemi İptal Et", callback_data="stop_process")],
    ])
    
    await message.reply(
        f"👋 **Merhaba, {message.from_user.first_name}.**\n\n"
        "💎 **Yael Saver Enterprise v4.0**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **Sistem Durumu:** `Aktif`\n"
        "⚡ **İşlem Kapasitesi:** `Multi-Thread ({MAX_CONCURRENT_JOBS}x)`\n"
        "🛡️ **Kısıtlama Koruması:** `Devrede`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Lütfen gerçekleştirmek istediğiniz işlemi seçiniz.",
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.from_user.id != OWNER_ID: return
    data = callback.data
    
    if data == "help_single":
        await callback.answer()
        await callback.message.reply(
            "📥 **Tekli Medya İndirme Modülü**\n\n"
            "Belirtilen linkteki içeriği sunucuya indirir ve size iletir.\n"
            "**Kullanım:** `/getmedia <LINK>`"
        )
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply(
            "🚀 **Toplu Veri Transfer Modülü**\n\n"
            "Kaynak kanaldaki içerikleri hedef kanala aktarır.\n"
            "**Kullanım:** `/transfer <KAYNAK_LINK> <HEDEF_LINK>`"
        )
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("İptal sinyali gönderildi.", show_alert=True)
        await callback.message.reply("⚠️ **Durduruluyor...**\nMevcut işlemler tamamlandıktan sonra sistem duracaktır.")

# ==================== GET MEDİA CODES ====================
@bot.on_message(filters.command("getmedia") & filters.user(OWNER_ID))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("⚠️ Lütfen geçerli bir link giriniz."); return

    status = await message.reply("🔍 **İçerik Analiz Ediliyor...**")
    data = parse_link(link)
    if not data or not data["msg_id"]: await status.edit("❌ Geçersiz Link Formatı."); return

    chat = await get_chat_smart(data["id"])
    if not chat: await status.edit("❌ Kanal erişimi sağlanamadı."); return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        if not (msg.video or msg.photo or msg.document):
            await status.edit("⚠️ İlgili mesajda indirilebilir medya bulunamadı.")
            return

        await status.edit("📥 **İndirme İşlemi Başlatıldı...**")
        path = await userbot.download_media(msg)
        
        await status.edit("📤 **Sunucuya Yükleniyor...**")
        cap = msg.caption or ""
        
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
        
    except Exception as e:
        await status.edit(f"❌ **Sistem Hatası:** `{e}`")

# ==================== TRANSFER USERBOT (WORKER) ====================
async def transfer_worker(sem, mid, src_chat_id, dst_chat_id, dst_args):
    """Her dosya için çalışan bağımsız işlem birimi"""
    if ABORT_FLAG: return (False, 0, "Kullanıcı İptali")

    async with sem: 
        path = None
        try:
            msg = await userbot.get_messages(src_chat_id, mid)
            if not msg or not (msg.video or msg.photo or msg.document): 
                return (False, 0, "Medya Tipi Desteklenmiyor")

            # Boyut Hesaplama (MB)
            file_size = 0
            if msg.video: file_size = msg.video.file_size
            elif msg.photo: file_size = msg.photo.file_size
            elif msg.document: file_size = msg.document.file_size
            size_mb = file_size / (1024 * 1024)

            # İndirme Prosesi
            path = await userbot.download_media(msg)
            if not path: return (False, 0, "İndirme Başarısız")

            # Yükleme Prosesi
            cap = msg.caption or ""
            while True:
                try:
                    if msg.video: 
                        await userbot.send_video(dst_chat_id, video=path, caption=cap, duration=msg.video.duration, **dst_args)
                    elif msg.photo: 
                        await userbot.send_photo(dst_chat_id, photo=path, caption=cap, **dst_args)
                    elif msg.document: 
                        await userbot.send_document(dst_chat_id, document=path, caption=cap, **dst_args)
                    break 
                except FloodWait as fw:
                    # Telegram limitlerine takılınca bekleme
                    await asyncio.sleep(fw.value + 2)
                except Exception as e:
                    if os.path.exists(path): os.remove(path)
                    return (False, size_mb, str(e))

            if os.path.exists(path): os.remove(path)
            return (True, size_mb, "OK")

        except Exception as e:
            if path and os.path.exists(path): os.remove(path)
            return (False, 0, str(e))

# ==================== TRANSFER MODÜLÜ (PROFESYONEL RAPORLAMA) ====================
@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    start_time = time.time() 

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("ℹ️ **Kullanım:** `/transfer [KAYNAK_LINK] [HEDEF_LINK]`"); return

    status = await message.reply("🔄 **Kaynak Analizi Yapılıyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)
        src_chat = await get_chat_smart(src_data["id"])
        dst_chat = await get_chat_smart(dst_data["id"])
        
        if not src_chat or not dst_chat: 
            await status.edit("❌ **Hata:** Kaynak veya Hedef kanal erişimi başarısız."); return

        start_msg_id = src_data["msg_id"]
        
        await status.edit(f"⚙️ **Mesajlar Taranıyor...**\n📂 Kaynak: `{src_chat.title}`")

        # 1. LİSTELEME PROSESİ
        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            if start_msg_id and m.id < start_msg_id: break
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse() 
        total = len(msg_list)
        if total == 0: await status.edit("⚠️ **Uyarı:** Aktarılacak uygun içerik bulunamadı."); return

        # 2. AKTARIM PROSESİ
        sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        tasks = []
        
        processed_count = 0
        success_count = 0
        fail_count = 0
        total_size_mb = 0.0
        
        await status.edit(f"🚀 **Transfer Başlatıldı**\n\n📂 Dosya Adedi: `{total}`\n⚙️ Protokol: `Concurrent Transfer`")

        for mid in msg_list:
            if ABORT_FLAG: break
            
            dst_args = {}
            target_top = dst_data["msg_id"] or dst_data["topic_id"]
            if target_top: dst_args["reply_to_message_id"] = target_top

            task = asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args))
            tasks.append(task)
            
            if len(tasks) >= MAX_CONCURRENT_JOBS + 1:
                finished, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                
                for t in finished:
                    success, size, err = t.result()
                    processed_count += 1
                    if success:
                        success_count += 1
                        total_size_mb += size
                    else:
                        fail_count += 1
                
                # CANLI DURUM RAPORU
                try: 
                    percent = (processed_count / total) * 100
                    await status.edit(
                        f"🔄 **Veri Aktarımı Sürüyor...**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📈 **İlerleme:** `%{percent:.1f}`\n"
                        f"🔢 **İşlenen:** `{processed_count}/{total}`\n"
                        f"✅ **Başarılı:** `{success_count}`\n"
                        f"❌ **Hatalı:** `{fail_count}`\n"
                        f"💾 **Transfer Hacmi:** `{total_size_mb:.1f} MB`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━"
                    )
                except: pass

        if tasks:
            done, _ = await asyncio.wait(tasks)
            for t in done:
                success, size, err = t.result()
                processed_count += 1
                if success: success_count += 1; total_size_mb += size
                else: fail_count += 1

        # 3. FİNAL RAPORU
        end_time = time.time()
        duration = end_time - start_time
        mins, secs = divmod(int(duration), 60)
        time_str = f"{mins}dk {secs}sn"

        final_msg = (
            f"✅ **TRANSFER İŞLEMİ TAMAMLANDI**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 **Kaynak:** `{src_chat.title}`\n"
            f"📤 **Hedef:** `{dst_chat.title}`\n"
            f"⏱️ **İşlem Süresi:** `{time_str}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **İSTATİSTİKLER**\n"
            f"✅ Başarılı: `{success_count}`\n"
            f"❌ Hatalı: `{fail_count}`\n"
            f"💾 Toplam Veri: `{total_size_mb:.2f} MB`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Yael Saver Enterprise Systems*"
        )
        
        await status.edit(final_msg)
        await bot.send_message(message.chat.id, "📋 **İşlem Raporu Oluşturuldu.**\nYukarıdaki detayları inceleyebilirsiniz.")

    except Exception as e:
        await status.edit(f"❌ **Kritik İşlem Hatası:** `{e}`")

# ==================== SİSTEM BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    await refresh_cache()
    print("YAEL SAVER ENTERPRISE SYSTEM: ONLINE 🟢")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
