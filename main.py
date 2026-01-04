import os
import asyncio
import logging
import sqlite3
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid

# ==================== 1. WEB SERVER (RENDER İÇİN) ====================
app = Flask(__name__)

@app.route('/')
def home(): return "Bot Çalışıyor! 🟢"

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

# Session Stringleri Çek
SESSION1 = os.environ.get("SESSION_STRING", "")
SESSION2 = os.environ.get("SESSION_STRING_2", "")

# Botu Başlat
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

USERBOTS = []
if SESSION1: USERBOTS.append(Client("ub1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
if SESSION2: USERBOTS.append(Client("ub2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))

# ==================== 3. İPTAL MEKANİZMASI ====================
ABORT_FLAG = False

@bot.on_message(filters.command("iptal") & filters.private)
async def cancel_process(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **İPTAL SİNYALİ GÖNDERİLDİ!**\nMevcut dosya biter bitmez işlem duracak.")

# ==================== 4. FULL TOPIC TRANSFER (V45) ====================
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_topic_full(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not USERBOTS: await message.reply("❌ Userbot yok!"); return
    ub = USERBOTS[0]
    
    # Güvenli Gecikme (Ban Yememek İçin)
    SAFETY_DELAY = 4 

    try:
        # KOMUT: /transfer [KAYNAK_LINK] [HEDEF_LINK]
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **KULLANIM:** `/transfer [KAYNAK_KONU_LINKI] [HEDEF_KONU_LINKI]`")
        return

    status = await message.reply("🔄 **BAĞLANTI KURULUYOR...**")

    # --- HAFIZA TAZELEME (PeerIdInvalid Fix) ---
    try:
        async for d in ub.get_dialogs(limit=50): pass
    except: pass

    # --- LİNK ÇÖZÜCÜ ---
    def resolve(link):
        data = {"id": None, "topic": None}
        link = str(link).strip()
        try:
            if "c/" in link:
                clean = link.split("c/")[1].split("?")[0].split("/")
                data["id"] = int("-100" + clean[0])
                # Topic ID'yi alıyoruz
                if len(clean) >= 2: data["topic"] = int(clean[1])
            elif "-100" in link:
                data["id"] = int(link)
        except: return None
        return data

    src = resolve(src_link)
    dst = resolve(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    # --- LİSTELEME (HEPSİNİ ÇEKME) ---
    await status.edit(f"📦 **KONU TARANIYOR...**\nLinkteki mesaj ne olursa olsun, konunun **EN BAŞINDAN** başlanacak.")

    msg_ids = []
    
    try:
        # Tüm grubu çekiyoruz (Hata vermemesi için)
        async for m in ub.get_chat_history(src["id"]):
            if ABORT_FLAG: break
            
            # --- KONU FİLTRESİ ---
            is_target = False
            
            if src["topic"]:
                try:
                    # Mesaj bu konuya mı ait?
                    # Hem yeni (thread_id) hem eski (reply_to) kontrolü
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    
                    if tid == src["topic"]: is_target = True 
                    elif m.id == src["topic"]: is_target = True # Konu başlığı
                except: pass
            else:
                is_target = True # Topic yoksa hepsini al

            if is_target:
                msg_ids.append(m.id)

    except Exception as e:
        await status.edit(f"❌ **TARAMA HATASI:** {e}\n(Bot grupta mı?)"); return

    # --- SIRALAMA (ESKİDEN YENİYE) ---
    msg_ids.reverse() 
    
    total = len(msg_ids)
    if total == 0: 
        await status.edit("❌ **MESAJ BULUNAMADI.** Konu ID yanlış olabilir."); return

    await status.edit(f"🚀 **AKTARIM BAŞLADI**\nToplam: {total} Mesaj\nSıra: Eskiden -> Yeniye\nMod: Temiz Yükleme (Etiketsiz)")

    # --- AKTARIM DÖNGÜSÜ ---
    count = 0
    fail = 0

    for msg_id in msg_ids:
        if ABORT_FLAG: 
            await status.edit("🛑 **KULLANICI İSTEĞİYLE DURDURULDU.**"); return
        
        try:
            msg = await ub.get_messages(src["id"], msg_id)
            if not msg or msg.empty: continue

            # Hedef Topic Ayarı
            send_args = {}
            if dst["topic"]: send_args["reply_to_message_id"] = dst["topic"]

            success = False
            
            # --- MEDYA İŞLEMLERİ ---
            if msg.media:
                path = None
                try:
                    # İndir
                    path = await ub.download_media(msg)
                    
                    # 0MB KONTROLÜ (Dosya var mı ve boyutu 0'dan büyük mü?)
                    if path and os.path.exists(path) and os.path.getsize(path) > 0:
                        
                        caption = msg.caption or ""
                        # Temiz Yükleme (Forward değil, Upload)
                        if msg.photo: await ub.send_photo(dst["id"], path, caption=caption, **send_args)
                        elif msg.video: await ub.send_video(dst["id"], path, caption=caption, **send_args)
                        elif msg.document: await ub.send_document(dst["id"], path, caption=caption, **send_args)
                        elif msg.audio: await ub.send_audio(dst["id"], path, caption=caption, **send_args)
                        elif msg.voice: await ub.send_voice(dst["id"], path, **send_args)
                        elif msg.sticker: await ub.send_sticker(dst["id"], path, **send_args)
                        elif msg.animation: await ub.send_animation(dst["id"], path, caption=caption, **send_args)
                        
                        success = True
                    else:
                        print(f"Hata: Dosya boş indi (ID: {msg_id})")
                        fail += 1
                except Exception as e:
                    print(f"Medya Hatası: {e}")
                    fail += 1
                finally:
                    # Dosyayı sil
                    if path and os.path.exists(path): os.remove(path)
            
            # --- SADECE YAZI ---
            elif msg.text and msg.text.strip():
                try:
                    await ub.send_message(dst["id"], msg.text, **send_args)
                    success = True
                except: fail += 1

            if success: count += 1
            
            # Bekleme (Ban Koruması)
            await asyncio.sleep(SAFETY_DELAY)
            
            if count % 5 == 0:
                try: await status.edit(f"🔄 **AKTARILIYOR...**\n✅ {count} / {total}")
                except: pass

        except FloodWait as e:
            await asyncio.sleep(e.value + 5)
        except Exception: 
            fail += 1
            pass

    await status.edit(f"🏁 **TAMAMLANDI!**\n✅ Başarılı: {count}\n❌ Hatalı/Atlanan: {fail}")

# ==================== 5. BAŞLATMA ====================
async def main():
    print("Sistem Başlatılıyor...")
    keep_alive() # Web Server Başlat
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
