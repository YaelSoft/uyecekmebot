import os
import asyncio
import logging
from quart import Quart
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "")
SESSION1 = os.environ.get("SESSION1", "")
SESSION2 = os.environ.get("SESSION2", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RenderBot")

app_web = Quart(__name__)

@app_web.route('/')
async def hello(): return "🔥 V106 TOPIC HUNTER Yayında!"

# ==================== BOTLAR ====================
clients = []
if SESSION1: clients.append(Client("session1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1))
if SESSION2 and len(SESSION2) > 10: clients.append(Client("session2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2))

if not clients: exit()
bot = clients[0]
user_state = {} 

# ==================== LİNK ÇÖZÜCÜ (TOPIC ID'Yİ ALMAK İÇİN) ====================
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
                data["topic"] = int(parts[1]) # Kaynak Topic ID'si burada
                data["msg"] = int(parts[2])   # Başlangıç Mesajı
        else: return None
    except: return None
    return data

# ==================== ID TANIYICI ====================
async def ensure_chat_access(client, chat_id, chat_name="Grup"):
    try:
        chat = await client.get_chat(chat_id)
        return chat.title
    except (PeerIdInvalid, ChannelInvalid):
        async for dialog in client.get_dialogs(limit=500):
            if dialog.chat.id == chat_id:
                return dialog.chat.title
        raise Exception(f"❌ {chat_name} bulunamadı! Nokta (.) at.")

# ==================== İŞLEM (İNDİR/YÜKLE) ====================
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
    await message.reply_text("🎯 **TOPIC MODU**\n\nBaşlamak istediğin **KAYNAK** mesajın linkini at.\n(Linkin içinde Topic ID olması önemli!)")

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
        
        msg_text = f"✅ Kaynak OK.\n🆔 Grup: `{link_data['id']}`\n"
        if link_data['topic']:
            msg_text += f"📂 Topic ID: `{link_data['topic']}` (Sadece bu konu taranacak)\n"
        else:
            msg_text += "⚠️ **UYARI:** Linkte Topic ID yok! Genel sohbet taranacak.\n"
            
        msg_text += "\n👉 Şimdi **HEDEF** topic linkini at."
        await message.reply_text(msg_text)

    # 2. HEDEF AL VE BAŞLAT
    elif state == "wait_dst":
        link_data = resolve_link(message.text)
        if not link_data:
            await message.reply_text("❌ Hedef Link Hatalı!")
            return
        
        user_state[uid]["data"]["dst"] = link_data
        user_state[uid]["step"] = "running"
        user_state[uid]["stop"] = False
        
        src = user_state[uid]["data"]["src"]
        
        # Erişim Kontrolü
        try:
            await ensure_chat_access(client, src['id'], "KAYNAK")
            await ensure_chat_access(client, link_data['id'], "HEDEF")
        except Exception as e:
            await message.reply_text(f"🛑 {e}")
            return

        await message.reply_text(f"🚀 **BAŞLIYOR...**\nKaynak Topic: `{src['topic']}`\nBaşlangıç Mesajı: `{src['msg']}`")
        asyncio.create_task(run_transfer(client, uid, src, link_data, message))

# ==================== TRANSFER MOTORU (TOPIC TARAMALI) ====================
async def run_transfer(main_client, uid, src, dst, status_msg):
    start_msg_id = src['msg']
    topic_id = src['topic'] # Kaynak Topic ID'si (Varsa)
    
    worker_index = 0
    
    # === İŞTE ÇÖZÜM BURADA: get_chat_history İLE LİSTE ALIYORUZ ===
    # Tek tek denemek yerine, Telegram'dan o konudaki mesajların listesini istiyoruz.
    # Bu sayede boşluklara takılmıyoruz.
    
    try:
        # Geçmişi al (Eskiden yeniye doğru)
        # topic_id varsa oraya odaklan, yoksa genel sohbete
        # offset_id=start_msg_id diyerek o mesajdan öncesini değil sonrasını alıyoruz
        
        # NOT: Pyrogram get_chat_history tersten gelir (Yeni -> Eski).
        # Biz Eskiden -> Yeniye gitmek istiyoruz.
        # O yüzden reverse=True yapıyoruz.
        
        msg_buffer = [] # Mesajları burada biriktirip sıraya koyacağız
        
        async for msg in main_client.get_chat_history(
            chat_id=src['id'], 
            limit=0, # Limit yok, hepsini al
            from_message_id=start_msg_id, # Buradan başla
            # Eğer topic varsa reply_to_message_id topic ID'si olur (Forum konularında)
            # Pyrogram'da topic filtrelemesi biraz karışıktır, en garantisi tümünü alıp filtrelemektir.
        ):
            # LİSTELEME MANTIĞI:
            # get_chat_history, from_message_id'den ESKİYE doğru gider.
            # Biz YENİYE doğru gitmek istiyoruz.
            # Bu yüzden strateji şu:
            # 1. Döngüyü kır.
            # 2. Generator kullanamayız çünkü yön ters.
            # 3. Manuel tarama yapacağız (V102 mantığı ama Topic filtreli).
            break # Bu yöntem çalışmadı, manuel metoda dönüyoruz.

    except: pass

    # === MANUEL TARAMA (TOPIC FİLTRELİ) ===
    current_id = start_msg_id
    empty_streak = 0
    
    while True:
        if user_state.get(uid, {}).get("stop", False):
            await status_msg.reply_text("🛑 Durduruldu.")
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
            except: pass

            # BOŞLUK KONTROLÜ
            if msg is None or msg.empty:
                empty_streak += 1
                if empty_streak % 100 == 0:
                    try: await status_msg.edit_text(f"⚠️ **Boşluk Taranıyor:** `{current_id}`")
                    except: pass
                
                if empty_streak > 500: # 500 Mesaj boşsa dur
                    await status_msg.reply_text(f"🏁 **Bitti!** Son ID: `{current_id}`")
                    break
                current_id += 1
                continue
            
            empty_streak = 0 # Mesaj var, sayacı sıfırla

            # === TOPIC KONTROLÜ (EN ÖNEMLİ YER) ===
            # Eğer kaynak linkinde Topic ID varsa, gelen mesajın o konuya ait olup olmadığına bak.
            # Forumlarda mesajlar bir "Topic"e aittir. Bu bilgi "message_thread_id" veya "reply_to_message_id" içindedir.
            
            is_same_topic = True
            if topic_id:
                msg_topic = getattr(msg, "message_thread_id", None) or getattr(msg, "reply_to_message_id", None)
                
                # Bazen top mesajın (kurucu mesajın) kendisi topic ID'ye eşittir.
                if msg.id == topic_id: 
                    msg_topic = topic_id
                
                # Eğer mesajın topic'i bizim istediğimiz topic değilse ATLA
                if msg_topic != topic_id:
                    # Bu mesaj başka konuya ait, ama ID akışı devam ediyor.
                    # O yüzden durmuyoruz, sadece bu mesajı işlemiyoruz.
                    current_id += 1
                    continue

            # TRANSFER İŞLEMİ
            if msg.media or msg.text:
                if current_id % 5 == 0:
                    try: await status_msg.edit_text(f"🔄 **İşleniyor:** `{current_id}`")
                    except: pass
                
                success = await download_and_upload(worker, msg, dst['id'], dst['topic'])
                
                if success: await asyncio.sleep(2) 
                else: await asyncio.sleep(5)
                    
            current_id += 1

        except Exception as e:
            logger.error(f"Hata: {e}")
            await asyncio.sleep(5)

# ==================== BAŞLATMA ====================
async def start_services():
    for c in clients: await c.start()
    print("✅ Hazır")
    port = int(os.environ.get("PORT", 8080))
    await app_web.run_task(host="0.0.0.0", port=port)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
