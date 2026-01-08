import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==================== MÜŞTERİ AYARLARI ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
# Eğer müşterinin sadece kendisinin kullanmasını istiyorsan buraya ID'sini yaz
OWNER_ID = int(os.environ.get("OWNER_ID", "0")) 

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PremiumBot")

# Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Premium Bot Online 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False

# ==================== ARKA PLAN ZEKA (AUTO-FIX) ====================

async def silent_chat_finder(chat_id_or_username):
    """
    Kullanıcıya hiçbir şey sormadan arka planda grubu bulur.
    Önce normal dener, olmazsa tüm listeyi tarar.
    """
    try:
        # 1. Normal Yöntem
        return await userbot.get_chat(chat_id_or_username)
    except:
        # 2. Hata verirse sessizce listeyi tara (Brute Force)
        target = str(chat_id_or_username).replace("-100", "").replace("@", "")
        
        async for dialog in userbot.get_dialogs():
            current_id = str(dialog.chat.id).replace("-100", "")
            
            # ID Eşleşmesi
            if current_id == target:
                return dialog.chat
            
            # Username Eşleşmesi
            if dialog.chat.username and dialog.chat.username.lower() == target.lower():
                return dialog.chat
                
        # Hiçbir şekilde bulunamazsa
        return None

def parse_link(link):
    """Linkten tüm verileri çeker"""
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private Link
            # t.me/c/123456/100 -> parts=['c', '123456', '100'] (örnek split mantığına göre değişir)
            # Daha temiz split:
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = int("-100" + clean[0])
            
            if len(clean) == 2: data["msg_id"] = int(clean[1])
            elif len(clean) == 3: 
                data["topic_id"] = int(clean[1])
                data["msg_id"] = int(clean[2])
        else: # Public Link
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
            if len(parts) >= 3: 
                data["topic_id"] = int(parts[1])
                data["msg_id"] = int(parts[2])
    except: return None
    return data

async def download_safe(ub, msg):
    try:
        path = await ub.download_media(msg)
        if path and os.path.getsize(path) > 0: return path
    except: pass
    return None

# ==================== ARAYÜZ VE KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    # Yetki Kontrolü (Opsiyonel: Sadece Owner kullanabilsin)
    if OWNER_ID != 0 and message.from_user.id != OWNER_ID:
        return
        
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İçerik Çek", callback_data="help_single"), 
         InlineKeyboardButton("🚀 Toplu Transfer", callback_data="help_transfer")],
        [InlineKeyboardButton("🛑 İşlemi Durdur", callback_data="stop_process")],
        [InlineKeyboardButton("👨‍💻 Destek / İletişim", url="https://t.me/SeninKullaniciAdin")]
    ])
    
    await message.reply_photo(
        photo="https://i.ibb.co/vzJXn2S/bot-image.jpg", # Buraya güzel bir banner linki koy
        caption=(
            f"👋 **Hoşgeldin, {message.from_user.first_name}!**\n\n"
            "Ben **Premium Content Saver Bot**.\n"
            "İletim kısıtlı (Restricted) kanallardan içerik kopyalayabilirim.\n\n"
            "🤖 **Sistem Durumu:** `Aktif`\n"
            "⚡ **Mod:** `Otomatik Algılama`\n\n"
            "👇 **Ne yapmak istersin?**"
        ),
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    if data == "help_single":
        await callback.answer()
        await callback.message.reply("📥 **Tekli İçerik İndirme:**\n\nKullanım:\n`/getmedia <LINK>`\n\nÖrnek:\n`/getmedia https://t.me/c/123456/99`")
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply("🚀 **Toplu Transfer:**\n\nKullanım:\n`/transfer <KAYNAK> <HEDEF>`\n\nÖrnek:\n`/transfer https://t.me/c/kaynak https://t.me/hedef`")
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("İptal sinyali gönderildi!", show_alert=True)
        await callback.message.reply("🛑 **İşlem durduruluyor...**")

# ==================== TEKLİ İNDİRME (/getmedia) ====================
@bot.on_message(filters.command("getmedia"))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("❌ **Kullanım:** `/getmedia https://t.me/...`"); return

    status = await message.reply("🔄 **Bağlanılıyor...**")
    
    data = parse_link(link)
    if not data or not data["msg_id"]:
        await status.edit("❌ Geçersiz link.")
        return

    # Arka planda sessizce bul
    chat = await silent_chat_finder(data["id"])
    
    if not chat:
        await status.edit("❌ **Erişim Hatası!**\nUserbot bu kanalda bulunamadı. Lütfen Userbot hesabının gruba üye olduğundan emin ol.")
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya bulunamadı.")
            return

        await status.edit("📥 **İndiriliyor...**")
        path = await download_safe(userbot, msg)
        
        await status.edit("📤 **Yükleniyor...**")
        cap = msg.caption or ""
        
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        os.remove(path)
        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TOPLU TRANSFER (/transfer) ====================
@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ **Kullanım:** `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")

    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)

        # Sessiz Arama (Müşteriyi yormadan)
        src_chat = await silent_chat_finder(src_data["id"])
        if not src_chat:
            await status.edit("❌ **Kaynak Grup Bulunamadı!**\nUserbot'un gruba üye olduğundan emin olun.")
            return
            
        dst_chat = await silent_chat_finder(dst_data["id"])
        if not dst_chat:
            await status.edit("❌ **Hedef Grup Bulunamadı!**")
            return

        # Başlangıç Bilgisi
        start_msg = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Transfer Başlatıldı**\n\n📤 **Kaynak:** {src_chat.title}\n📥 **Hedef:** {dst_chat.title}\n📍 **Başlangıç:** {start_msg}")

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic ve ID Filtreleri
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0: await status.edit("❌ İçerik bulunamadı."); return

        count = 0
        await status.edit(f"📥 **Aktarım: 0/{total}**\n_Lütfen bekleyin..._")

        for mid in msg_list:
            if ABORT_FLAG: await status.edit("🛑 İşlem kullanıcı tarafından durduruldu."); return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                
                path = await download_safe(userbot, msg)
                if not path: continue

                # Hedef Topic Ayarı
                s_args = {}
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
                await asyncio.sleep(4) # Spam Koruması

            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **İşlem Tamamlandı!**\nToplam {count} adet medya taşındı.")

    except Exception as e:
        await status.edit(f"❌ Bir hata oluştu: {e}")

# ==================== BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    print("Premium Bot Hazır!")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
