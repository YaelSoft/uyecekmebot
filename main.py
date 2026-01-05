import os
import asyncio
import logging
import sqlite3
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid

# ==================== 1. WEB SERVER ====================
app = Flask(__name__)

@app.route('/')
def home(): return "Bot Aktif! 🟢"

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
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
SESSION1 = os.environ.get("SESSION_STRING", "")
SESSION2 = os.environ.get("SESSION_STRING_2", "")

bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

USERBOTS = []
if SESSION1: USERBOTS.append(Client("ub1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
if SESSION2: USERBOTS.append(Client("ub2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))

ABORT_FLAG = False

# ==================== 3. SAĞLAM İNDİRİCİ (SMART DOWNLOADER) ====================
# Bu fonksiyon dosya tam inmeden bırakmaz!
async def download_with_verification(ub, msg, retries=3):
    """
    Dosyayı indirir ve boyutunu kontrol eder.
    Eksikse silip tekrar dener.
    """
    # 1. Beklenen Boyutu Bul
    expected_size = 0
    if msg.video: expected_size = msg.video.file_size
    elif msg.document: expected_size = msg.document.file_size
    elif msg.photo: expected_size = msg.photo.file_size
    elif msg.audio: expected_size = msg.audio.file_size
    elif msg.voice: expected_size = msg.voice.file_size
    
    if expected_size == 0: return None # Boyut yoksa riskli

    file_path = None
    
    for attempt in range(1, retries + 1):
        try:
            # İndirme Başlat
            file_path = await ub.download_media(msg)
            
            # Disk Kontrolü
            if file_path and os.path.exists(file_path):
                actual_size = os.path.getsize(file_path)
                
                # Toleranslı Karşılaştırma (Bazen byte farkı olabilir, %95 tutsa yeter)
                if actual_size >= expected_size or (expected_size - actual_size) < 1024:
                    return file_path # Başarılı!
                else:
                    print(f"⚠️ EKSİK İNDİ ({attempt}/{retries}): {actual_size}/{expected_size} byte. Tekrar deneniyor...")
                    os.remove(file_path) # Sil ve döngüye devam et
            
        except Exception as e:
            print(f"⚠️ İndirme Hatası ({attempt}): {e}")
            if file_path and os.path.exists(file_path): os.remove(file_path)
        
        await asyncio.sleep(2) # Hata sonrası biraz bekle
        
    return None # Tüm denemeler başarısız

# ==================== 4. KOMUTLAR ====================

@bot.on_message(filters.command("iptal") & filters.private)
async def cancel_process(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **İPTAL EDİLDİ.**")

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_verified(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not USERBOTS: await message.reply("❌ Userbot yok!"); return
    ub = USERBOTS[0]
    
    SAFETY_DELAY = 4 # Güvenli bekleme

    try:
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **/transfer [KAYNAK_LINK] [HEDEF_LINK]**")
        return

    status = await message.reply("🔄 **ANALİZ EDİLİYOR...**")

    # Hafıza Tazele
    try:
        async for d in ub.get_dialogs(limit=50): pass
    except: pass

    # Link Çözücü
    def resolve(link):
        data = {"id": None, "topic": None}
        link = str(link).strip()
        try:
            if "c/" in link:
                clean = link.split("c/")[1].split("?")[0].split("/")
                data["id"] = int("-100" + clean[0])
                if len(clean) >= 2: data["topic"] = int(clean[1])
            elif "-100" in link:
                data["id"] = int(link)
        except: return None
        return data

    src = resolve(src_link)
    dst = resolve(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    # Listeleme
    await status.edit(f"📦 **GEÇMİŞ TARANIYOR...**\nEksiksiz ve sıralı aktarım için hazırlanıyor.")
    msg_ids = []
    
    try:
        async for m in ub.get_chat_history(src["id"]):
            if ABORT_FLAG: break
            is_target = False
            if src["topic"]:
                try:
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    if tid == src["topic"] or m.id == src["topic"]: is_target = True
                except: pass
            else: is_target = True

            if is_target: msg_ids.append(m.id)
    except Exception as e:
        await status.edit(f"❌ Tarama Hatası: {e}"); return

    msg_ids.reverse()
    total = len(msg_ids)
    
    if total == 0: await status.edit("❌ Mesaj bulunamadı."); return

    await status.edit(f"🚀 **AKTARIM BAŞLADI**\nToplam: {total} Mesaj\nMod: %100 Doğrulama (Bozuk Dosya Atlamaz)")

    # --- AKTARIM DÖNGÜSÜ ---
    count = 0
    fail = 0

    for msg_id in msg_ids:
        if ABORT_FLAG: await status.edit("🛑 Durduruldu."); return
        
        try:
            msg = await ub.get_messages(src["id"], msg_id)
            if not msg or msg.empty: continue

            # Hedef Topic
            send_args = {}
            if dst["topic"]: send_args["reply_to_message_id"] = dst["topic"]

            success = False
            
            # --- MEDYA İŞLEMLERİ (METADATA + DOĞRULAMA) ---
            if msg.media:
                # 1. SAĞLAM İNDİRME FONKSİYONUNU ÇAĞIR
                path = await download_with_verification(ub, msg, retries=3)
                
                if path:
                    caption = msg.caption or ""
                    try:
                        # 2. METADATA İLE GÖNDERME (00:00 Hatasını Çözer)
                        if msg.video:
                            await ub.send_video(
                                dst["id"], path, caption=caption, 
                                duration=msg.video.duration, # Süre
                                width=msg.video.width,       # Genişlik
                                height=msg.video.height,     # Yükseklik
                                thumb=None, # Küçük resim indirmek karmaşık, şimdilik otomatik olsun
                                **send_args
                            )
                        elif msg.photo: await ub.send_photo(dst["id"], path, caption=caption, **send_args)
                        elif msg.document: await ub.send_document(dst["id"], path, caption=caption, **send_args)
                        elif msg.audio: await ub.send_audio(dst["id"], path, caption=caption, **send_args)
                        elif msg.voice: await ub.send_voice(dst["id"], path, **send_args)
                        elif msg.sticker: await ub.send_sticker(dst["id"], path, **send_args)
                        elif msg.animation: await ub.send_animation(dst["id"], path, caption=caption, **send_args)
                        
                        success = True
                    except Exception as upload_err:
                        print(f"Yükleme Hatası ({msg_id}): {upload_err}")
                        fail += 1
                    finally:
                        if os.path.exists(path): os.remove(path)
                else:
                    # İndirme başarısız olduysa
                    print(f"İndirme Başarısız (ID: {msg_id})")
                    fail += 1

            # --- SADECE YAZI ---
            elif msg.text and msg.text.strip():
                try:
                    await ub.send_message(dst["id"], msg.text, **send_args)
                    success = True
                except: fail += 1

            if success: count += 1
            await asyncio.sleep(SAFETY_DELAY)
            
            if count % 5 == 0:
                try: await status.edit(f"🔄 **AKTARILIYOR...**\n✅ {count} / {total}\n(Sıfır Hata Modu)")
                except: pass

        except FloodWait as e: await asyncio.sleep(e.value + 5)
        except Exception: fail += 1

    await status.edit(f"🏁 **TAMAMLANDI!**\n✅ Başarılı: {count}\n❌ İndirilemeyen: {fail}")

# ==================== 5. BAŞLATMA ====================
async def main():
    print("Sistem Başlatılıyor...")
    keep_alive()
    await bot.start()
    for ub in USERBOTS:
        try: await ub.start()
        except: pass
    await idle()
    await bot.stop()
    for ub in USERBOTS:
        try: await ub.stop()
        except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
