import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SaverBot")

# Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Calisiyor 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} # Hafıza Deposu

# ==================== ZEKA VE HAFIZA ====================

async def cache_all_chats():
    """Bot açılınca tüm grupları buraya kaydeder"""
    global CHAT_CACHE
    logger.info("🧠 HAFIZA: Sohbetler taranıyor (Bu işlem biraz sürebilir)...")
    count = 0
    try:
        async for dialog in userbot.get_dialogs():
            # Hem normal ID hem temiz ID (-100'süz) olarak kaydet
            raw_id = str(dialog.chat.id)
            clean_id = raw_id.replace("-100", "").replace("-", "")
            
            CHAT_CACHE[raw_id] = dialog.chat
            CHAT_CACHE[clean_id] = dialog.chat
            
            if dialog.chat.username:
                CHAT_CACHE[dialog.chat.username.lower()] = dialog.chat
            count += 1
    except Exception as e:
        logger.error(f"Tarama hatası: {e}")
        
    logger.info(f"✅ HAFIZA: {count} sohbet kaydedildi. Artık bot kör değil.")

async def get_chat_smart(chat_input):
    """Hafızadan bulur, yoksa Telegram'a sorar"""
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0] # c/1234/55 -> 1234
    
    # 1. Hafızada var mı?
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    # 2. Direkt ID mi?
    try: return await userbot.get_chat(int(target))
    except: pass
    try: return await userbot.get_chat(int("-100" + target))
    except: pass
    
    # 3. Bulunamadı -> Listeyi Yenile ve Tekrar Bak
    logger.info("⚠️ Kanal hafızada yok, yenileniyor...")
    await cache_all_chats()
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    return None

def parse_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private Link
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

async def download_safe(ub, msg):
    try:
        path = await ub.download_media(msg)
        if path and os.path.getsize(path) > 0: return path
    except: pass
    return None

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    # Resim yok, sadece yazı. Donma yapmaz.
    await message.reply(
        "✅ **Bot Aktif ve Hazır!**\n\n"
        "Userbot tüm sohbetleri hafızaya aldı.\n"
        "Link atınca tanımama şansı yok.\n\n"
        "🔹 `/getmedia <LINK>` -> Tekli İndir\n"
        "🔹 `/transfer <KAYNAK> <HEDEF>` -> Toplu Aktar\n"
        "🔹 `/iptal` -> Durdur"
    )

@bot.on_message(filters.command("iptal"))
async def stop_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 İşlem durduruldu.")

# --- TEKLİ İNDİRME (/getmedia) ---
@bot.on_message(filters.command("getmedia"))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("❌ Link gir."); return

    status = await message.reply("🔍 **Hafızadan aranıyor...**")
    
    data = parse_link(link)
    if not data or not data["msg_id"]:
        await status.edit("❌ Link bozuk. Mesaj ID'si yok.")
        return

    chat = await get_chat_smart(data["id"])
    if not chat:
        await status.edit(f"❌ **BULUNAMADI!**\nUserbot ID `{data['id']}` olan grupta değil.")
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya yok.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_safe(userbot, msg)
        
        await status.edit("📤 **Gönderiliyor...**")
        cap = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        os.remove(path)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- TOPLU TRANSFER (/transfer) ---
@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Kontrol ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)

        src_chat = await get_chat_smart(src_data["id"])
        if not src_chat: await status.edit("❌ Kaynak grup bulunamadı!"); return
        
        dst_chat = await get_chat_smart(dst_data["id"])
        if not dst_chat: await status.edit("❌ Hedef grup bulunamadı!"); return

        start_msg = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Başlıyor!**\nK: {src_chat.title}\nH: {dst_chat.title}\nMod: {start_msg}")

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic ve ID Filtreleri
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0: await status.edit("❌ Medya yok."); return

        count = 0
        await status.edit(f"📥 **Aktarım: 0/{total}**")

        for mid in msg_list:
            if ABORT_FLAG: await status.edit("🛑 Durdu."); return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                path = await download_safe(userbot, msg)
                if not path: continue

                # Hedef Topic
                s_args = {}
                target_top = dst_data["msg_id"] or dst_data["topic_id"]
                if target_top: s_args["reply_to_message_id"] = target_top

                cap = msg.caption or ""
                if msg.video: await userbot.send_video(dst_chat.id, video=path, caption=cap, duration=msg.video.duration, **s_args)
                elif msg.photo: await userbot.send_photo(dst_chat.id, photo=path, caption=cap, **s_args)
                elif msg.document: await userbot.send_document(dst_chat.id, document=path, caption=cap, **s_args)
                
                count += 1
                os.remove(path)
                
                if count % 5 == 0:
                    try: await status.edit(f"🔄 **{count}/{total}**")
                    except: pass
                await asyncio.sleep(4)
            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **Bitti:** {count} dosya.")
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== ANA ÇALIŞTIRMA (TARAMA BURADA) ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    
    # --- İŞTE BURASI TARAMA YAPIYOR ---
    # Bot her açıldığında bunu yapar.
    await cache_all_chats() 
    # ----------------------------------
    
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
