import os
import asyncio
import logging
from quart import Quart
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChatWriteForbidden, ChatAdminRequired, UserBannedInChannel

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "")
SESSION1 = os.environ.get("SESSION1", "")
SESSION2 = os.environ.get("SESSION2", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RenderBot")

app_web = Quart(__name__)

@app_web.route('/')
async def hello(): return "🔥 V104 Hazır!"

# ==================== BOTLAR ====================
clients = []
if SESSION1: clients.append(Client("session1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1))
if SESSION2 and len(SESSION2) > 10: clients.append(Client("session2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2))

if not clients: exit()
bot = clients[0]
user_state = {} 

# ==================== LİNK ÇÖZÜCÜ ====================
def resolve_link(link):
    data = {"id": None, "topic": None, "msg": 0}
    try:
        clean_link = link.strip().split("?")[0]
        if "t.me/c/" in clean_link:
            parts = clean_link.split("t.me/c/")[1].split("/")
            data["id"] = int("-100" + parts[0])
            
            if len(parts) == 2: 
                data["msg"] = int(parts[1])
            elif len(parts) == 3: 
                data["topic"] = int(parts[1])
                data["msg"] = int(parts[2])
        else: return None
    except: return None
    return data

async def download_and_upload(worker, message, target_chat_id, target_topic):
    file_path = None
    try:
        file_path = await worker.download_media(message)
        if not file_path: return False
        
        caption = message.caption or ""
        kwargs = {"reply_to_message_id": target_topic} if target_topic else {}

        if message.video: await worker.send_video(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.photo: await worker.send_photo(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.document: await worker.send_document(target_chat_id, file_path, caption=caption, **kwargs)
        elif message.text: await worker.send_message(target_chat_id, message.text, **kwargs)
            
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        return False
    finally:
        if file_path and os.path.exists(file_path): os.remove(file_path)

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("basla") & filters.me)
async def start_command(client, message):
    user_state[message.from_user.id] = {"step": "wait_src", "data": {}, "stop": False}
    await message.reply_text("🕵️‍♂️ **HATA BULUCU MODU**\n\nÖnce **KAYNAK** mesajın linkini at.")

@bot.on_message(filters.command("dur") & filters.me)
async def stop_command(client, message):
    uid = message.from_user.id
    user_state[uid]["stop"] = True
    await message.reply_text("🛑 Durduruluyor...")

@bot.on_message(filters.text & filters.me)
async def message_handler(client, message):
    uid = message.from_user.id
    state = user_state.get(uid, {}).get("step", "idle")

    # 1. KAYNAK AL
    if state == "wait_src":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Link Hatalı!")
            return
        
        user_state[uid]["data"]["src"] = link_data
        user_state[uid]["step"] = "wait_dst"
        await message.reply_text(f"✅ Kaynak OK.\n\n👉 Şimdi **HEDEF** topic linkini at.\n(Dikkat: Hedefe test mesajı atıp sileceğim).")

    # 2. HEDEF AL VE TEST ET (ÖNEMLİ KISIM)
    elif state == "wait_dst":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hedef Link Hatalı!")
            return
        
        target_id = link_data['id']
        topic_id = link_data['topic']
        
        status_msg = await message.reply_text("🔌 **HEDEF GRUBA BAĞLANTI TEST EDİLİYOR...**")
        
        # --- TEST AŞAMASI ---
        try:
            # 1. Grubu Görebiliyor muyuz?
            chat = await client.get_chat(target_id)
            chat_title = chat.title
            
            # 2. Mesaj Atabiliyor muyuz? (Test Mesajı)
            kwargs = {"reply_to_message_id": topic_id} if topic_id else {}
            sent_msg = await client.send_message(target_id, "🤖 Bağlantı Testi (Bu mesaj silinecek)", **kwargs)
            
            # 3. Başarılıysa sil
            await sent_msg.delete()
            
            await status_msg.edit_text(f"✅ **BAĞLANTI BAŞARILI!**\n\nGrup: `{chat_title}`\nDurum: Mesaj atılabiliyor.\n\n🚀 **TRANSFER BAŞLIYOR...**")
            
        except ChatWriteForbidden:
            await status_msg.edit_text(f"❌ **YETKİ YOK!**\nBu gruba mesaj atma iznin kapalı. (Admin engellemiş veya sadece okuma modu).")
            return
        except ChatAdminRequired:
            await status_msg.edit_text(f"❌ **ADMİN YETKİSİ LAZIM!**\nBurası bir Kanal veya özel grup, mesaj atabilmek için Admin olmalısın.")
            return
        except UserBannedInChannel:
            await status_msg.edit_text(f"❌ **BANLISIN!**\nBu gruptan banlanmışsın veya kısıtlanmışsın.")
            return
        except Exception as e:
            await status_msg.edit_text(f"❌ **ERİŞİM HATASI!**\nBot bu grubu göremiyor.\n\n**Olası Sebepler:**\n1. Bot (Senin Hesap) bu grupta üye değil.\n2. ID yanlış (-100 ile başlamalı).\n3. İnternet hatası.\n\nTelegram Hata Kodu: `{e}`")
            return
        
        # TESTİ GEÇTİYSE DEVAM ET
        user_state[uid]["data"]["dst"] = link_data
        user_state[uid]["step"] = "running"
        user_state[uid]["stop"] = False
        
        src = user_state[uid]["data"]["src"]
        
        asyncio.create_task(run_transfer(client, uid, src, link_data, message))

# ==================== TRANSFER MOTORU ====================
async def run_transfer(main_client, uid, src, dst, status_msg):
    current_id = src['msg']
    error_count = 0
    worker_index = 0
    
    while True:
        if user_state.get(uid, {}).get("stop", False):
            await status_msg.reply_text("🛑 Durduruldu.")
            user_state[uid]["step"] = "idle"
            break

        worker = clients[worker_index % len(clients)]
        worker_index += 1
        
        try:
            # Kaynak Mesajı Çek
            msg = None
            try:
                msg = await worker.get_messages(src['id'], current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                msg = await worker.get_messages(src['id'], current_id)
            except: pass

            if msg is None or msg.empty:
                error_count += 1
                if error_count > 500:
                    await status_msg.reply_text(f"🏁 **Bitti!** Son ID: `{current_id}`")
                    break
                current_id += 1
                continue
            
            error_count = 0

            if msg.media or msg.text:
                if current_id % 5 == 0:
                    try: await status_msg.edit_text(f"🔄 **İşleniyor:** `{current_id}`")
                    except: pass
                
                # Hedefe Yükle (Testi zaten geçtik, burası çalışmalı)
                success = await download_and_upload(worker, msg, dst['id'], dst['topic'])
                
                if success: await asyncio.sleep(2) 
                else: await asyncio.sleep(5)
                    
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
