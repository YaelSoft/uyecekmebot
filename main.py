import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==================== AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
# Bu ID'ye sahip olmayan kimse botu kullanamaz (Lisans Sistemi)
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Loglama
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver System Online 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================

async def refresh_cache():
    """Tüm grupları hafızaya alır"""
    global CHAT_CACHE
    async for dialog in userbot.get_dialogs():
        raw_id = str(dialog.chat.id)
        clean_id = raw_id.replace("-100", "").replace("-", "")
        CHAT_CACHE[raw_id] = dialog.chat
        CHAT_CACHE[clean_id] = dialog.chat
        if dialog.chat.username:
            CHAT_CACHE[dialog.chat.username.lower()] = dialog.chat

async def get_chat_smart(chat_input):
    """Hafızadan veya Telegram'dan grubu bulur"""
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0]
    
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    try: return await userbot.get_chat(int(target))
    except: pass
    try: return await userbot.get_chat(int("-100" + target))
    except: pass
    
    # Bulunamazsa yenile
    await refresh_cache()
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    
    return None

def parse_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("http://", "").replace("t.me/", "")
    parts = link.split("/")
    
    try:
        if "c/" in link: # Private
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = clean[0]
            if len(clean) == 2: data["msg_id"] = int(clean[1])
            elif len(clean) == 3: 
                data["topic_id"] = int(clean[1])
                data["msg_id"] = int(clean[2])
        else: # Public
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

# ==================== ARAYÜZ VE START ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    # LİSANS KONTROLÜ (Sadece Sahibi Kullanabilir)
    if message.from_user.id != OWNER_ID:
        await message.reply(
            "🚫 **Yetkisiz Erişim!**\n\n"
            "Bu bot kişiye özeldir.\n"
            "Satın almak veya kendi botunuzu kurdurmak için:\n"
            "👉 **@yasin33** ile iletişime geçin."
        )
        return

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İndir (/getmedia)", callback_data="help_single")],
        [InlineKeyboardButton("🚀 Transfer Başlat (/transfer)", callback_data="help_transfer")],
        [InlineKeyboardButton("🛑 İşlemi Durdur", callback_data="stop_process")],
        [InlineKeyboardButton("👨‍💻 Sahibi / Destek", url="https://t.me/yasin33")]
    ])
    
    await message.reply(
        f"👋 **Hoşgeldin, {message.from_user.first_name}!**\n\n"
        "🤖 **Yael Saver Bot v3.0** (Pro Sürüm)\n"
        "🟢 **Sistem:** Aktif\n"
        "🛡️ **Korumalı İçerik:** Destekleniyor\n"
        "📂 **Önbellek:** Hazır\n\n"
        "Aşağıdaki butonları kullanarak yardım alabilirsin.",
        reply_markup=buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Yetkiniz yok!", show_alert=True)
        return

    data = callback.data
    if data == "help_single":
        await callback.answer()
        await callback.message.reply(
            "📥 **Tekli İçerik İndirme**\n\n"
            "Bir mesajın linkini atarak indirir.\n"
            "**Komut:** `/getmedia <LINK>`\n"
            "**Örnek:** `/getmedia https://t.me/c/12345/99`"
        )
    elif data == "help_transfer":
        await callback.answer()
        await callback.message.reply(
            "🚀 **Toplu Transfer Modu**\n\n"
            "Bir kanaldaki içerikleri diğerine kopyalar.\n"
            "**Komut:** `/transfer <KAYNAK> <HEDEF>`\n\n"
            "📌 **Önemli İpucu:**\n"
            "Eğer kaynak linkin sonuna mesaj numarası eklerseniz oradan başlar!\n"
            "Örn: `.../kaynak/500` -> 500. mesaj ve sonrasını çeker."
        )
    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("Durduruluyor...", show_alert=True)
        await callback.message.reply("🛑 **İşlem durduruldu.**")

# ==================== TEKLİ İNDİRME ====================
@bot.on_message(filters.command("getmedia") & filters.user(OWNER_ID))
async def getmedia_cmd(client, message):
    try: link = message.command[1]
    except: await message.reply("❌ Link girmelisin."); return

    status = await message.reply("🔍 **Aranıyor...**")
    data = parse_link(link)
    if not data or not data["msg_id"]: await status.edit("❌ Link hatalı."); return

    chat = await get_chat_smart(data["id"])
    if not chat: await status.edit("❌ Kanal bulunamadı! Userbot üye mi?"); return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        if not (msg.video or msg.photo or msg.document):
            await status.edit("❌ Medya yok.")
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

# ==================== TRANSFER (AKILLI BAŞLANGIÇLI) ====================
@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ Kullanım: `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)

        src_chat = await get_chat_smart(src_data["id"])
        if not src_chat: await status.edit("❌ Kaynak bulunamadı!"); return
        
        dst_chat = await get_chat_smart(dst_data["id"])
        if not dst_chat: await status.edit("❌ Hedef bulunamadı!"); return

        # BAŞLANGIÇ NOKTASI AYARI
        start_msg_id = src_data["msg_id"]
        start_txt = f"Mesaj {start_msg_id}'den İtibaren" if start_msg_id else "En Baştan"

        await status.edit(
            f"🚀 **Transfer Başlıyor!**\n\n"
            f"📤 **Kaynak:** {src_chat.title}\n"
            f"📥 **Hedef:** {dst_chat.title}\n"
            f"📍 **Başlangıç:** {start_txt}\n"
            f"📝 **Liste:** Hazırlanıyor..."
        )

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # Topic Filtresi
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
            
            # --- KRİTİK NOKTA: BAŞLANGIÇ FİLTRESİ ---
            # get_chat_history Yeni -> Eski gelir. (Örn: 1000, 999, 998...)
            # Eğer kullanıcı "/500" girdiyse (start_msg_id=500):
            # 500'den küçük bir ID gördüğümüz an (499), döngüyü kırarız.
            # Çünkü daha eskiye gitmeye gerek yok.
            if start_msg_id and m.id < start_msg_id:
                break
            
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        # Listeyi Ters Çevir (Eskiden -> Yeniye Sıralı Yükleme İçin)
        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0: await status.edit("❌ İçerik bulunamadı."); return

        count = 0
        await status.edit(f"📥 **Aktarım: 0/{total}**")

        for mid in msg_list:
            if ABORT_FLAG: await status.edit("🛑 Durdu."); return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                path = await download_safe(userbot, msg)
                if not path: continue

                # Hedef Parametreleri
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
                    try: await status.edit(f"🔄 **İlerliyor:** {count}/{total}")
                    except: pass
                await asyncio.sleep(4)

            except FloodWait as fw: await asyncio.sleep(fw.value + 5)
            except Exception as e:
                if 'path' in locals() and os.path.exists(path): os.remove(path)

        await bot.send_message(message.chat.id, f"✅ **İşlem Tamamlandı!**\nToplam {count} dosya aktarıldı.")

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== BAŞLATMA ====================
async def main():
    keep_alive()
    await bot.start()
    await userbot.start()
    
    # Başlangıç Taraması
    await refresh_cache()
    
    print("Yael Saver Bot Yayında!")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
