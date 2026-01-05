import os
import asyncio
import logging
import sqlite3
import time
from threading import Thread
from flask import Flask, render_template
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, UserDeactivatedBan

# ==================== 1. WEB SERVER (RENDER İÇİN) ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "V60 TWIN TURBO ENGINE ACTIVE! 🚀"

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

# Yönetici Botu
bot = Client("manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# İşçi Botlar (Userbots)
WORKERS = []
# Bot durumlarını takip eden sözlük: {bot_index: next_available_time}
WORKER_STATUS = {} 

if SESSION1: 
    WORKERS.append(Client("w1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
    WORKER_STATUS[0] = 0
if SESSION2: 
    WORKERS.append(Client("w2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))
    WORKER_STATUS[1] = 0

ABORT_FLAG = False

# ==================== 3. HAFIZA SİSTEMİ ====================
DB_NAME = "transfer_history.db"

def init_history_db():
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute('''CREATE TABLE IF NOT EXISTS history 
                             (src_id INTEGER, msg_id INTEGER, dst_id INTEGER, 
                             PRIMARY KEY (src_id, msg_id, dst_id))''')
    conn.commit(); conn.close()

def is_already_sent(src_id, msg_id, dst_id):
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT 1 FROM history WHERE src_id=? AND msg_id=? AND dst_id=?", 
                                (src_id, msg_id, dst_id)).fetchone()
    conn.close()
    return bool(res)

def mark_as_sent(src_id, msg_id, dst_id):
    conn = sqlite3.connect(DB_NAME)
    try: conn.cursor().execute("INSERT INTO history VALUES (?, ?, ?)", (src_id, msg_id, dst_id))
    except: pass
    conn.commit(); conn.close()

init_history_db()

# ==================== 4. AKILLI BOT SEÇİCİ (BEYİN) ====================
async def get_best_worker():
    """En müsait botu seçer. Hepsi banlıysa en az bekleyeni bekler."""
    while True:
        now = time.time()
        best_worker_idx = -1
        min_wait = float('inf')

        # Tüm botları tara
        for idx, release_time in WORKER_STATUS.items():
            if now >= release_time:
                # Bu bot müsait! Direkt bunu döndür.
                return WORKERS[idx], idx
            else:
                # Bu bot banlı, kalan süresine bak
                wait_time = release_time - now
                if wait_time < min_wait:
                    min_wait = wait_time
                    best_worker_idx = idx
        
        # Eğer buraya geldiysek HİÇBİR bot müsait değil demektir.
        # En az beklemesi gereken botun süresi kadar uyuyalım.
        if best_worker_idx != -1:
            print(f"💤 Tüm motorlar soğutuluyor... Bekleme: {int(min_wait)} sn")
            await asyncio.sleep(min_wait)
            # Uyandıktan sonra döngü başa döner ve o botu seçer.
        else:
            # Bot yoksa (Acil durum)
            return None, -1

def report_flood(worker_idx, seconds):
    """Botun ceza yediğini sisteme işler"""
    WORKER_STATUS[worker_idx] = time.time() + seconds + 2 # +2 sn güvenlik payı
    print(f"⚠️ Motor {worker_idx + 1} ısındı! {seconds} sn devre dışı bırakılıyor.")

# ==================== 5. SAĞLAM İNDİRİCİ ====================
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
                actual_size = os.path.getsize(file_path)
                if actual_size >= expected_size or (expected_size - actual_size) < 1024:
                    return file_path
                else:
                    os.remove(file_path)
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
async def transfer_twin_turbo(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not WORKERS: await message.reply("❌ Hiç Userbot Yok!"); return
    
    try:
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **Kullanım:** `/transfer [KAYNAK] [HEDEF]`")
        return

    status = await message.reply("🏎️ **V60 MOTORLARI ISITILIYOR...**")

    # Hafıza Tazele (Tüm Botlar İçin)
    for w in WORKERS:
        try: async for d in w.get_dialogs(limit=10): pass
        except: pass

    src = resolve_link(src_link)
    dst = resolve_link(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    start_point = src['msg'] if src['msg'] > 0 else 0
    
    await status.edit(f"📦 **LİSTE ÇEKİLİYOR...**\n(Bu işlem biraz sürebilir, tüm geçmiş taranıyor)")

    msg_ids = []
    # Listeyi çekmek için 1. Botu kullanıyoruz (Okuma işlemi ban yemez genelde)
    scanner = WORKERS[0]
    
    try:
        async for m in scanner.get_chat_history(src['id']):
            if ABORT_FLAG: break
            if start_point > 0 and m.id < start_point: continue
            if src['topic']:
                try:
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    if tid != src['topic'] and m.id != src['topic']: continue
                except: continue
            msg_ids.append(m.id)
    except Exception as e:
        await status.edit(f"❌ Liste Hatası: {e}"); return

    msg_ids.reverse()
    total = len(msg_ids)
    
    if total == 0: await status.edit("❌ Mesaj bulunamadı."); return

    await status.edit(f"🚀 **TWIN TURBO AKTARIM BAŞLADI**\nToplam Hedef: {total}\nMotor Sayısı: {len(WORKERS)}")

    stats = {"success": 0, "skipped": 0, "failed": 0}

    for msg_id in msg_ids:
        if ABORT_FLAG: await status.edit("🛑 **Durduruldu.**"); return
        
        # 1. HAFIZA KONTROLÜ
        if is_already_sent(src['id'], msg_id, dst['id']):
            stats["skipped"] += 1
            if stats["skipped"] % 100 == 0:
                try: await status.edit(f"⏩ **HIZLI GEÇİŞ**\nAtlanan: {stats['skipped']}")
                except: pass
            continue

        # 2. GÖNDERİM DÖNGÜSÜ (Başarılı olana kadar veya vazgeçene kadar)
        sent_success = False
        retry_count = 0
        
        while not sent_success and retry_count < 10: # Max 10 deneme
            if ABORT_FLAG: break
            
            # Müsait botu seç
            current_worker, worker_idx = await get_best_worker()
            
            try:
                # Mesajı çek
                msg = await current_worker.get_messages(src['id'], msg_id)
                if not msg or msg.empty: 
                    sent_success = True # Mesaj yoksa başarılı sayıp geç
                    break

                send_args = {}
                if dst['topic']: send_args["reply_to_message_id"] = dst['topic']
                
                # --- YÜKLEME ---
                if msg.media:
                    path = await download_with_verification(current_worker, msg)
                    if path:
                        caption = msg.caption or ""
                        try:
                            if msg.video:
                                await current_worker.send_video(dst['id'], path, caption=caption, 
                                    duration=msg.video.duration, width=msg.video.width, height=msg.video.height, **send_args)
                            elif msg.photo: await current_worker.send_photo(dst['id'], path, caption=caption, **send_args)
                            elif msg.document: await current_worker.send_document(dst['id'], path, caption=caption, **send_args)
                            elif msg.audio: await current_worker.send_audio(dst['id'], path, caption=caption, **send_args)
                            elif msg.voice: await current_worker.send_voice(dst['id'], path, **send_args)
                            # Başarılı!
                            sent_success = True
                        except FloodWait as e:
                            # BU BOT BAN YEDİ!
                            report_flood(worker_idx, e.value)
                            retry_count += 1
                            continue # Döngü başına dön, diğer botu seç
                        except Exception as e:
                            print(f"Hata: {e}")
                            sent_success = False # Kritik hata, geç
                            break
                        finally:
                            if os.path.exists(path): os.remove(path)
                    else:
                        sent_success = False # İndirilemedi
                        break
                
                elif msg.text and msg.text.strip():
                    try:
                        await current_worker.send_message(dst['id'], msg.text, **send_args)
                        sent_success = True
                    except FloodWait as e:
                        report_flood(worker_idx, e.value)
                        retry_count += 1
                        continue
                    except:
                        break

            except FloodWait as e:
                report_flood(worker_idx, e.value)
                retry_count += 1
                continue # Diğer bota geç
            except Exception:
                break # Mesajı çekemedik vs.

        # Döngü bitti
        if sent_success:
            stats["success"] += 1
            mark_as_sent(src['id'], msg_id, dst['id'])
        else:
            if stats["skipped"] == 0: # Sadece gerçekten denenip atılamayanları say
                stats["failed"] += 1

        # Raporlama
        if (stats["success"] + stats["failed"]) % 5 == 0:
            try: await status.edit(
                f"🏎️ **TWIN TURBO AKTİF**\n"
                f"✅: {stats['success']} | ⏭️: {stats['skipped']} | ❌: {stats['failed']}\n"
                f"📉 Kalan: {total - (stats['success'] + stats['skipped'] + stats['failed'])}"
            )
            except: pass

    await status.edit(
        f"🏁 **BİTİŞ ÇİZGİSİ!**\n"
        f"✅ Toplam: {stats['success']}\n"
        f"⏭️ Atlanan: {stats['skipped']}\n"
        f"❌ Hata: {stats['failed']}"
    )

@bot.on_message(filters.command("iptal") & filters.private)
async def stop_cmd(c, m):
    global ABORT_FLAG
    ABORT_FLAG = True
    await m.reply("🛑 **FRENE BASILDI! Durduruluyor...**")

# ==================== 7. BAŞLATMA ====================
async def main():
    print("V60 Motorları Çalıştırılıyor...")
    keep_alive()
    await bot.start()
    for i, ub in enumerate(WORKERS):
        try: 
            await ub.start()
            print(f"✅ Motor {i+1} Hazır!")
        except Exception as e: 
            print(f"⚠️ Motor {i+1} Arızalı: {e}")
            
    await idle()
    
    await bot.stop()
    for ub in WORKERS:
        try: await ub.stop()
        except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
