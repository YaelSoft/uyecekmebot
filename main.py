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
def home(): return "Turbo Manager Active! ⚡"

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

bot = Client("manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

USERBOTS = []
if SESSION1: USERBOTS.append(Client("ub1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
if SESSION2: USERBOTS.append(Client("ub2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))

ABORT_FLAG = False

# ==================== 3. HAFIZA SİSTEMİ (GEÇMİŞİ HATIRLA) ====================
DB_NAME = "transfer_history.db"

def init_history_db():
    conn = sqlite3.connect(DB_NAME)
    # Tablo: KaynakGrup, KaynakMesajID, HedefGrup
    conn.cursor().execute('''CREATE TABLE IF NOT EXISTS history 
                             (src_id INTEGER, msg_id INTEGER, dst_id INTEGER, 
                             PRIMARY KEY (src_id, msg_id, dst_id))''')
    conn.commit(); conn.close()

def is_already_sent(src_id, msg_id, dst_id):
    """Bu mesaj daha önce bu hedefe atıldı mı?"""
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT 1 FROM history WHERE src_id=? AND msg_id=? AND dst_id=?", 
                                (src_id, msg_id, dst_id)).fetchone()
    conn.close()
    return bool(res)

def mark_as_sent(src_id, msg_id, dst_id):
    """Mesajı 'atıldı' olarak işaretle"""
    conn = sqlite3.connect(DB_NAME)
    try: conn.cursor().execute("INSERT INTO history VALUES (?, ?, ?)", (src_id, msg_id, dst_id))
    except: pass
    conn.commit(); conn.close()

init_history_db()

# ==================== 4. SAĞLAM İNDİRİCİ ====================
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
                # 1KB tolerans
                if actual_size >= expected_size or (expected_size - actual_size) < 1024:
                    return file_path
                else:
                    os.remove(file_path)
        except:
            if file_path and os.path.exists(file_path): os.remove(file_path)
        await asyncio.sleep(1)
    return None

# ==================== 5. ANA TRANSFER KOMUTU (V47) ====================
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
async def transfer_turbo(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not USERBOTS: await message.reply("❌ Userbot Yok!"); return
    ub = USERBOTS[0]
    
    # 🔥 TURBO MOD: Hız artırıldı, flood yerse bekler
    SAFETY_DELAY = 1 

    try:
        # Linkleri Al (Topic veya Normal fark etmez)
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **Kullanım:** `/transfer [KAYNAK_LINK] [HEDEF_LINK]`")
        return

    status = await message.reply("⚡ **TURBO ANALİZ BAŞLADI...**")

    # Hafıza Tazele
    try: async for d in ub.get_dialogs(limit=20): pass
    except: pass

    src = resolve_link(src_link)
    dst = resolve_link(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    # Başlangıç Mesajı (Linkte verilenden başla)
    start_point = src['msg'] if src['msg'] > 0 else 0
    
    await status.edit(f"📦 **LİSTE HAZIRLANIYOR...**\nVeritabanı kontrol ediliyor...")

    msg_ids = []
    try:
        # Tüm geçmişi çek
        async for m in ub.get_chat_history(src['id']):
            if ABORT_FLAG: break
            
            # 1. Başlangıç Filtresi (Eskileri alma)
            if start_point > 0 and m.id < start_point: continue

            # 2. Topic Filtresi
            if src['topic']:
                try:
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    if tid != src['topic'] and m.id != src['topic']: continue
                except: continue
            
            msg_ids.append(m.id)
    except Exception as e:
        await status.edit(f"❌ Liste Hatası: {e}"); return

    msg_ids.reverse() # Eskiden yeniye
    total = len(msg_ids)
    
    if total == 0: await status.edit("❌ Mesaj bulunamadı."); return

    await status.edit(f"🚀 **TURBO AKTARIM BAŞLADI**\nToplam Hedef: {total}")

    # İSTATİSTİKLER
    stats = {"success": 0, "skipped": 0, "failed": 0}

    for msg_id in msg_ids:
        if ABORT_FLAG: await status.edit("🛑 **Durduruldu.**"); return
        
        # --- 1. HAFIZA KONTROLÜ (BU HIZLANDIRIR) ---
        if is_already_sent(src['id'], msg_id, dst['id']):
            stats["skipped"] += 1
            # Her 50 atlamada bir bilgi ver (Hızlı geçiş için sık güncelleme)
            if stats["skipped"] % 50 == 0:
                try: await status.edit(
                    f"♻️ **HIZLI GEÇİŞ (ATLANİYOR)...**\n"
                    f"✅ Başarılı: {stats['success']}\n"
                    f"⏭️ Önceden Atılan: {stats['skipped']}\n"
                    f"📉 Kalan: {total - (stats['success'] + stats['skipped'])}"
                )
                except: pass
            continue # Döngünün başına dön, sonraki mesaja geç

        # --- 2. GÖNDERİM ---
        try:
            msg = await ub.get_messages(src['id'], msg_id)
            if not msg or msg.empty: continue

            send_args = {}
            if dst['topic']: send_args["reply_to_message_id"] = dst['topic']

            success = False
            
            if msg.media:
                path = await download_with_verification(ub, msg)
                if path:
                    caption = msg.caption or ""
                    try:
                        if msg.video:
                            await ub.send_video(dst['id'], path, caption=caption, 
                                duration=msg.video.duration, width=msg.video.width, height=msg.video.height, **send_args)
                        elif msg.photo: await ub.send_photo(dst['id'], path, caption=caption, **send_args)
                        elif msg.document: await ub.send_document(dst['id'], path, caption=caption, **send_args)
                        elif msg.audio: await ub.send_audio(dst['id'], path, caption=caption, **send_args)
                        elif msg.voice: await ub.send_voice(dst['id'], path, **send_args)
                        elif msg.sticker: await ub.send_sticker(dst['id'], path, **send_args)
                        elif msg.animation: await ub.send_animation(dst['id'], path, caption=caption, **send_args)
                        
                        success = True
                    except: stats["failed"] += 1
                    finally: os.remove(path)
                else: stats["failed"] += 1

            elif msg.text and msg.text.strip():
                try:
                    await ub.send_message(dst['id'], msg.text, **send_args)
                    success = True
                except: stats["failed"] += 1

            # --- SONUÇ İŞLEME ---
            if success: 
                stats["success"] += 1
                # Başarılıysa veritabanına kaydet
                mark_as_sent(src['id'], msg_id, dst['id'])
            
            # Bekleme
            await asyncio.sleep(SAFETY_DELAY)
            
            # Detaylı Rapor (Her 5 işlemde bir)
            if (stats["success"] + stats["failed"]) % 5 == 0:
                try: await status.edit(
                    f"📊 **DETAYLI DURUM**\n\n"
                    f"✅ **Atılan:** {stats['success']}\n"
                    f"♻️ **Atlanan (Eski):** {stats['skipped']}\n"
                    f"❌ **Hata:** {stats['failed']}\n"
                    f"📉 **Kalan:** {total - (stats['success'] + stats['skipped'] + stats['failed'])}"
                )
                except: pass

        except FloodWait as e:
            # Hız sınırına takılırsak bekle, ama durma
            print(f"Hız Limiti: {e.value} saniye bekleniyor...")
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            stats["failed"] += 1

    await status.edit(
        f"🏁 **İŞLEM TAMAMLANDI!**\n\n"
        f"✅ Toplam Atılan: {stats['success']}\n"
        f"♻️ Önceden Vardı: {stats['skipped']}\n"
        f"❌ Başarısız: {stats['failed']}"
    )

@bot.on_message(filters.command("iptal") & filters.private)
async def stop_cmd(c, m):
    global ABORT_FLAG
    ABORT_FLAG = True
    await m.reply("🛑 **DURDURULUYOR...**")

# ==================== 6. BAŞLATMA ====================
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
