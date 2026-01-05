import os
import asyncio
import logging
from quart import Quart
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, FileReferenceExpired

# ==================== AYARLAR (ENV'den Çeker) ====================
# Hata veren kısım burasıydı, düzelttim:
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "hash_buraya")
SESSION1 = os.environ.get("SESSION1", "")
SESSION2 = os.environ.get("SESSION2", "") # <-- ARTIK TANIMLI, HATA VERMEZ

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RenderBot")

# ==================== WEB SERVER (Render İçin) ====================
app_web = Quart(__name__)

@app_web.route('/')
async def hello():
    return "🔥 Bot Canavar Gibi Çalışıyor!"

# ==================== BOT İSTEMCİLERİ ====================
clients = []

# Session 1 varsa ekle
if SESSION1: 
    clients.append(Client("session1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1))

# Session 2 varsa ekle (Artık hata vermez çünkü yukarıda tanımlı)
if SESSION2 and len(SESSION2) > 10: 
    clients.append(Client("session2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2))

if not clients:
    logger.error("❌ Session String Girilmemiş! Render Environment ayarlarını kontrol et.")
    exit()

# Ana kontrolcü
bot = clients[0]

# ==================== DURUM YÖNETİMİ ====================
user_state = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================
def resolve_link(link):
    data = {"id": None, "topic": None, "msg": 0}
    try:
        if "t.me/c/" in link:
            parts = link.split("t.me/c/")[1].split("/")
            data["id"] = int("-100" + parts[0])
            
            if len(parts) == 2: 
                data["msg"] = int(parts[1].split("?")[0])
            elif len(parts) == 3: 
                data["topic"] = int(parts[1])
                data["msg"] = int(parts[2].split("?")[0])
        else: return None
    except: return None
    return data

async def download_and_upload(worker, message, target_chat_id, target_topic):
    file_path = None
    try:
        # 1. İNDİRME
        file_path = await worker.download_media(message)
        if not file_path: return False
        
        # 2. YÜKLEME
        caption = message.caption or ""
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
        return False 
    except Exception as e:
        logger.error(f"❌ İşlem Hatası: {e}")
        return False
    finally:
        if file_path and os.path.exists(file_path): os.remove(file_path)

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("basla") & filters.me)
async def start_command(client, message):
    user_state[message.from_user.id] = {"step": "wait_src", "data": {}, "stop": False}
    await message.reply_text("👋 **Selam!**\n\nBaşlamak için **KAYNAK** mesajın linkini at.")

@bot.on_message(filters.command("dur") & filters.me)
async def stop_command(client, message):
    uid = message.from_user.id
    if uid in user_state and user_state[uid].get("step") == "running":
        user_state[uid]["stop"] = True
        await message.reply_text("🛑 **DURDURMA EMRİ ALINDI!**\n\nMevcut dosya biter bitmez işlem duracak.")
    else:
        await message.reply_text("⚠️ Zaten çalışan bir işlem yok.")

@bot.on_message(filters.text & filters.me)
async def message_handler(client, message):
    uid = message.from_user.id
    state = user_state.get(uid, {}).get("step", "idle")

    if state == "wait_src":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hatalı Link!")
            return
        
        user_state[uid]["data"]["src"] = link_data
        user_state[uid]["step"] = "wait_dst"
        await message.reply_text(f"✅ Kaynak Alındı.\n\n👉 Şimdi **HEDEF** topic linkini at.")

    elif state == "wait_dst":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hatalı Link!")
            return
        
        user_state[uid]["data"]["dst"] = link_data
        user_state[uid]["step"] = "running"
        user_state[uid]["stop"] = False 
        
        await message.reply_text(f"🚀 **OPERASYON BAŞLIYOR!**\n\nDurdurmak istersen `.dur` yazman yeterli.")
        
        asyncio.create_task(run_transfer(client, uid, user_state[uid]["data"]["src"], user_state[uid]["data"]["dst"], message))

# ==================== TRANSFER MOTORU ====================
async def run_transfer(main_client, uid, src, dst, status_msg):
    current_id = src['msg']
    error_count = 0
    worker_index = 0
    
    while True:
        if user_state.get(uid, {}).get("stop", False):
            await status_msg.reply_text("🛑 **İşlem Kullanıcı İsteğiyle Durduruldu!**")
            user_state[uid]["step"] = "idle"
            break

        worker = clients[worker_index % len(clients)]
        worker_index += 1
        
        try:
            msg = None
            try:
                msg = await worker.get_messages(src['id'], current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msg = await worker.get_messages(src['id'], current_id)
            except Exception: pass 

            if msg is None or msg.empty:
                error_count += 1
                if error_count > 50:
                    await status_msg.reply_text("🏁 **İşlem Tamamlandı!** (Mesaj sonuna gelindi).")
                    break
                current_id += 1
                continue
            
            error_count = 0

            if msg.media or msg.text:
                await status_msg.edit_text(f"🔄 **İşleniyor:** `{current_id}`")
                
                success = await download_and_upload(worker, msg, dst['id'], dst['topic'])
                
                if success: await asyncio.sleep(2) 
                else:
                    await asyncio.sleep(5)
                    continue 

            current_id += 1

        except Exception as e:
            logger.error(f"Genel Hata: {e}")
            await asyncio.sleep(5)

# ==================== BAŞLATMA ====================
async def start_services():
    for c in clients: await c.start()
    print("✅ Botlar Aktif!")
    port = int(os.environ.get("PORT", 8080))
    await app_web.run_task(host="0.0.0.0", port=port)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
