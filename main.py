import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid

# ==================== 1. WEB SERVER (RENDER İÇİN) ====================
app = Flask(__name__)

@app.route('/')
def home(): return "Yael Saver Bot Aktif! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== 2. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# Bot Tanımları
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False

# ==================== 3. YARDIMCI FONKSİYONLAR ====================

async def force_find_chat(chat_id):
    """
    PeerIdInvalid hatasını çözmek için Userbot'un sohbet listesini tarar.
    """
    try:
        # Önce direkt dene
        return await userbot.get_chat(chat_id)
    except:
        logger.info(f"⚠️ Kanal ({chat_id}) direkt bulunamadı, liste taranıyor...")
        async for dialog in userbot.get_dialogs():
            if str(dialog.chat.id) == str(chat_id):
                return dialog.chat
            if isinstance(chat_id, str) and dialog.chat.username:
                if dialog.chat.username.lower() == chat_id.replace("@", "").lower():
                    return dialog.chat
        raise ValueError("Kanal bulunamadı! Userbot bu kanala üye mi?")

def resolve_link(link):
    """
    Linkten Chat ID, Mesaj ID ve Topic ID'yi ayıklar.
    """
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private: c/123456/100
            clean_parts = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = int("-100" + clean_parts[0])
            
            # Topic tespiti (Bazen linkte topic ID'si mesaj ID gibi görünür)
            if len(clean_parts) >= 2:
                data["msg_id"] = int(clean_parts[-1]) # Sondaki her zaman mesaj ID'dir
                if len(clean_parts) > 2:
                    data["topic_id"] = int(clean_parts[1]) # Ortadaki topic olabilir
                    
        else: # Public: username/100
            data["id"] = parts[0]
            if len(parts) >= 2:
                data["msg_id"] = int(parts[1])
    except:
        return None
        
    return data

async def download_with_verification(ub, msg, retries=3):
    """Dosyayı indirir ve boyut doğrulaması yapar."""
    expected_size = 0
    if msg.video: expected_size = msg.video.file_size
    elif msg.photo: expected_size = msg.photo.file_size
    elif msg.document: expected_size = msg.document.file_size
    
    if expected_size == 0: return None

    file_path = None
    for attempt in range(1, retries + 1):
        try:
            file_path = await ub.download_media(msg)
            if file_path and os.path.exists(file_path):
                actual_size = os.path.getsize(file_path)
                if actual_size >= expected_size * 0.95: # %95 doğruluk payı
                    return file_path
                else:
                    os.remove(file_path)
        except Exception as e:
            if file_path and os.path.exists(file_path): os.remove(file_path)
        await asyncio.sleep(2)
    return None

# ==================== 4. KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply(
        "👋 **Merhaba! Ben Yael Saver Bot.**\n\n"
        "İletim kısıtlı kanallardan içerik kopyalayabilirim.\n\n"
        "**Komutlar:**\n"
        "🔹 `/tekli <LINK>` - Tek bir medya indirir.\n"
        "🔹 `/transfer <KAYNAK> <HEDEF>` - Toplu kopyalar.\n"
        "🔹 `/iptal` - İşlemi durdurur.\n\n"
        "ℹ️ *Transfer komutunda kaynak linke mesaj ID eklersen (örn: /100), oradan başlar ve sona kadar gider.*"
    )

@bot.on_message(filters.command("iptal"))
async def cancel_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **İşlem iptal edildi.**")

# --- TEKLİ İNDİRME ---
@bot.on_message(filters.command("tekli"))
async def single_download(client, message):
    try:
        link = message.command[1]
    except:
        await message.reply("❌ Link girmelisin!\nÖrnek: `/tekli https://t.me/c/xxxx/123`")
        return

    status = await message.reply("🔄 **İnceleniyor...**")

    try:
        data = resolve_link(link)
        if not data or not data["msg_id"]:
            await status.edit("❌ Hatalı Link! Mesaj ID'si içermeli.")
            return

        # PeerID Fix
        chat = await force_find_chat(data["id"])
        
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Bu mesajda indirilecek medya yok.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_with_verification(userbot, msg)
        
        if not path:
            await status.edit("❌ İndirme başarısız oldu.")
            return

        await status.edit("📤 **Gönderiliyor...**")
        
        # Bota gönder (Komutu kullanan kişiye)
        caption = msg.caption or ""
        if msg.video:
            await bot.send_video(message.chat.id, video=path, caption=caption)
        elif msg.photo:
            await bot.send_photo(message.chat.id, photo=path, caption=caption)
        elif msg.document:
            await bot.send_document(message.chat.id, document=path, caption=caption)

        os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# --- TOPLU TRANSFER (TOPIC DESTEKLİ) ---
@bot.on_message(filters.command("transfer"))
async def transfer_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try:
        args = message.text.split()
        src_link = args[1]
        dst_link = args[2]
    except:
        await message.reply("❌ **Kullanım:** `/transfer KAYNAK HEDEF`")
        return

    status = await message.reply("🔄 **Kanal Bağlantıları Kontrol Ediliyor...**")

    try:
        # Linkleri Çöz
        src_data = resolve_link(src_link)
        dst_data = resolve_link(dst_link)

        # Kanalları Bul (PeerID Invalid Fix)
        src_chat = await force_find_chat(src_data["id"])
        dst_chat = await force_find_chat(dst_data["id"])

        # Mesaj Listesini Oluştur
        await status.edit("📦 **Mesaj Geçmişi Taranıyor...**\n_Bu işlem mesaj sayısına göre zaman alabilir._")
        
        msg_list = []
        
        # Pyrogram reverse=True desteklemediği için normal çekip biz ters çevireceğiz.
        # Bu sayede Eskiden -> Yeniye doğru atarız.
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Eğer kaynak linkte topic varsa, sadece o topici al
            # Topic ID'si genellikle reply_to_message_id veya message_thread_id'dir.
            if src_data["topic_id"]:
                t_id = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if t_id != src_data["topic_id"]:
                    continue # Başka topic, atla

            # Başlangıç mesajından ESKİSİNİ alma (ID küçüldükçe eskiye gider)
            # Bizim istediğimiz: Verilen ID (örn 500) ve ondan sonrakiler (501, 502...)
            # get_chat_history En Yeniden (örn 1000) başlar geriye gider (999, 998...).
            # Eğer okunan mesajın ID'si, start_id'den küçükse döngüyü kırabiliriz.
            if src_data["msg_id"] and m.id < src_data["msg_id"]:
                break
            
            # Sadece Medya Al
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        # Listeyi Ters Çevir (Eskiden -> Yeniye)
        msg_list.reverse()
        total_msgs = len(msg_list)
        
        if total_msgs == 0:
            await status.edit("❌ Aktarılacak medya bulunamadı.")
            return

        baslangic_bilgisi = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Transfer Başlıyor!**\n\n📝 Toplam: {total_msgs} Medya\n📍 Başlangıç: {baslangic_bilgisi}\n➡️ Yön: Eskiden -> Yeniye")

        success_count = 0
        
        for mid in msg_list:
            if ABORT_FLAG:
                await status.edit("🛑 İşlem durduruldu.")
                return

            try:
                # Mesajı taze çek
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg or msg.empty: continue

                # İNDİR
                file_path = await download_with_verification(userbot, msg)
                if not file_path: continue

                # HEDEF TOPIC AYARI
                send_args = {}
                # Eğer hedef linkte bir mesaj ID varsa, onu topic ID olarak varsayalım
                # (Kullanıcı Topic linki verdiyse linkin sonundaki ID topic ID'sidir)
                if dst_data["msg_id"]: 
                    send_args["reply_to_message_id"] = dst_data["msg_id"]
                elif dst_data["topic_id"]:
                    send_args["reply_to_message_id"] = dst_data["topic_id"]

                # YÜKLE
                caption = msg.caption or ""
                if msg.video:
                    await userbot.send_video(
                        dst_chat.id, video=file_path, caption=caption,
                        duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
                        **send_args
                    )
                elif msg.photo:
                    await userbot.send_photo(dst_chat.id, photo=file_path, caption=caption, **send_args)
                elif msg.document:
                    await userbot.send_document(dst_chat.id, document=file_path, caption=caption, **send_args)

                success_count += 1
                os.remove(file_path) # Sil

                if success_count % 5 == 0:
                    try: await status.edit(f"🔄 **Aktarılıyor...** {success_count}/{total_msgs}")
                    except: pass
                
                await asyncio.sleep(4) # Spam Önlemi

            except FloodWait as fw:
                await asyncio.sleep(fw.value + 5)
            except Exception as e:
                logger.error(f"Transfer Hatası: {e}")
                if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

        await bot.send_message(message.chat.id, f"✅ **BİTTİ!**\nToplam {success_count} medya başarıyla taşındı.")

    except Exception as e:
        await status.edit(f"❌ Kritik Hata: {e}")

# ==================== 5. BAŞLATMA ====================
async def main():
    logger.info("Sistem başlatılıyor...")
    keep_alive()
    
    await bot.start()
    await userbot.start()
    
    logger.info("♻️ Önbellek Yenileniyor (PeerIdInvalid Fix)...")
    try:
        # Dialogları tarayarak ID'leri hafızaya alıyoruz
        async for d in userbot.get_dialogs(limit=200): pass
        logger.info("✅ Sohbet listesi güncellendi!")
    except: pass
    
    logger.info("🤖 Yael Saver Bot Hazır!")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
