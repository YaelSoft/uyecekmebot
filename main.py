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

# Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Aktif! 🟢"
def run_web(): app.run(host="0.0.0.0", port=8080)
def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# Botlar
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False

# ==================== YARDIMCI FONKSİYONLAR ====================

def resolve_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = int("-100" + clean[0])
            if len(clean) >= 2: data["msg_id"] = int(clean[-1])
            if len(clean) > 2: data["topic_id"] = int(clean[1])
        elif "+" in link or "joinchat" in link:
            return None # Bu bir davet linkidir, ID çözülemez
        else: # Public
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
    except: return None
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
        
        # BULAMAZSA HATA FIRLAT (Ki kullanıcıya soralım)
        raise ValueError("BULUNAMADI")

async def download_safe(ub, msg):
    """Güvenli indirme"""
    try:
        path = await ub.download_media(msg)
        if path and os.path.getsize(path) > 0: return path
    except: pass
    return None

# ==================== YENİ KOMUT: MANUEL TANIMLAMA ====================

@bot.on_message(filters.command("tanimla"))
async def manuel_tanimla(client, message):
    try:
        link = message.command[1]
    except:
        await message.reply("❌ **Kullanım:** `/tanimla https://t.me/+AbCdEfGh...`\n\n_Kanalın davet linkini veya normal linkini atarsan Userbot giriş yapıp hafızasını tazeler._")
        return

    status = await message.reply("🔄 **Kanala bağlanılıyor...**")

    try:
        # Eğer + varsa bu bir davet linkidir, katılmaya çalış
        if "+" in link or "joinchat" in link:
            try:
                chat = await userbot.join_chat(link)
                await status.edit(f"✅ **BAŞARILI!**\nKanal Tanımlandı: **{chat.title}**\nID: `{chat.id}`\n\n_Şimdi transfer komutunu tekrar deneyebilirsin._")
            except UserAlreadyParticipant:
                # Zaten üyeyse get_chat yaparak tazeleyelim
                # Join linkinden chat objesini alamayabiliriz, ama AccessHash tazelenir.
                await status.edit("✅ **Zaten Üyesin!**\nBağlantı tazelendi. Transferi tekrar dene.")
            except Exception as e:
                await status.edit(f"❌ Davet linki hatası: {e}")
        
        else:
            # Normal link ise get_chat zorla
            try:
                chat = await userbot.get_chat(link)
                await status.edit(f"✅ **Görüldü!**\nKanal: **{chat.title}**\nID: `{chat.id}`\n\nTransferi tekrar dene.")
            except Exception as e:
                await status.edit(f"❌ Userbot bu linki hala göremiyor. Lütfen **Davet Linki (Invite Link)** kullanmayı dene.\nHata: {e}")

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
        await message.reply("❌ **Kullanım:** `/transfer KAYNAK HEDEF`")
        return

    status = await message.reply("🔄 **Kanallar aranıyor...**")

    try:
        src_data = resolve_link(src_link)
        dst_data = resolve_link(dst_link)
        
        if not src_data or not dst_data:
             await status.edit("❌ Link formatı geçersiz.")
             return

        # 1. KAYNAK KANALI BULMA
        try:
            src_chat = await get_chat_guvenli(src_data["id"])
        except ValueError:
            # İŞTE BURASI SENİN İSTEDİĞİN YER
            await status.edit(
                f"⚠️ **KAYNAK KANAL BULUNAMADI!**\n\n"
                f"Userbot ID'yi (`{src_data['id']}`) tanıyamadı.\n\n"
                f"👇 **ÇÖZÜM:**\n"
                f"Lütfen şu komutu kullanarak kanalı tanıt:\n"
                f"`/tanimla <KANALIN_DAVET_LINKI>`\n\n"
                f"_(Davet linki yoksa, kanalın herhangi bir mesaj linkini de deneyebilirsin)_"
            )
            return

        # 2. HEDEF KANALI BULMA
        try:
            dst_chat = await get_chat_guvenli(dst_data["id"])
        except ValueError:
            await status.edit(
                f"⚠️ **HEDEF KANAL BULUNAMADI!**\n\n"
                f"Lütfen şu komutu kullanarak kanalı tanıt:\n"
                f"`/tanimla <HEDEF_DAVET_LINKI>`"
            )
            return

        # ... (Kanal bulunduysa işlem devam eder) ...
        
        baslangic_txt = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Başlıyor!**\nK: {src_chat.title}\nH: {dst_chat.title}\nMod: {baslangic_txt}")

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic ve ID Filtresi
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0:
            await status.edit("❌ Medya yok.")
            return

        count = 0
        await status.edit(f"📥 **Transfer Sürüyor...**\nToplam: {total} Dosya")

        for mid in msg_list:
            if ABORT_FLAG:
                await status.edit("🛑 Durduruldu.")
                return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                
                path = await download_safe(userbot, msg)
                if not path: continue
                
                # Hedef Parametreleri
                s_args = {}
                if dst_data["msg_id"]: s_args["reply_to_message_id"] = dst_data["msg_id"]
                elif dst_data["topic_id"]: s_args["reply_to_message_id"] = dst_data["topic_id"]

                caption = msg.caption or ""
                if msg.video: await userbot.send_video(dst_chat.id, video=path, caption=caption, duration=msg.video.duration, **s_args)
                elif msg.photo: await userbot.send_photo(dst_chat.id, photo=path, caption=caption, **s_args)
                elif msg.document: await userbot.send_document(dst_chat.id, document=path, caption=caption, **s_args)
                
                count += 1
                os.remove(path)
                
                if count % 5 == 0:
                    try: await status.edit(f"🔄 **İlerliyor:** {count}/{total}")
                    except: pass
                
                await asyncio.sleep(4)

            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                logger.error(e)
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **BİTTİ!** {count} dosya taşındı.")

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TEKLİ İNDİRME ====================
@bot.on_message(filters.command("tekli"))
async def tekli_cmd(client, message):
    try: link = message.command[1]; data = resolve_link(link)
    except: await message.reply("❌ Link gir."); return

    status = await message.reply("🔄 **İşleniyor...**")
    try:
        chat = await get_chat_guvenli(data["id"]) # Hata verirse exception fırlatır
    except ValueError:
        await status.edit(f"⚠️ Kanal bulunamadı! `/tanimla <DAVET_LINKI>` komutunu kullan.")
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        path = await download_safe(userbot, msg)
        if not path: await status.edit("❌ İndirilemedi."); return
        
        await status.edit("📤 **Gönderiliyor...**")
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=msg.caption)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=msg.caption)
        os.remove(path)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    print("Bot Hazır!")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
