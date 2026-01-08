import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, UserAlreadyParticipant

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# Web Server (Render İçin)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Aktif! 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False

# ==================== YENİLENMİŞ LINK PARSER (FIX) ====================

def resolve_link(link):
    """
    Topic ve Normal Grup ayrımını kesin olarak yapar.
    Mantık: Link parçalara ayrılır.
    - Son parça her zaman Mesaj ID'sidir.
    - İlk parça her zaman Chat ID'dir.
    - Eğer arada bir parça varsa, o Topic ID'sidir.
    """
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    
    # Parametreleri temizle (?single vs)
    link = link.split("?")[0]
    
    try:
        if "c/" in link: # Private Link (t.me/c/123456/...)
            parts = link.split("c/")[1].split("/")
            # ID her zaman vardır ve -100 ile başlar
            data["id"] = int("-100" + parts[0])
            
            if len(parts) == 2:
                # Format: ID / MSG_ID (Normal Grup)
                data["msg_id"] = int(parts[1])
            elif len(parts) == 3:
                # Format: ID / TOPIC / MSG_ID (Topicli Grup)
                data["topic_id"] = int(parts[1])
                data["msg_id"] = int(parts[2])
                
        else: # Public Link (t.me/kullaniciadi/...)
            parts = link.split("/")
            data["id"] = parts[0] # Username
            
            if len(parts) == 2:
                # Format: Username / MSG_ID
                data["msg_id"] = int(parts[1])
            elif len(parts) == 3:
                # Format: Username / TOPIC / MSG_ID
                data["topic_id"] = int(parts[1])
                data["msg_id"] = int(parts[2])
                
    except Exception as e:
        logger.error(f"Link Parse Hatası: {e}")
        return None
        
    return data

async def get_chat_guvenli(chat_id):
    """Kanalı bulamazsa hata fırlatır, kullanıcıdan yardım ister."""
    try:
        return await userbot.get_chat(chat_id)
    except:
        # Son çare listeyi tara
        async for d in userbot.get_dialogs():
            if str(d.chat.id) == str(chat_id): return d.chat
            if isinstance(chat_id, str) and d.chat.username:
                if d.chat.username.lower() == chat_id.replace("@","").lower(): return d.chat
        raise ValueError("BULUNAMADI")

async def download_safe(ub, msg):
    """Yarım indirmeyi önleyen fonksiyon"""
    try:
        path = await ub.download_media(msg)
        if path and os.path.getsize(path) > 0: return path
    except: pass
    return None

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply("👋 **Bot Aktif!**\n\nTopic ve Normal grup ayrımı düzeltildi.\n\n`/tekli LINK`\n`/transfer KAYNAK HEDEF`")

@bot.on_message(filters.command("iptal"))
async def cancel_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 İptal edildi.")

@bot.on_message(filters.command("tanimla"))
async def manuel_tanimla(client, message):
    try: link = message.command[1]
    except: await message.reply("❌ Link gir."); return
    status = await message.reply("🔄 Bağlanılıyor...")
    try:
        if "+" in link or "joinchat" in link:
            chat = await userbot.join_chat(link)
        else:
            chat = await userbot.get_chat(link)
        await status.edit(f"✅ Tanımlandı: {chat.title}")
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TEKLİ İNDİRME (FIXED) ====================
@bot.on_message(filters.command("tekli"))
async def tekli_cmd(client, message):
    try:
        link = message.command[1]
        data = resolve_link(link)
    except:
        await message.reply("❌ Link hatalı.")
        return

    if not data or not data["msg_id"]:
        await message.reply("❌ Linkte mesaj numarası yok! (Örn: /105)")
        return

    status = await message.reply("🔄 **Analiz ediliyor...**")

    try:
        # Kanalı Bul
        try:
            chat = await get_chat_guvenli(data["id"])
        except ValueError:
            await status.edit(f"⚠️ Kanal bulunamadı! `/tanimla DAVET_LINKI` yap.")
            return

        # Mesajı Çek
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        # Eğer mesaj boş geldiyse (bazen topic ID'si karışırsa boş gelir)
        if not msg or msg.empty:
            await status.edit("❌ Mesaj bulunamadı! Linki kontrol et.")
            return

        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Bu mesajda medya yok.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_safe(userbot, msg)
        
        if not path:
            await status.edit("❌ İndirme başarısız.")
            return

        await status.edit("📤 **Gönderiliyor...**")
        
        caption = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=caption)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=caption)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=caption)
        
        os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TRANSFER KOMUTU ====================
@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    try:
        args = message.text.split()
        src_link, dst_link = args[1], args[2]
    except:
        await message.reply("❌ `/transfer KAYNAK HEDEF`")
        return

    status = await message.reply("🔄 **Hazırlanıyor...**")
    
    try:
        src_data = resolve_link(src_link)
        dst_data = resolve_link(dst_link)
        
        try: src_chat = await get_chat_guvenli(src_data["id"])
        except: await status.edit("❌ Kaynak kanal bulunamadı! `/tanimla` kullan."); return
        
        try: dst_chat = await get_chat_guvenli(dst_data["id"])
        except: await status.edit("❌ Hedef kanal bulunamadı! `/tanimla` kullan."); return

        baslangic = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Başlıyor!**\nKaynak: {src_chat.title}\nHedef: {dst_chat.title}\nMod: {baslangic}")

        msg_list = []
        
        # Mesajları Topla
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic Filtresi: Eğer kaynak linkte Topic varsa SADECE onu al
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            # ID Filtresi
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0:
            await status.edit("❌ Aktarılacak medya bulunamadı.")
            return

        count = 0
        await status.edit(f"📥 **Transfer Sürüyor...**\nToplam: {total} Medya")

        for mid in msg_list:
            if ABORT_FLAG: await status.edit("🛑 Durdu."); return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                
                path = await download_safe(userbot, msg)
                if not path: continue
                
                # Hedef Argümanları
                s_args = {}
                # Eğer hedef linkte Topic/Msg ID varsa oraya reply at (Topic içine düşer)
                target_topic = dst_data["topic_id"] or dst_data["msg_id"]
                if target_topic: s_args["reply_to_message_id"] = target_topic

                cap = msg.caption or ""
                if msg.video: await userbot.send_video(dst_chat.id, video=path, caption=cap, duration=msg.video.duration, **s_args)
                elif msg.photo: await userbot.send_photo(dst_chat.id, photo=path, caption=cap, **s_args)
                elif msg.document: await userbot.send_document(dst_chat.id, document=path, caption=cap, **s_args)
                
                count += 1
                os.remove(path)
                
                if count % 5 == 0:
                    try: await status.edit(f"🔄 **İlerliyor:** {count}/{total}")
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
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
