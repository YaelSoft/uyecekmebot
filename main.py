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
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Aktif! 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False

# ==================== AKILLI KANAL BULUCU (LINK GEREKTİRMEZ) ====================

async def smart_find_chat(target_id_str):
    """
    Kullanıcının verdiği ID (örn: 1555999) ile Userbot'un listesindeki
    ID'leri (-1001555999) karşılaştırır. Eşleşirse Chat objesini döner.
    """
    target_clean = str(target_id_str).replace("-100", "").replace("-", "")
    
    logger.info(f"🔍 Kanal aranıyor... Hedef ID (Temiz): {target_clean}")
    
    # Userbot'un tüm sohbetlerini gez
    async for dialog in userbot.get_dialogs():
        current_id = str(dialog.chat.id)
        current_clean = current_id.replace("-100", "").replace("-", "")
        
        # 1. ID Numarası Tutuyor mu?
        if current_clean == target_clean:
            logger.info(f"✅ BULUNDU! ID Eşleşti: {dialog.chat.title}")
            return dialog.chat
            
        # 2. Username Tutuyor mu? (Eğer ID string ise)
        if dialog.chat.username and str(target_id_str).replace("@","").lower() == dialog.chat.username.lower():
            logger.info(f"✅ BULUNDU! Username Eşleşti: {dialog.chat.title}")
            return dialog.chat

    logger.error("❌ Eşleşme bulunamadı.")
    return None

def resolve_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private (c/123456/100)
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = clean[0] # String olarak alıyoruz ki smart_find eşleştirsin
            
            if len(clean) == 2:
                data["msg_id"] = int(clean[1])
            elif len(clean) == 3:
                data["topic_id"] = int(clean[1])
                data["msg_id"] = int(clean[2])
                
        else: # Public
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
            if len(parts) >= 3: data["topic_id"] = int(parts[1]); data["msg_id"] = int(parts[2])
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
async def start_handler(client, message):
    await message.reply(
        "👋 **Yael Saver (Körlük Giderildi)**\n\n"
        "Artık link istemiyorum. Userbot grubun içindeyse, ID'den tanırım.\n\n"
        "🛠 **Araçlar:**\n"
        "🔹 `/listele` -> Userbot'un gördüğü grupları listeler.\n"
        "🔹 `/transfer <KAYNAK> <HEDEF>`\n"
        "🔹 `/tekli <LINK>`"
    )

@bot.on_message(filters.command("iptal"))
async def cancel_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 Durdu.")

# --- YENİ KOMUT: LİSTELE ---
@bot.on_message(filters.command("listele"))
async def listele_handler(client, message):
    """Userbot'un gördüğü son 50 grubu listeler"""
    status = await message.reply("🔍 **Grup listen çekiliyor...**")
    text = "**📂 Görünen Gruplar (Userbot):**\n\n"
    count = 0
    try:
        async for dialog in userbot.get_dialogs(limit=50):
            if dialog.chat.title:
                # ID'yi temizleyip gösterelim ki kullanıcı kontrol etsin
                clean_id = str(dialog.chat.id).replace("-100", "")
                text += f"🔹 **{dialog.chat.title}**\n🆔 `{clean_id}`\n\n"
                count += 1
        
        if count == 0:
            await status.edit("❌ Userbot hiç grup görmüyor! Session hatalı olabilir mi?")
        else:
            # Mesaj çok uzunsa bölmek gerekir ama şimdilik tek atalım
            if len(text) > 4000: text = text[:4000] + "... (liste devam ediyor)"
            await status.edit(text)
            
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- TEKLİ İNDİRME ---
@bot.on_message(filters.command("tekli"))
async def tekli_cmd(client, message):
    try: link = message.command[1]; data = resolve_link(link)
    except: await message.reply("❌ Link gir."); return

    status = await message.reply("🔄 **Akıllı Arama Yapılıyor...**")

    try:
        # ID Eşleştirme Yapıyoruz
        chat = await smart_find_chat(data["id"])
        
        if not chat:
            await status.edit(f"❌ **Kanal Bulunamadı!**\nUserbot `{data['id']}` ID'li grupta görünmüyor.\n`/listele` yazarak kontrol et.")
            return

        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya yok veya mesaj silinmiş.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_safe(userbot, msg)
        
        await status.edit("📤 **Yükleniyor...**")
        caption = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=caption)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=caption)
        os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- TRANSFER ---
@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Gruplar Eşleştiriliyor...**")

    try:
        src_data = resolve_link(src_link)
        dst_data = resolve_link(dst_link)
        
        # 1. KAYNAK BUL
        src_chat = await smart_find_chat(src_data["id"])
        if not src_chat:
            await status.edit(f"❌ **KAYNAK BULUNAMADI!**\nID: `{src_data['id']}`\nUserbot bu grupta değil mi? `/listele` yaz.")
            return

        # 2. HEDEF BUL
        dst_chat = await smart_find_chat(dst_data["id"])
        if not dst_chat:
            await status.edit(f"❌ **HEDEF BULUNAMADI!**\nID: `{dst_data['id']}`")
            return

        baslangic = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Transfer Başlıyor!**\nK: {src_chat.title}\nH: {dst_chat.title}\nMod: {baslangic}")

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic Filtresi
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
                
                s_args = {}
                # Hedef Topic
                target_top = dst_data["msg_id"] or dst_data["topic_id"]
                if target_top: s_args["reply_to_message_id"] = target_top

                cap = msg.caption or ""
                if msg.video: await userbot.send_video(dst_chat.id, video=path, caption=cap, duration=msg.video.duration, **s_args)
                elif msg.photo: await userbot.send_photo(dst_chat.id, photo=path, caption=cap, **s_args)
                elif msg.document: await userbot.send_document(dst_chat.id, document=path, caption=cap, **s_args)
                
                count += 1
                os.remove(path)
                
                if count % 5 == 0:
                    try: await status.edit(f"🔄 **Aktarım:** {count}/{total}")
                    except: pass
                await asyncio.sleep(4)

            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **Tamamlandı!** {count} dosya.")

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    
    # Başlangıçta listeyi çekip RAM'e alalım
    print("Liste güncelleniyor...")
    async for d in userbot.get_dialogs(): pass
    
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
