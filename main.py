import os
import asyncio
import logging
from quart import Quart
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "")
SESSION1 = os.environ.get("SESSION1", "")
SESSION2 = os.environ.get("SESSION2", "")

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RenderBot")

app_web = Quart(__name__)

@app_web.route('/')
async def hello():
    return "🔥 V103 Yayında!"

# ==================== BOTLAR ====================
clients = []
if SESSION1: clients.append(Client("session1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1))
if SESSION2 and len(SESSION2) > 10: clients.append(Client("session2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2))

if not clients: exit()
bot = clients[0]
user_state = {} 

# ==================== YENİLENMİŞ LİNK ÇÖZÜCÜ ====================
def resolve_link(link):
    """Link formatını akıllıca analiz eder"""
    data = {"id": None, "topic": None, "msg": 0}
    try:
        # Link temizliği
        clean_link = link.strip().split("?")[0]
        
        if "t.me/c/" in clean_link:
            parts = clean_link.split("t.me/c/")[1].split("/")
            
            # Chat ID (Her zaman ilk parça)
            # Eğer ID zaten -100 ile başlamıyorsa ekle
            chat_id_str = parts[0]
            data["id"] = int("-100" + chat_id_str)
            
            if len(parts) == 2: 
                # Format: t.me/c/CHAT_ID/MSG_ID
                data["msg"] = int(parts[1])
                
            elif len(parts) == 3: 
                # Format: t.me/c/CHAT_ID/TOPIC_ID/MSG_ID
                data["topic"] = int(parts[1])
                data["msg"] = int(parts[2])
                
        else: return None
    except Exception as e:
        logger.error(f"Link Hatası: {e}")
        return None
    return data

async def download_and_upload(worker, message, target_chat_id, target_topic):
    file_path = None
    try:
        file_path = await worker.download_media(message)
        if not file_path: return False
        
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
        logger.warning(f"Flood: {e.value}")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.error(f"İşlem Hatası: {e}")
        return False
    finally:
        if file_path and os.path.exists(file_path): os.remove(file_path)

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("basla") & filters.me)
async def start_command(client, message):
    user_state[message.from_user.id] = {"step": "wait_src", "data": {}, "stop": False}
    await message.reply_text("🕵️‍♂️ **TANI MODU AKTİF**\n\nBaşlamak için **KAYNAK** mesajın linkini at.\n(Ben de doğru anlayıp anlamadığımı söyleyeceğim).")

@bot.on_message(filters.command("dur") & filters.me)
async def stop_command(client, message):
    uid = message.from_user.id
    user_state[uid]["stop"] = True
    await message.reply_text("🛑 Durduruluyor...")

@bot.on_message(filters.text & filters.me)
async def message_handler(client, message):
    uid = message.from_user.id
    state = user_state.get(uid, {}).get("step", "idle")

    # 1. KAYNAK
    if state == "wait_src":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Linki çözemedim! Format `https://t.me/c/...` olmalı.")
            return
        
        # TANI RAPORU (DEBUG)
        debug_msg = (
            f"✅ **KAYNAK ANALİZİ:**\n"
            f"🆔 Grup ID: `{link_data['id']}`\n"
            f"🔢 Başlangıç Mesajı: `{link_data['msg']}`\n"
            f"📂 Topic ID: `{link_data['topic']}` (Varsa)\n\n"
            f"Şimdi **HEDEF** topic linkini at."
        )
        
        user_state[uid]["data"]["src"] = link_data
        user_state[uid]["step"] = "wait_dst"
        await message.reply_text(debug_msg)

    # 2. HEDEF
    elif state == "wait_dst":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hedef Linki Hatalı!")
            return
        
        user_state[uid]["data"]["dst"] = link_data
        user_state[uid]["step"] = "running"
        user_state[uid]["stop"] = False
        
        src = user_state[uid]["data"]["src"]
        
        # ERİŞİM TESTİ
        await message.reply_text("🔌 **Erişim Testi Yapılıyor...**\n(Eğer burada takılırsa bot o grupta değildir)")
        try:
            test_msg = await client.get_messages(src['id'], src['msg'])
            if not test_msg or test_msg.empty:
                await message.reply_text(f"⚠️ **UYARI:** {src['msg']} numaralı mesaj BOŞ veya SİLİNMİŞ görünüyor!\nİşlem yine de başlatılıyor...")
            else:
                await message.reply_text(f"✅ **Erişim Başarılı!**\nMesaj Türü: `{test_msg.media if test_msg.media else 'Metin'}`\n\n🚀 **BAŞLIYORUZ!**")
        except Exception as e:
            await message.reply_text(f"❌ **ERİŞİM HATASI:**\nBot kaynak gruba erişemiyor!\nSebep: `{e}`")
            return

        asyncio.create_task(run_transfer(client, uid, user_state[uid]["data"]["src"], user_state[uid]["data"]["dst"], message))

# ==================== MOTOR ====================
async def run_transfer(main_client, uid, src, dst, status_msg):
    current_id = src['msg']
    empty_streak = 0
    worker_index = 0
    
    while True:
        if user_state.get(uid, {}).get("stop", False):
            await status_msg.reply_text("🛑 İşlem Durduruldu.")
            user_state[uid]["step"] = "idle"
            break

        worker = clients[worker_index % len(clients)]
        worker_index += 1
        
        try:
            # Mesajı Çek
            msg = None
            try:
                msg = await worker.get_messages(src['id'], current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msg = await worker.get_messages(src['id'], current_id)
            except: pass

            # BOŞLUK KONTROLÜ (Hemen pes etme)
            if msg is None or msg.empty:
                empty_streak += 1
                
                # Sadece her 50 boşlukta bir bilgi ver
                if empty_streak % 50 == 0:
                    await status_msg.edit_text(f"⚠️ **Boşluk Taranıyor:** `{current_id}`\n(Arka arkaya {empty_streak} boş mesaj)")
                
                # 500 Mesaj boyunca bomboşsa dur (Eskiden 50 idi, artırdım)
                if empty_streak > 500:
                    await status_msg.reply_text(f"🏁 **Tamamlandı!**\nSon taranan ID: `{current_id}`\n(500 mesajdır veri yok, sonuna gelindi).")
                    break
                
                current_id += 1
                continue
            
            empty_streak = 0 # Mesaj bulduk, sayacı sıfırla

            if msg.media or msg.text:
                # Durum güncellemesi (Her mesajda değil, 5'te bir yap ki spam olmasın)
                if current_id % 5 == 0:
                    try: await status_msg.edit_text(f"🔄 **İşleniyor:** `{current_id}`")
                    except: pass
                
                success = await download_and_upload(worker, msg, dst['id'], dst['topic'])
                
                if success: await asyncio.sleep(2) 
                else:
                    await asyncio.sleep(5)
                    # Başarısızsa atla ve devam et (Takılı kalmasın)
                    
            current_id += 1

        except Exception as e:
            logger.error(f"Döngü Hatası: {e}")
            await asyncio.sleep(5)

# ==================== BAŞLATMA ====================
async def start_services():
    for c in clients: await c.start()
    print("✅ Botlar Hazır")
    port = int(os.environ.get("PORT", 8080))
    await app_web.run_task(host="0.0.0.0", port=port)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
