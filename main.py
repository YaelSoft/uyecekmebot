import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait

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
def home(): return "Bot Aktif! Derin Arama Modu 🟢"
def run_web(): port = int(os.environ.get("PORT", 8080)); app.run(host="0.0.0.0", port=port)
def keep_alive(): t = Thread(target=run_web); t.daemon = True; t.start()

# Botlar
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

ABORT_FLAG = False
FOUND_CHATS_CACHE = {} # Bulunan grupları hafızada tutmak için

# ==================== YARDIMCI FONKSİYONLAR ====================

def resolve_link_id(link):
    """Linkten sadece ID'yi çeker"""
    link = str(link).strip()
    try:
        if "c/" in link: # Private: t.me/c/123456/99
            clean = link.split("c/")[1].split("/")[0]
            return clean # String olarak döndür (123456)
        else:
            return None
    except: return None

def parse_full_link(link):
    """Transfer için detaylı parse"""
    data = {"id": None, "msg_id": None, "topic_id": None}
    link = str(link).strip().replace("https://", "").replace("t.me/", "")
    try:
        if "c/" in link: 
            parts = link.split("c/")[1].split("?")[0].split("/")
            data["id"] = int("-100" + parts[0])
            if len(parts) >= 2: data["msg_id"] = int(parts[-1])
            if len(parts) > 2: data["topic_id"] = int(parts[1])
        else: # Public
            parts = link.split("/")
            data["id"] = parts[0]
            if len(parts) >= 2: data["msg_id"] = int(parts[1])
    except: return None
    return data

async def download_safe(ub, msg):
    try:
        path = await ub.download_media(msg)
        if path and os.path.getsize(path) > 0: return path
    except: pass
    return None

# ==================== KOMUTLAR ====================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply(
        "🕵️‍♂️ **Kayıp Grup Avcısı Bot**\n\n"
        "Eğer bot grubu göremiyorsa şu adımı uygula:\n\n"
        "1️⃣ O gruptan herhangi bir mesajın bağlantısını kopyala.\n"
        "2️⃣ `/bul <MESAJ_LINKI>` yaz.\n"
        "3️⃣ Bot grubu bulunca `/transfer` yap."
    )

@bot.on_message(filters.command("iptal"))
async def cancel_handler(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 İşlem durduruldu.")

# --- DERİN ARAMA KOMUTU (SENİN İLACIN BU) ---
@bot.on_message(filters.command("bul"))
async def bul_handler(client, message):
    try:
        link = message.command[1]
        target_id_raw = resolve_link_id(link) # Örn: 1555999
    except:
        await message.reply("❌ Link gir. Örn: `/bul https://t.me/c/123456/789`")
        return

    if not target_id_raw:
        await message.reply("❌ Linkten ID alınamadı. `t.me/c/` formatında olduğundan emin ol.")
        return

    status = await message.reply(f"🕵️‍♂️ **Derin Arama Başlatıldı...**\n\nAranan ID: `{target_id_raw}`\nUserbot'un tüm sohbetleri taranıyor (Bu biraz sürebilir)...")

    found_chat = None
    count = 0
    
    # Userbot'un tüm dialoglarını gez (Limit yok)
    async for dialog in userbot.get_dialogs():
        count += 1
        
        # Userbot'taki ID'leri temizle (-100'ü at)
        current_id = str(dialog.chat.id).replace("-100", "").replace("-", "")
        
        # Karşılaştır
        if current_id == str(target_id_raw):
            found_chat = dialog.chat
            break
        
        # Kullanıcıya canlı bilgi ver (Her 200 grupta bir)
        if count % 200 == 0:
            try: await status.edit(f"🕵️‍♂️ **Taranıyor...**\nKontrol edilen grup sayısı: {count}")
            except: pass

    if found_chat:
        # Bulunanı hafızaya at
        FOUND_CHATS_CACHE[found_chat.id] = found_chat
        
        await status.edit(
            f"✅ **BINGO! GRUP BULUNDU!**\n\n"
            f"📌 **Başlık:** {found_chat.title}\n"
            f"🆔 **Orijinal ID:** `{found_chat.id}`\n\n"
            f"Artık transfer komutunu kullanabilirsin:\n"
            f"`/transfer {link} https://t.me/hedef_link`"
        )
    else:
        await status.edit(
            f"❌ **SONUÇ YOK!**\n\n"
            f"Userbot hesabınla toplam **{count}** adet sohbete bakıldı ama `{target_id_raw}` ID'li grup bulunamadı.\n\n"
            f"⚠️ **Olası Sebepler:**\n"
            f"1. Yanlış Userbot (Session) ile giriş yaptın.\n"
            f"2. Gruptan atıldın.\n"
            f"3. O link bambaşka bir gruba ait."
        )

# --- TRANSFER ---
@bot.on_message(filters.command("transfer"))
async def transfer_cmd(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False

    try: args = message.text.split(); src_link, dst_link = args[1], args[2]
    except: await message.reply("❌ `/transfer KAYNAK HEDEF`"); return

    status = await message.reply("🔄 **Hazırlanıyor...**")

    try:
        src_data = parse_full_link(src_link)
        dst_data = parse_full_link(dst_link)
        
        # --- KAYNAK KANALI ALMA (CACHE KONTROLLÜ) ---
        src_chat = None
        
        # 1. Önce Cache'e bak (/bul komutu bulduysa buradadır)
        if src_data["id"] in FOUND_CHATS_CACHE:
            src_chat = FOUND_CHATS_CACHE[src_data["id"]]
        else:
            # 2. Cache'de yoksa get_chat dene
            try:
                src_chat = await userbot.get_chat(src_data["id"])
            except:
                # 3. Yine bulamazsa listeden manuel ara (Son şans)
                target_raw = str(src_data["id"]).replace("-100", "")
                async for d in userbot.get_dialogs():
                    if str(d.chat.id).replace("-100", "") == target_raw:
                        src_chat = d.chat; break
        
        if not src_chat:
            await status.edit("❌ **KAYNAK GRUP BULUNAMADI!**\nÖnce `/bul KAYNAK_LINK` komutunu kullanarak botun grubu tanımasını sağla.")
            return

        # --- HEDEF KANALI ALMA ---
        try: dst_chat = await userbot.get_chat(dst_data["id"])
        except: await status.edit("❌ Hedef grup bulunamadı."); return

        # --- İŞLEM BAŞLIYOR ---
        baslangic = f"Mesaj {src_data['msg_id']}" if src_data['msg_id'] else "En Baştan"
        await status.edit(f"🚀 **Transfer Başlıyor!**\nK: {src_chat.title}\nH: {dst_chat.title}\nMod: {baslangic}")

        msg_list = []
        async for m in userbot.get_chat_history(src_chat.id):
            if ABORT_FLAG: break
            
            # ID Filtresi (Belli mesajdan sonrası)
            if src_data["msg_id"] and m.id < src_data["msg_id"]: break
            
            # Topic Filtresi
            if src_data["topic_id"]:
                tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                if tid != src_data["topic_id"]: continue
                
            if m.video or m.photo or m.document:
                msg_list.append(m.id)

        msg_list.reverse()
        total = len(msg_list)
        
        if total == 0: await status.edit("❌ Medya yok."); return

        count = 0
        await status.edit(f"📥 **Aktarım: 0/{total}**")

        for mid in msg_list:
            if ABORT_FLAG: await status.edit("🛑 Durdu."); return

            try:
                msg = await userbot.get_messages(src_chat.id, mid)
                if not msg: continue
                path = await download_safe(userbot, msg)
                if not path: continue
                
                s_args = {}
                # Hedef Topic
                target_top = dst_data["topic_id"] or dst_data["msg_id"]
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

        await bot.send_message(message.chat.id, f"✅ **Tamamlandı!** {count} dosya.")

    except Exception as e:
        await status.edit(f"❌ Hata: {e}")

# ==================== TEKLİ İNDİRME ====================
@bot.on_message(filters.command("tekli"))
async def tekli_cmd(client, message):
    # (Yukarıdaki transfer mantığının aynısı tekli için de geçerli)
    # Önce Cache kontrolü eklenerek burası da çalışır hale gelir.
    try: link = message.command[1]; data = parse_full_link(link)
    except: await message.reply("❌ Link gir."); return

    status = await message.reply("🔄 **İşleniyor...**")
    try:
        # Önce Cache'e bak
        if data["id"] in FOUND_CHATS_CACHE:
            chat = FOUND_CHATS_CACHE[data["id"]]
        else:
            # Yoksa manuel ara
            chat = None
            target_raw = str(data["id"]).replace("-100", "")
            async for d in userbot.get_dialogs():
                if str(d.chat.id).replace("-100", "") == target_raw:
                    chat = d.chat; break
        
        if not chat:
            await status.edit("❌ Grup bulunamadı! `/bul` komutunu kullan.")
            return

        msg = await userbot.get_messages(chat.id, data["msg_id"])
        path = await download_safe(userbot, msg)
        
        await status.edit("📤 **Yükleniyor...**")
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
