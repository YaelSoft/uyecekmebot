import os
import asyncio
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

# ==================== RENDER AYARLARI ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

MAX_JOBS = 4

# DENEME SÜRÜMÜ AYARLARI
USER_USAGE = {} # Kim kaç tane indirdi?
FREE_LIMIT = 3  # Bedava hak sayısı

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# ==================== WEB SERVER (RENDER İÇİN) ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver Sales Mode Online"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# ==================== BOT BAŞLATMA ====================
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
CHAT_CACHE = {} 

# ==================== YARDIMCI FONKSİYONLAR ====================
async def get_chat_smart(chat_input):
    target = str(chat_input).replace("https://", "").replace("t.me/", "").replace("@", "").lower()
    if "c/" in target: target = target.split("c/")[1].split("/")[0]
    if target in CHAT_CACHE: return CHAT_CACHE[target]
    try: return await userbot.get_chat(int(target))
    except: pass
    try: return await userbot.get_chat(int("-100" + target))
    except: pass
    try: return await userbot.get_chat(target)
    except: return None

def parse_link(link):
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("t.me/", "")
    parts = link.split("/")
    try:
        if "c/" in link: 
            clean = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = clean[0]
            if len(clean) == 2: data["msg_id"] = int(clean[1])
            elif len(clean) == 3: data["topic_id"] = int(clean[1]); data["msg_id"] = int(clean[2])
        else: 
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
            if len(parts) >= 3: data["topic_id"] = int(parts[1]); data["msg_id"] = int(parts[2])
    except: return None
    return data

# ==================== MENÜ SİSTEMİ ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Kullanıcı Durumu (Admin mi Misafir mi?)
    if user_id == OWNER_ID:
        status_text = "👑 **Yönetici Modu** (Sınırsız)"
    else:
        used = USER_USAGE.get(user_id, 0)
        remaining = max(0, FREE_LIMIT - used)
        status_text = f"👤 **Misafir Modu**\n🎁 Deneme Hakkı: `{remaining}/{FREE_LIMIT}`"

    menu_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tekli İndir (Demo)", callback_data="page_single")],
        [InlineKeyboardButton("🚀 Toplu Transfer (Premium)", callback_data="page_transfer")],
        [InlineKeyboardButton("💎 SATIN AL / İLETİŞİM", url="https://t.me/yasin33")]
    ])
    
    await message.reply(
        f"👋 **Hoş Geldiniz, {message.from_user.first_name}**\n\n"
        f"🤖 **Yael Saver - Kısıtlı İçerik İndirici**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{status_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Bu bot, 'İletim Kısıtlaması' olan gruplardan içerik indirmenizi sağlar.\n"
        f"Satın almadan önce sistemi test etmeniz için **{FREE_LIMIT} adet ücretsiz indirme** hakkınız vardır.\n\n"
        f"👇 **İşlem Seçiniz:**",
        reply_markup=menu_buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "main_menu":
        await start_handler(client, callback.message)

    elif data == "page_single":
        await callback.answer()
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri Dön", callback_data="main_menu")]])
        
        used = USER_USAGE.get(user_id, 0)
        limit_info = "Sınırsız" if user_id == OWNER_ID else f"{max(0, FREE_LIMIT - used)} Hak Kaldı"
        
        await callback.message.edit_text(
            f"📥 **TEKLİ İNDİRME** ({limit_info})\n\n"
            "Fotoğraf veya video linkini göndererek indirebilirsiniz.\n\n"
            "📝 **Kullanım:**\n"
            "`/indir <Link>`\n\n"
            "💡 **Örnek:**\n"
            "`/indir https://t.me/c/123456/99`",
            reply_markup=back
        )

    elif data == "page_transfer":
        await callback.answer()
        premium_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 SATIN AL / BİLGİ AL", url="https://t.me/yasin33")],
            [InlineKeyboardButton("🔙 Geri Dön", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "🚀 **TOPLU TRANSFER MODÜLÜ (PREMIUM)**\n\n"
            "Bu özellik, binlerce dosyayı tek komutla kendi kanalınıza yedeklemenizi sağlar.\n\n"
            "🔒 **Bu özellik sadece Full Sürümde aktiftir.**\n"
            "Kendi botunuzu kurdurmak için iletişime geçin.",
            reply_markup=premium_btn
        )

# ==================== İNDİRME İŞLEMİ (LİMİT KONTROLLÜ) ====================

@bot.on_message(filters.command("indir"))
async def indir_cmd(client, message):
    user_id = message.from_user.id
    
    # KOTA KONTROLÜ
    if user_id != OWNER_ID:
        used = USER_USAGE.get(user_id, 0)
        if used >= FREE_LIMIT:
            buy_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 LİMİTSİZ SÜRÜMÜ AL", url="https://t.me/yasin33")]])
            await message.reply(
                "⛔ **DENEME HAKKINIZ BİTTİ**\n\n"
                "Sistemin çalıştığını test ettiniz.\n"
                "Sınırsız indirme ve toplu transfer özellikleri için botu satın almalısınız.\n\n"
                "👇 **Hemen İletişime Geç:**",
                reply_markup=buy_btn
            )
            return

    try: link = message.command[1]
    except: await message.reply("⚠️ Link girmelisiniz."); return

    status = await message.reply("🔍 **Medya Aranıyor...**")
    data = parse_link(link)
    chat = await get_chat_smart(data["id"])
    
    if not chat:
        await status.edit("❌ Kanal bulunamadı. (Userbot üye değil)")
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        await status.edit("📥 **İndiriliyor...**")
        path = await userbot.download_media(msg)
        
        if not path:
            await status.edit("❌ İndirme başarısız.")
            return

        await status.edit("📤 **Gönderiliyor...**")
        
        cap = msg.caption or ""
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
        
        # Kullanım Hakkını Düş
        if user_id != OWNER_ID:
            USER_USAGE[user_id] = USER_USAGE.get(user_id, 0) + 1
            remaining = max(0, FREE_LIMIT - USER_USAGE[user_id])
            await message.reply(f"🎁 **Kalan Deneme Hakkı:** {remaining}")
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TRANSFER (SADECE OWNER) ====================

# Yardımcı Transfer İşçisi
async def transfer_worker(sem, mid, src, dst, args):
    if ABORT_FLAG: return (False, 0)
    async with sem:
        path = None
        try:
            msg = await userbot.get_messages(src, mid)
            if not msg or not (msg.video or msg.photo or msg.document): return (False, 0)
            
            size = 0
            if msg.video: size = msg.video.file_size
            elif msg.photo: size = msg.photo.file_size
            elif msg.document: size = msg.document.file_size
            
            path = await userbot.download_media(msg)
            if not path: return (False, 0)
            
            while True:
                if ABORT_FLAG: break
                try:
                    if msg.video: await userbot.send_video(dst, video=path, caption=msg.caption or "", duration=msg.video.duration, **args)
                    elif msg.photo: await userbot.send_photo(dst, photo=path, caption=msg.caption or "", **args)
                    elif msg.document: await userbot.send_document(dst, document=path, caption=msg.caption or "", **args)
                    break
                except FloodWait as fw: await asyncio.sleep(fw.value + 3)
                except: break
            
            if os.path.exists(path): os.remove(path)
            return (True, size / 1024 / 1024)
        except: 
            if path and os.path.exists(path): os.remove(path)
            return (False, 0)

@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    # YETKİ KONTROLÜ
    if message.from_user.id != OWNER_ID:
        await message.reply(
            "🔒 **Bu özellik sadece PREMIUM Sürümde aktiftir.**\n"
            "Sınırsız toplu transfer için satın almalısınız.\n"
            "👉 @yasin33"
        )
        return

    global ABORT_FLAG
    ABORT_FLAG = False
    
    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("⚠️ Kullanım: `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Analiz Ediliyor...**")
    
    try:
        src_data = parse_link(src_link)
        dst_data = parse_link(dst_link)
        src_chat = await get_chat_smart(src_data["id"])
        dst_chat = await get_chat_smart(dst_data["id"])
        
        if not src_chat or not dst_chat:
            await status.edit("❌ Kanal bulunamadı.")
            return

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            if m.video or m.photo or m.document: msg_list.append(m.id)
        
        msg_list.reverse()
        total = len(msg_list)
        if total == 0: await status.edit("❌ Dosya yok."); return
        
        sem = asyncio.Semaphore(MAX_JOBS)
        tasks = []
        processed = 0
        success = 0
        
        await status.edit(f"🚀 **Transfer Başladı**\n📂 Toplam: `{total}` dosya")
        
        for mid in msg_list:
            if ABORT_FLAG: break
            dst_args = {}
            if dst_data["msg_id"]: dst_args["reply_to_message_id"] = dst_data["msg_id"]
            
            tasks.append(asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args)))
            
            if len(tasks) >= MAX_JOBS + 1:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                for t in done:
                    res, size = t.result()
                    processed += 1
                    if res: success += 1
                
                try:
                    percent = int((processed / total) * 100)
                    await status.edit(f"🔄 **İşleniyor...**\n📊 İlerleme: %{percent} ({processed}/{total})")
                except: pass

        if tasks: await asyncio.wait(tasks)
        await status.edit("✅ **TRANSFER TAMAMLANDI!**")
        
    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== MAIN ====================
async def main():
    keep_alive()
    print("Bot Başlatılıyor...")
    await bot.start()
    await userbot.start()
    print("✅ YAEL SAVER CLEAN SALES MODE AKTİF")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
