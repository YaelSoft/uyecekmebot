import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid

# ==================== WEB SERVER ====================
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

# ==================== AYARLAR ====================
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

# ==================== HATA ÇÖZÜCÜLER ====================

async def force_find_chat(chat_id):
    """
    Kanalı bulmak için 3 aşamalı tarama yapar:
    1. Direkt ID (-100'lü)
    2. Düz ID (-100'süz)
    3. Tüm liste taraması (Garanti Yöntem)
    """
    # 1. Aşama: Direkt Dene
    try:
        return await userbot.get_chat(chat_id)
    except:
        pass # Hata verirse devam et

    # 2. Aşama: ID Formatını Değiştirip Dene
    try:
        # Eğer -100 ile başlıyorsa, silip dene
        alt_id = int(str(chat_id).replace("-100", ""))
        return await userbot.get_chat(alt_id)
    except:
        pass

    # 3. Aşama: Manuel Liste Taraması (LIMITSIZ)
    logger.info(f"⚠️ Kanal ({chat_id}) direkt bulunamadı, TÜM liste taranıyor...")
    
    chat_str = str(chat_id).replace("-100", "") # Karşılaştırma için temiz ID
    
    async for dialog in userbot.get_dialogs(): # LİMİT YOK! Hepsini tarar.
        d_id = str(dialog.chat.id).replace("-100", "")
        
        # ID Eşleşmesi
        if d_id == chat_str:
            logger.info(f"✅ Kanal bulundu (Liste Taraması): {dialog.chat.title}")
            return dialog.chat
            
        # Username Eşleşmesi (Eğer link username ise)
        if isinstance(chat_id, str) and dialog.chat.username:
            if dialog.chat.username.lower() == chat_id.replace("@", "").lower():
                return dialog.chat

    # Bulunamazsa loglara bas (Render loglarından görürsün)
    logger.error(f"❌ KANAL BULUNAMADI! Aranan ID: {chat_id}")
    raise ValueError("Userbot bu kanalı listesinde bulamadı! Üye olduğuna emin misin?")

def resolve_link(link):
    """Linkten ID'leri ayıklar (Hatasız)"""
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private: c/123456/100
            # Link c/123456/.. ise ID -100123456'dır.
            clean_parts = link.split("c/")[1].split("?")[0].split("/")
            raw_id = clean_parts[0]
            data["id"] = int("-100" + raw_id)
            
            # Mesaj ve Topic tespiti
            if len(clean_parts) >= 2:
                data["msg_id"] = int(clean_parts[-1]) # Son parça her zaman Mesaj ID
                if len(clean_parts) > 2:
                    data["topic_id"] = int(clean_parts[1]) # Ortadaki parça Topic ID
                    
        else: # Public: username/100
            data["id"] = parts[0]
            if len(parts) >= 2:
                data["msg_id"] = int(parts[1])
    except:
        return None
        
    return data

async def download_with_verification(ub, msg, retries=3):
    """Sağlam İndirici"""
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
                if actual_size >= expected_size * 0.95:
                    return file_path
                else:
                    os.remove(file_path)
        except:
            if file_path and os.path.exists(file_path): os.remove(file_path)
        await asyncio.sleep(2)
    return None

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply(
        "👋 **Yael Saver Bot (Full Access)**\n\n"
        "✅ `PeerIdInvalid` Fix (Limitsiz Tarama)\n"
        "✅ `Topic` Desteği\n"
        "✅ `İletim Kısıtlı` Desteği\n\n"
        "**Nasıl Kullanılır?**\n"
        "1️⃣ Kaynak linki al (sonundaki sayıları silersen hepsini çeker)\n"
        "2️⃣ `/transfer KAYNAK HEDEF` yaz.\n"
        "Örn: `/transfer https://t.me/c/123456 https://t.me/hedef`"
    )

@bot.on_message(filters.command("iptal"))
async def cancel_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **İşlem durduruldu.**")

@bot.on_message(filters.command("tekli"))
async def single_download(client, message):
    try:
        link = message.command[1]
        data = resolve_link(link)
    except:
        await message.reply("❌ Link hatalı.")
        return

    status = await message.reply("🔄 **Aranıyor...**")

    try:
        chat = await force_find_chat(data["id"])
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya yok.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_with_verification(userbot, msg)
        
        await status.edit("📤 **Yükleniyor...**")
        
        caption = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=caption)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=caption)
        
        os.remove(path)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

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

    status = await message.reply("🔄 **Kanallar aranıyor (Detaylı Tarama)...**")

    try:
        # Linkleri Çöz
        src_data = resolve_link(src_link)
        dst_data = resolve_link(dst_link)

        # Kanalları Bul (Zorla)
        try:
            src_chat = await force_find_chat(src_data["id"])
            dst_chat = await force_find_chat(dst_data["id"])
        except ValueError as ve:
            await status.edit(f"❌ **Kanal Bulunamadı!**\n{ve}\n\n*Çözüm:* Userbot ile o gruba girip bir mesaj yazın veya okuyun.")
            return

        await status.edit(f"📦 **Mesajlar Toplanıyor...**\nKaynak: {src_chat.title}\nHedef: {dst_chat.title}")
        
        msg_list = []
        
        # En Yeniden -> En Eskiye tarar
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic Filtresi
            if src_data["topic_id"]:
                t_id = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if t_id != src_data["topic_id"]: continue

            # Başlangıç Mesajı Kontrolü
            # Bizim istediğimiz: Verilen ID (500) ve SONRASI (501, 502...).
            # get_chat_history 1000, 999, 998... diye gelir.
            # Eğer gelen mesaj (499), bizim başlangıçtan (500) küçükse dur.
            if src_data["msg_id"] and m.id < src_data["msg_id"]:
                break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        # Listeyi Ters Çevir (Eskiden -> Yeniye)
        msg_list.reverse()
        total_msgs = len(msg_list)
        
        if total_msgs == 0:
            await status.edit("❌ Medya bulunamadı.")
            return

        baslangic_bilgisi = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Transfer Başlıyor!**\n📝 Dosya: {total_msgs}\n📍 Konum: {baslangic_bilgisi}")

        count = 0
        for mid in msg_list:
            if ABORT_FLAG:
                await status.edit("🛑 Durduruldu.")
                return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg or msg.empty: continue

                path = await download_with_verification(userbot, msg)
                if not path: continue

                # Hedef Topic Ayarı
                send_args = {}
                if dst_data["msg_id"]: send_args["reply_to_message_id"] = dst_data["msg_id"]
                elif dst_data["topic_id"]: send_args["reply_to_message_id"] = dst_data["topic_id"]

                caption = msg.caption or ""
                if msg.video:
                    await userbot.send_video(dst_chat.id, video=path, caption=caption, duration=msg.video.duration, **send_args)
                elif msg.photo:
                    await userbot.send_photo(dst_chat.id, photo=path, caption=caption, **send_args)
                elif msg.document:
                    await userbot.send_document(dst_chat.id, document=path, caption=caption, **send_args)

                count += 1
                os.remove(path)

                if count % 5 == 0:
                    try: await status.edit(f"🔄 **Aktarım:** {count}/{total_msgs}")
                    except: pass
                
                await asyncio.sleep(4)

            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                logger.error(f"Err: {e}")
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **BİTTİ!** Toplam {count} dosya.")

    except Exception as e:
        await status.edit(f"❌ Genel Hata: {e}")

# ==================== BAŞLATMA ====================
async def main():
    logger.info("Botlar başlatılıyor...")
    keep_alive()
    await bot.start()
    await userbot.start()
    
    logger.info("♻️ Kanal Listesi (Sınırsız) Taranıyor...")
    # Sadece bir kere tüm listeyi çekip Pyrogram önbelleğine atıyoruz
    # Limit yok, hepsini gezer.
    async for d in userbot.get_dialogs(): pass
    
    logger.info("✅ Sistem Hazır!")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
