import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelPrivate, ChannelInvalid

# ==================== 1. WEB SERVER ====================
app = Flask(__name__)

@app.route('/')
def home(): return "V66 PEER FIX ACTIVE! 🟢"

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

# Yönetici Bot
bot = Client("manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# İşçi Botlar
WORKERS = []
WORKER_STATUS = {} 

if SESSION1: 
    WORKERS.append(Client("w1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
    WORKER_STATUS[0] = 0
if SESSION2: 
    WORKERS.append(Client("w2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))
    WORKER_STATUS[1] = 0

ABORT_FLAG = False

# ==================== 3. HEDEF TARAYICI (DNA KONTROLÜ) ====================
EXISTING_FILES_CACHE = set()

def generate_signature(msg):
    """Dosya kimliği oluşturur"""
    size = 0
    duration = 0
    file_name = "unknown"
    caption_hash = hash(msg.caption) if msg.caption else 0
    
    if msg.video:
        size = msg.video.file_size
        duration = msg.video.duration
        file_name = msg.video.file_name or "vid"
    elif msg.document:
        size = msg.document.file_size
        file_name = msg.document.file_name or "doc"
    elif msg.photo:
        size = msg.photo.file_size
        file_name = "photo" 
    elif msg.audio:
        size = msg.audio.file_size
        duration = msg.audio.duration
        file_name = msg.audio.file_name or "audio"
    elif msg.voice:
        size = msg.voice.file_size
    
    if size == 0 and msg.text:
        return (0, 0, "text", hash(msg.text.strip()))
    
    if size == 0: return None
    return (size, duration, file_name, caption_hash)

# --- YENİ EKLENEN KRİTİK FONKSİYON: ID BULUCU ---
async def force_refresh_peers(worker, target_id):
    """
    Userbot'un dialoglarını gezerek ID'yi tanımasını sağlar.
    PeerIdInvalid hatasının kesin çözümüdür.
    """
    found = False
    try:
        # Önce direkt deniyoruz
        await worker.get_chat(target_id)
        return True
    except:
        # Hata verirse dialogları geziyoruz
        print(f"🔄 ID Tanınmadı ({target_id}), Dialoglar taranıyor...")
        async for dialog in worker.get_dialogs(limit=None): # Limit yok, hepsine bak
            if dialog.chat.id == target_id:
                found = True
                break
    return found

async def scan_target_group(worker, chat_id, topic_id=None):
    """Hedef grubu tarar"""
    EXISTING_FILES_CACHE.clear()
    count = 0
    
    # Erişim Kontrolü (Zorla Tanıtma)
    is_access_ok = await force_refresh_peers(worker, chat_id)
    if not is_access_ok:
        # Son çare: Direkt get_chat_history dene, bazen çalışır
        pass

    try:
        async for msg in worker.get_chat_history(chat_id, limit=3000):
            if topic_id:
                tid = getattr(msg, "message_thread_id", None) or getattr(msg, "reply_to_message_id", None)
                if tid != topic_id and msg.id != topic_id: continue
            
            sig = generate_signature(msg)
            if sig:
                EXISTING_FILES_CACHE.add(sig)
                count += 1
    except Exception as e:
        raise Exception(f"Tarama Hatası: {e}\n(Bot grupta mı? ID: {chat_id})")
            
    return count

# ==================== 4. MOTOR SEÇİCİ ====================
async def get_best_worker():
    while True:
        now = time.time()
        best_idx = -1
        min_wait = float('inf')
        for idx, release_time in WORKER_STATUS.items():
            if now >= release_time: return WORKERS[idx], idx
            else:
                wait = release_time - now
                if wait < min_wait: min_wait = wait; best_idx = idx
        
        if best_idx != -1: await asyncio.sleep(min_wait)
        else: return None, -1

def report_flood(idx, seconds):
    WORKER_STATUS[idx] = time.time() + seconds + 2
    print(f"⚠️ Motor {idx+1} Isındı: {seconds}sn")

# ==================== 5. İNDİRİCİ ====================
async def download_with_verification(ub, msg, retries=3):
    expected_size = 0
    if msg.video: expected_size = msg.video.file_size
    elif msg.document: expected_size = msg.document.file_size
    elif msg.photo: expected_size = msg.photo.file_size
    if expected_size == 0: return None

    file_path = None
    for attempt in range(1, retries + 1):
        try:
            file_path = await ub.download_media(msg)
            if file_path and os.path.exists(file_path):
                actual = os.path.getsize(file_path)
                if actual >= expected_size or (expected_size - actual) < 1024:
                    return file_path
                else: os.remove(file_path)
        except:
            if file_path and os.path.exists(file_path): os.remove(file_path)
        await asyncio.sleep(0.5)
    return None

# ==================== 6. TRANSFER KOMUTU ====================
def resolve_link(link):
    data = {"id": None, "topic": None, "msg": 0}
    link = str(link).strip()
    try:
        if "c/" in link:
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = int("-100" + clean[0])
            if len(clean) == 3: 
                data["topic"] = int(clean[1])
                data["msg"] = int(clean[2])
            elif len(clean) == 2:
                data["msg"] = int(clean[1])
        elif "-100" in link:
            data["id"] = int(link)
    except: return None
    return data

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_final_fix(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not WORKERS: await message.reply("❌ Userbot Yok!"); return
    
    try:
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **Kullanım:** `/transfer [KAYNAK] [HEDEF]`")
        return

    status = await message.reply("🔄 **SUNUCU HAFIZASI TAZELENİYOR...**\n(PeerID Hatasını Çözmek İçin Gruplar Taranıyor)")

    src = resolve_link(src_link)
    dst = resolve_link(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    # --- KRİTİK NOKTA: GRUPLARI TANI ---
    # Botun ID'leri tanıması için dialogları tarıyoruz.
    try:
        # Önce hedefi tanı
        await force_refresh_peers(WORKERS[0], dst['id'])
        # Sonra kaynağı tanı
        await force_refresh_peers(WORKERS[0], src['id'])
    except Exception as e:
        print(f"Refresh hatası (önemsiz olabilir): {e}")

    # ADIM 1: HEDEFİ TARA
    try:
        existing_count = await scan_target_group(WORKERS[0], dst['id'], dst['topic'])
        await status.edit(f"✅ **HEDEF GRUP ONAYLANDI!**\nDosya Sayısı: {existing_count}\n\n🚀 **Kaynak Çekiliyor...**")
    except Exception as e:
        await status.edit(f"❌ **ERİŞİM HATASI:** {e}\n\nLütfen Userbot'un bu grupta olduğundan ve mesaj atabildiğinden emin olun."); return

    start_point = src['msg'] if src['msg'] > 0 else 0
    msg_ids = []
    
    # ADIM 2: KAYNAĞI LİSTELE
    try:
        async for m in WORKERS[0].get_chat_history(src['id']):
            if ABORT_FLAG: break
            if start_point > 0 and m.id < start_point: continue
            if src['topic']:
                try:
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    if tid != src['topic'] and m.id != src['topic']: continue
                except: continue
            msg_ids.append(m.id)
    except Exception as e:
        await status.edit(f"❌ Kaynak Erişim Hatası: {e}"); return

    msg_ids.reverse()
    total = len(msg_ids)

    await status.edit(f"🏎️ **TRANSFER BAŞLADI**\nKaynak: {total} Mesaj")

    stats = {"success": 0, "skipped": 0, "failed": 0}

    # ADIM 3: AKILLI AKTARIM
    for msg_id in msg_ids:
        if ABORT_FLAG: await status.edit("🛑 **Durduruldu.**"); return
        
        check_worker, _ = await get_best_worker()
        try:
            msg = await check_worker.get_messages(src['id'], msg_id)
            if not msg or msg.empty: continue
            
            # DNA KONTROLÜ
            sig = generate_signature(msg)
            
            if sig and sig in EXISTING_FILES_CACHE:
                stats["skipped"] += 1
                if stats["skipped"] % 50 == 0:
                    try: await status.edit(f"⏩ **GEÇİLİYOR...**\nAtlanan: {stats['skipped']}")
                    except: pass
                continue 
            
            sent = False
            retry = 0
            
            while not sent and retry < 10:
                if ABORT_FLAG: break
                worker, w_idx = await get_best_worker()
                
                try:
                    send_args = {}
                    if dst['topic']: send_args["reply_to_message_id"] = dst['topic']
                    
                    if msg.media:
                        path = await download_with_verification(worker, msg)
                        if path:
                            caption = msg.caption or ""
                            try:
                                if msg.video:
                                    await worker.send_video(dst['id'], path, caption=caption, 
                                        duration=msg.video.duration, width=msg.video.width, height=msg.video.height, **send_args)
                                elif msg.photo: await worker.send_photo(dst['id'], path, caption=caption, **send_args)
                                elif msg.document: await worker.send_document(dst['id'], path, caption=caption, **send_args)
                                elif msg.audio: await worker.send_audio(dst['id'], path, caption=caption, **send_args)
                                elif msg.voice: await worker.send_voice(dst['id'], path, **send_args)
                                sent = True
                            except FloodWait as e:
                                report_flood(w_idx, e.value)
                                retry += 1; continue
                            except: sent = False; break
                            finally:
                                if os.path.exists(path): os.remove(path)
                        else: sent = False; break
                    
                    elif msg.text:
                        try:
                            await worker.send_message(dst['id'], msg.text, **send_args)
                            sent = True
                        except FloodWait as e:
                            report_flood(w_idx, e.value)
                            retry += 1; continue
                        except: break

                except FloodWait as e:
                    report_flood(w_idx, e.value)
                    retry += 1; continue
                except: break

            if sent:
                stats["success"] += 1
                if sig: EXISTING_FILES_CACHE.add(sig)
            else:
                if stats["skipped"] == 0: stats["failed"] += 1

            if (stats["success"] + stats["failed"]) % 5 == 0:
                try: await status.edit(
                    f"📊 **DURUM**\n"
                    f"✅: {stats['success']} | ⏩: {stats['skipped']} | ❌: {stats['failed']}\n"
                    f"📉 Kalan: {total - (stats['success'] + stats['skipped'] + stats['failed'])}"
                )
                except: pass

        except Exception as e:
            stats["failed"] += 1

    await status.edit(
        f"🏁 **TAMAMLANDI!**\n"
        f"✅ Yeni Atılan: {stats['success']}\n"
        f"⏩ Zaten Vardı: {stats['skipped']}\n"
        f"❌ Hata: {stats['failed']}"
    )

@bot.on_message(filters.command("iptal") & filters.private)
async def stop_cmd(c, m):
    global ABORT_FLAG
    ABORT_FLAG = True
    await m.reply("🛑 **Durduruluyor...**")

async def main():
    print("V66 Fix Başlatılıyor...")
    keep_alive()
    await bot.start()
    for i, ub in enumerate(WORKERS):
        try: await ub.start(); print(f"✅ Motor {i+1} Hazır")
        except: pass
    await idle()
    await bot.stop()
    for ub in WORKERS:
        try: await ub.stop()
        except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
