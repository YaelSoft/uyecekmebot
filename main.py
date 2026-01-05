import os
import asyncio
import logging
from quart import Quart
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, FileReferenceExpired

# ==================== AYARLAR (ENV'den Çeker) ====================
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "hash_buraya")
SESSION1 = os.environ.get("SESSION1", "")

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RenderBot")

# ==================== WEB SERVER (Render İçin Şart) ====================
app_web = Quart(__name__)

@app_web.route('/')
async def hello():
    return "🔥 Bot Canavar Gibi Çalışıyor!"

# ==================== BOT İSTEMCİLERİ ====================
clients = []
if SESSION1: clients.append(Client("session1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1))
if SESSION2: clients.append(Client("session2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2))

if not clients:
    logger.error("❌ Session String Girilmemiş!")
    exit()

# Ana kontrolcü (Komutları alan bot - İlk Session)
bot = clients[0]

# ==================== DURUM YÖNETİMİ ====================
user_state = {} # {user_id: {"step": "waiting_source", "data": {}}}
# step: idle, wait_src, wait_dst, running

# ==================== YARDIMCI FONKSİYONLAR ====================
def resolve_link(link):
    """Linkten ID ve Topic bilgisini çeker"""
    data = {"id": None, "topic": None, "msg": 0}
    try:
        if "t.me/c/" in link:
            parts = link.split("t.me/c/")[1].split("/")
            data["id"] = int("-100" + parts[0])
            
            if len(parts) == 2: # t.me/c/ID/MSG
                data["msg"] = int(parts[1].split("?")[0])
            elif len(parts) == 3: # t.me/c/ID/TOPIC/MSG
                data["topic"] = int(parts[1])
                data["msg"] = int(parts[2].split("?")[0])
        else:
            return None
    except: return None
    return data

async def download_and_upload(worker, message, target_chat_id, target_topic):
    """Bypass Modu: İndir -> Yükle -> Sil"""
    file_path = None
    try:
        # 1. İNDİRME
        file_path = await worker.download_media(message)
        
        if not file_path: return False
        
        # 2. YÜKLEME
        caption = message.caption or ""
        # Topic varsa reply_to_message_id olarak ayarla
        kwargs = {"reply_to_message_id": target_topic} if target_topic else {}

        if message.video:
            await worker.send_video(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.photo:
            await worker.send_photo(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.document:
            await worker.send_document(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.text:
            await worker.send_message(target_chat_id, message.text, **kwargs)
            
        return True

    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: {e.value} saniye")
        await asyncio.sleep(e.value)
        return False # Hata sayılır, tekrar denensin
    except Exception as e:
        logger.error(f"❌ İşlem Hatası: {e}")
        return False
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# ==================== TELEGRAM KOMUTLARI ====================

@bot.on_message(filters.command("basla") & filters.me)
async def start_command(client, message):
    user_state[message.from_user.id] = {"step": "wait_src", "data": {}}
    await message.reply_text("👋 **Selam Kral!**\n\nTransferi başlatmak için:\n👉 **KAYNAK** mesajın linkini at (Nereden başlayayım?).")

@bot.on_message(filters.text & filters.me)
async def message_handler(client, message):
    uid = message.from_user.id
    state = user_state.get(uid, {}).get("step", "idle")

    # 1. KAYNAK LİNKİ ALMA
    if state == "wait_src":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hatalı Link! Lütfen `https://t.me/c/...` formatında at.")
            return
        
        user_state[uid]["data"]["src"] = link_data
        user_state[uid]["step"] = "wait_dst"
        await message.reply_text(f"✅ Kaynak Alındı: `{link_data['id']}`\nBaşlangıç Mesajı: `{link_data['msg']}`\n\n👉 Şimdi **HEDEF** gruptaki topic linkini at (Nereye atayım?).")

    # 2. HEDEF LİNKİ ALMA VE BAŞLATMA
    elif state == "wait_dst":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hatalı Link!")
            return
        
        user_state[uid]["data"]["dst"] = link_data
        user_state[uid]["step"] = "running"
        
        src = user_state[uid]["data"]["src"]
        dst = user_state[uid]["data"]["dst"]
        
        await message.reply_text(f"🚀 **OPERASYON BAŞLIYOR!**\n\n📥 Kaynak: `{src['id']}` (Mesaj: {src['msg']})\n📤 Hedef: `{dst['id']}` (Topic: {dst['topic']})\n\nArkanı yaslan, ben hallediyorum.")
        
        # İŞLEMİ BAŞLAT
        asyncio.create_task(run_transfer(client, src, dst, message))

# ==================== TRANSFER MOTORU ====================
async def run_transfer(main_client, src, dst, status_msg):
    current_id = src['msg']
    error_count = 0
    
    # İki worker'ı döngüyle kullanacağız
    worker_index = 0
    
    while True:
        worker = clients[worker_index % len(clients)] # Sırayla worker seç
        worker_index += 1
        
        try:
            # 1. Mesajı Çek (Tazeleme Mantığıyla)
            msg = None
            try:
                msg = await worker.get_messages(src['id'], current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msg = await worker.get_messages(src['id'], current_id)
            except Exception: pass # Mesaj silinmiş olabilir

            # Mesaj yoksa veya boşsa
            if msg is None or msg.empty:
                error_count += 1
                if error_count > 50: # 50 boş mesaj üst üste gelirse dur
                    await status_msg.reply_text("🏁 **İşlem Tamamlandı!** (Mesaj sonuna gelindi).")
                    break
                current_id += 1
                continue
            
            error_count = 0 # Mesaj bulduk, hatayı sıfırla

            # 2. İşlem Yap (Sadece Medya veya Metin)
            if msg.media or msg.text:
                await status_msg.edit_text(f"🔄 **İşleniyor:** `{current_id}`")
                
                success = await download_and_upload(worker, msg, dst['id'], dst['topic'])
                
                if success:
                    # Hız limiti yememek için minik bekleme
                    await asyncio.sleep(2) 
                else:
                    # Başarısızsa aynı ID'yi tekrar dene (veya atla)
                    # Basitlik için bir sonraki worker denesin diye ID artırmıyoruz
                    await asyncio.sleep(5)
                    continue 

            current_id += 1

        except Exception as e:
            logger.error(f"Genel Hata: {e}")
            await asyncio.sleep(5)

# ==================== BAŞLATMA ====================
async def start_services():
    # Botları başlat
    for c in clients: await c.start()
    print("✅ Botlar Aktif!")
    
    # Web serverı başlat (Render portu)
    port = int(os.environ.get("PORT", 8080))
    await app_web.run_task(host="0.0.0.0", port=port)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())

