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
FREE_LIMIT = 3

# HAFIZA SİSTEMLERİ
USER_USAGE = {}       # Kota takibi
USER_STATE = {}       # Kullanıcı durumu

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YaelSaver")

# ==================== WEB SERVER ====================
app = Flask(__name__)
@app.route('/')
def home(): return "Yael Saver Final Online"
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
    if user_id in USER_STATE: del USER_STATE[user_id]
    
    if user_id == OWNER_ID:
        status_text = "👑 **Yönetici Modu** (Sınırsız)"
    else:
        used = USER_USAGE.get(user_id, 0)
        remaining = max(0, FREE_LIMIT - used)
        status_text = f"👤 **Misafir Modu**\n🎁 Deneme Hakkı: `{remaining}/{FREE_LIMIT}`"

    menu_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 İNDİR", callback_data="btn_indir"),
         InlineKeyboardButton("🚀 Toplu Transfer", callback_data="btn_transfer")],
        [InlineKeyboardButton("❓ Nasıl Kullanılır?", callback_data="show_tutorial")],
        [InlineKeyboardButton("💎 KENDİ BOTUNU KURDUR", url="https://t.me/yasin33")]
    ])
    
    if user_id == OWNER_ID:
        menu_buttons.inline_keyboard.append([InlineKeyboardButton("🛑 İŞLEMİ DURDUR", callback_data="stop_confirm")])

    await message.reply(
        f"👋 **Merhaba, {message.from_user.first_name}**\n\n"
        f"🤖 **Yael Saver - Arşiv Asistanı**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{status_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"İletim yasağı olan içerikleri özgürleştirin.\n"
        f"Demo sürümde **{FREE_LIMIT} adet** ücretsiz işlem yapabilirsiniz.\n\n"
        f"👇 **İşlem Seçiniz:**",
        reply_markup=menu_buttons
    )

@bot.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    
    # ANA MENÜ
    if data == "main_menu":
        if user_id in USER_STATE: del USER_STATE[user_id]
        await start_handler(client, callback.message)

    # İNDİRME MODU
    elif data == "btn_indir":
        await callback.answer()
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 İptal / Geri Dön", callback_data="main_menu")]])
        
        used = USER_USAGE.get(user_id, 0)
        remaining = max(0, FREE_LIMIT - used)
        
        if user_id != OWNER_ID and remaining <= 0:
            await callback.answer("Deneme hakkınız doldu!", show_alert=True)
            return

        USER_STATE[user_id] = "waiting_link"
        
        await callback.message.edit_text(
            f"🔗 **LÜTFEN BAĞLANTIYI GÖNDERİN**\n\n"
            f"İndirmek istediğiniz fotoğraf veya videonun linkini yapıştırıp gönderin.\n"
            f"🎁 **Kalan Hak:** {remaining}\n\n"
            f"⚠️ **ÖNEMLİ:** Demo sürüm sadece 'Herkese Açık' kanallarda çalışır. Gizli kanallar için Premium almalısınız.",
            reply_markup=back
        )

    # TRANSFER SAYFASI
    elif data == "btn_transfer":
        await callback.answer()
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri Dön", callback_data="main_menu")]])

        if user_id == OWNER_ID:
            await callback.message.edit_text(
                "🚀 **TOPLU TRANSFER (YÖNETİCİ)**\n\n"
                "Komut: `/transfer KAYNAK HEDEF`",
                reply_markup=back
            )
        else:
            premium_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 FİYAT AL / İLETİŞİM", url="https://t.me/yasin33")],
                [InlineKeyboardButton("🔙 Geri Dön", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                "🚀 **TOPLU TRANSFER MODÜLÜ (PREMIUM)**\n\n"
                "Kanal kopyalama ve sınırsız yedekleme özelliği sadece **Kişiye Özel Botlarda** bulunur.\n\n"
                "Kendi hesabınıza entegre çalışan botunuzu kurdurmak için iletişime geçin.",
                reply_markup=premium_btn
            )

    # --- YENİ METİNSEL KULLANIM KILAVUZU ---
    elif data == "show_tutorial":
        await callback.answer()
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menüye Dön", callback_data="main_menu")]])
        
        await callback.message.edit_text(
            "📚 **YAEL SAVER KULLANIM REHBERİ**\n\n"
            "**1️⃣ Tekli İndirme (Demo):**\n"
            "• Menüden **'İNDİR'** butonuna basın.\n"
            "• Telegram'daki herhangi bir video/fotoğrafın bağlantısını (Link) kopyalayın.\n"
            "• Bota gönderin. Bot kısıtlamayı kaldırıp size iletecektir.\n"
            "*(Not: Demo sürümde sadece Herkese Açık kanallar desteklenir.)*\n\n"
            "**2️⃣ Gizli/Özel Kanallar:**\n"
            "• Erişiminiz olmayan veya linki gizli olan kanallar için **Kişiye Özel Bot** gereklidir.\n"
            "• Özel bot, sizin hesabınız üzerinden çalışır ve üye olduğunuz HER YERDEN indirme yapar.\n\n"
            "**3️⃣ Toplu Transfer:**\n"
            "• Binlerce dosyayı tek tıkla yedeklemek için Premium sürüm almalısınız.\n\n"
            "💎 **Kurulum & Satın Alım:** @yasin33",
            reply_markup=back
        )

    # DURDURMA (ADMİN)
    elif data == "stop_confirm":
        if user_id != OWNER_ID: return
        confirm = InlineKeyboardMarkup([[InlineKeyboardButton("✅ EVET", callback_data="stop_process"), InlineKeyboardButton("🔙 HAYIR", callback_data="main_menu")]])
        await callback.message.edit_text("⚠️ Tüm işlemler durdurulsun mu?", reply_markup=confirm)

    elif data == "stop_process":
        global ABORT_FLAG
        ABORT_FLAG = True
        await callback.answer("Durduruldu.", show_alert=True)
        await callback.message.edit_text("🛑 **SİSTEM DURDURULDU**")

# ==================== MESAJ DİNLEYİCİ (LİNK YAKALAYICI) ====================
@bot.on_message(filters.text & ~filters.command(["start", "transfer"]))
async def message_handler(client, message):
    user_id = message.from_user.id
    
    if USER_STATE.get(user_id) != "waiting_link": return

    if user_id != OWNER_ID:
        used = USER_USAGE.get(user_id, 0)
        if used >= FREE_LIMIT:
            del USER_STATE[user_id]
            buy_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 LİMİTSİZ SÜRÜM AL", url="https://t.me/yasin33")]])
            await message.reply("⛔ **DENEME HAKKINIZ BİTTİ**\n\nSınırsız kullanım için iletişime geçin.", reply_markup=buy_btn)
            return

    link = message.text
    if "t.me/" not in link:
        await message.reply("⚠️ **Hatalı Link!**\nLütfen geçerli bir Telegram mesaj linki gönderin.\nÖrn: `https://t.me/kanal/123`")
        return

    status = await message.reply("🔍 **Medya Aranıyor...**")
    del USER_STATE[user_id] # İşlem başladı, modu kapat

    data = parse_link(link)
    chat = await get_chat_smart(data["id"])
    
    # ÖZEL KANAL UYARISI
    if not chat:
        buy_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 KENDİ BOTUNU KURDUR", url="https://t.me/yasin33")]])
        await status.edit(
            "❌ **ERİŞİM YOK!**\n\n"
            "Bu içerik **Gizli/Özel** bir kanalda. Demo bot sadece 'Herkese Açık' kanalları indirebilir.\n\n"
            "💡 **ÇÖZÜM:**\n"
            "Özel gruplarınızdan indirme yapmak için **Kişiye Özel Bot Kurulumu** satın almalısınız.",
            reply_markup=buy_btn
        )
        return

    try:
        msg = await userbot.get_messages(chat.id, data["msg_id"])
        
        await status.edit("📥 **İndiriliyor...**")
        path = await userbot.download_media(msg)
        
        if not path: await status.edit("❌ İndirme başarısız."); return

        await status.edit("📤 **Gönderiliyor...**")
        
        cap = msg.caption or ""
        cap += "\n\n🤖 **Yael Saver ile indirildi.**"
        
        if msg.video: await bot.send_video(message.chat.id, video=path, caption=cap)
        elif msg.photo: await bot.send_photo(message.chat.id, photo=path, caption=cap)
        elif msg.document: await bot.send_document(message.chat.id, document=path, caption=cap)
        
        if os.path.exists(path): os.remove(path)
        await status.delete()
        
        if user_id != OWNER_ID:
            USER_USAGE[user_id] = USER_USAGE.get(user_id, 0) + 1
            remaining = max(0, FREE_LIMIT - USER_USAGE[user_id])
            menu_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Başka İndir", callback_data="btn_indir")]])
            await message.reply(f"🎁 **Kalan Hakkınız:** {remaining}", reply_markup=menu_btn)
        
    except Exception as e: await status.edit(f"❌ Hata: {e}")

# ==================== TRANSFER (ADMİN) ====================
async def transfer_worker(sem, mid, src, dst, args):
    if ABORT_FLAG: return (False, 0)
    async with sem:
        path = None
        try:
            msg = await userbot.get_messages(src, mid)
            if not msg or not (msg.video or msg.photo or msg.document): return (False, 0)
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
            return (True, 0)
        except: 
            if path and os.path.exists(path): os.remove(path)
            return (False, 0)

@bot.on_message(filters.command("transfer") & filters.user(OWNER_ID))
async def transfer_cmd(client, message):
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
        if not src_chat or not dst_chat: await status.edit("❌ Kanal bulunamadı."); return

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
        await status.edit(f"🚀 **Transfer Başladı**\n📂 Dosya: `{total}`")
        
        for mid in msg_list:
            if ABORT_FLAG: break
            dst_args = {}
            if dst_data["msg_id"]: dst_args["reply_to_message_id"] = dst_data["msg_id"]
            tasks.append(asyncio.create_task(transfer_worker(sem, mid, src_chat.id, dst_chat.id, dst_args)))
            if len(tasks) >= MAX_JOBS + 1:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                for t in done: processed += 1
                try: await status.edit(f"🔄 **İşleniyor...**\n📊 İlerleme: %{int((processed/total)*100)} ({processed}/{total})"); except: pass

        if tasks: await asyncio.wait(tasks)
        await status.edit("✅ **TRANSFER TAMAMLANDI!**")
    except Exception as e: await status.edit(f"❌ Hata: {e}")

# ==================== MAIN ====================
async def main():
    keep_alive()
    print("Bot Başlatılıyor...")
    await bot.start()
    await userbot.start()
    print("✅ YAEL SAVER FINAL MODE")
    await idle()
    await bot.stop()
    await userbot.stop()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
