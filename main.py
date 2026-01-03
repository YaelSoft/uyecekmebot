import os
import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    UserAlreadyParticipant, InviteHashExpired, ChannelPrivate, 
    PeerIdInvalid, FloodWait, UsernameInvalid, ChannelInvalid
)

# ==================== 1. AYARLAR ====================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# ÇİFT MOTOR SESSIONLAR
SESSION1 = os.environ.get("SESSION_STRING", "")
SESSION2 = os.environ.get("SESSION_STRING_2", "")

# ==================== 2. WEB SERVER ====================
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V60 (Pro UI) Active! 🟢"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==================== 3. VERİTABANI ====================
DB_NAME = "yaelsaver.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT, join_date TEXT)''')
    conn.commit(); conn.close()

def check_user_access(user_id):
    if user_id == OWNER_ID: return True, "👑 Yönetici"
    conn = sqlite3.connect(DB_NAME)
    res = conn.cursor().execute("SELECT status, join_date FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not res: 
        conn.cursor().execute("INSERT INTO users VALUES (?, 'FREE', ?)", (user_id, datetime.now().isoformat()))
        conn.commit(); conn.close()
        return True, "🟢 Deneme (24 Saat)"
    status, join_str = res
    conn.close()
    if status == "VIP": return True, "💎 VIP"
    if datetime.now() < datetime.fromisoformat(join_str) + timedelta(hours=24): return True, "🟢 Deneme"
    return False, "🔴 Süre Doldu"

def set_vip(user_id, is_vip):
    status = "VIP" if is_vip else "FREE"
    with sqlite3.connect(DB_NAME) as conn:
        try: conn.cursor().execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, status, datetime.now().isoformat()))
        except: conn.cursor().execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))

# ==================== 4. İSTEMCİLER ====================
init_db()
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

USERBOTS = []
if SESSION1: USERBOTS.append(Client("ub1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
if SESSION2: USERBOTS.append(Client("ub2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))

# ==================== 5. YENİ MENÜLER (PROFESYONEL) ====================
def main_menu(user_id):
    btns = [
        [InlineKeyboardButton("📥 Nasıl Kullanılır?", callback_data="help_dl"),
         InlineKeyboardButton("📚 Komutlar", callback_data="cmd_list")],
        [InlineKeyboardButton("👤 Hesabım", callback_data="my_account"),
         InlineKeyboardButton("📞 İletişim / Satın Al", url="https://t.me/yasin33")],
        [InlineKeyboardButton("👑 VIP Menüsü (Transfer)", callback_data="vip_menu")]
    ]
    if user_id == OWNER_ID: btns.append([InlineKeyboardButton("👮‍♂️ Yönetici Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(btns)

def vip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Kanal Kopyala", callback_data="help_trans")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Ekle", callback_data="how_add"), InlineKeyboardButton("➖ Sil", callback_data="how_del")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]
    ])
def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="main")]])

# ==================== 6. START & CALLBACKS ====================
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    
    if not access: 
        await message.reply("⛔ **Deneme Süreniz Doldu!**\nSınırsız erişim için iletişime geçin: @yasin33")
        return
    
    txt = (
        f"👋 **Selam! Ben YaelSaver.**\n\n"
        f"🚀 **Ne İşe Yararım?**\n"
        f"Telegram'daki **gizli, kopyalama yasağı olan veya katılamadığınız** kanallardan "
        f"video, fotoğraf ve dosyaları indirip size sunarım.\n\n"
        f"🔻 **Nasıl Başlarım?**\n"
        f"Tek yapman gereken, içerik linkini bana göndermek.\n\n"
        f"📊 **Üyelik Durumunuz:** {status}"
    )
    await message.reply(txt, reply_markup=main_menu(user_id))

@bot.on_callback_query()
async def cb_handler(client, cb):
    uid = cb.from_user.id
    data = cb.data

    if data == "main": 
        access, status = check_user_access(uid)
        txt = (f"👋 **YaelSaver Paneli**\n\n📊 Durum: {status}\n🚀 Hazırım, link gönderebilirsin.")
        await cb.message.edit_text(txt, reply_markup=main_menu(uid))
    
    elif data == "cmd_list":
        msg = (
            "📚 **Komut Listesi**\n\n"
            "1️⃣ **Link Gönderme:**\n"
            "Direkt mesaj linkini (`t.me/c/...`) atarsan indiririm.\n\n"
            "2️⃣ **Davet Linki:**\n"
            "Eğer 'Erişim Yok' dersem, grubun davet linkini (`t.me/+...`) at, ben girerim.\n\n"
            "3️⃣ **Zincir Transfer (Topic):**\n"
            "`/zincir KaynakLink HedefLink`\n"
            "Belirtilen mesajdan başlar, hedef topic'e aktarır."
        )
        await cb.message.edit_text(msg, reply_markup=back_btn())

    elif data == "help_dl":
        msg = (
            "📥 **İçerik İndirme Rehberi**\n\n"
            "1. İndirmek istediğin mesajın üstüne gel, 'Bağlantıyı Kopyala' de.\n"
            "2. O linki bana yapıştır.\n"
            "3. Eğer **'Erişimim Yok'** dersem, o kanal gizlidir ve ben içinde değilimdir.\n"
            "4. O kanalın **Davet Linkini** bana atarsan, saniyesinde girer ve o içeriği indiririm."
        )
        await cb.message.edit_text(msg, reply_markup=back_btn())

    elif data == "my_account": _, st = check_user_access(uid); await cb.message.edit_text(f"📊 **Hesap Bilgisi**\n\nID: `{uid}`\nPaket: {st}", reply_markup=back_btn())
    elif data == "vip_menu": await cb.message.edit_text("👑 **VIP & Transfer İşlemleri**", reply_markup=vip_menu())
    elif data == "help_trans": await cb.message.edit_text("🔄 **Toplu Transfer**\n\nKomut: `/zincir Kaynak Hedef`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="vip_menu")]]))
    
    elif data == "admin_panel":
        if uid != OWNER_ID: await cb.answer("Yasak!", show_alert=True); return
        await cb.message.edit_text("👮‍♂️ **Yönetici Paneli**", reply_markup=admin_menu())
    elif data == "how_add": await cb.message.edit_text("VIP Ekleme:\n`/addvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))
    elif data == "how_del": await cb.message.edit_text("VIP Silme:\n`/delvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))

# ==================== 7. YARDIMCI FONKSİYONLAR ====================

async def force_scan_all_bots(target_id):
    for ub in USERBOTS:
        try:
            async for dialog in ub.get_dialogs(limit=50): pass 
            try:
                await ub.get_chat(target_id)
                return ub
            except: continue
        except: continue
    return None

async def try_join_all(link):
    for ub in USERBOTS:
        try:
            await ub.join_chat(link)
            return True, ub
        except UserAlreadyParticipant:
            return True, ub
        except: continue
    return False, None

# ==================== 8. TEKLİ İNDİRME (DÜZELTİLDİ: KOMUTLARA KARIŞMAZ) ====================
# BURASI ÇOK ÖNEMLİ: ~filters.regex(r"^/") sayesinde komutlara atlamaz!
@bot.on_message(filters.regex(r"t\.me/") & ~filters.regex(r"^/") & filters.private)
async def link_handler(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ **Süre Doldu!**"); return

    text = message.text.strip()
    
    # A) DAVET LİNKİ
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Gizli Gruba Sızılıyor...**")
        success, _ = await try_join_all(text)
        
        if success:
            await status_msg.edit("✅ **Başarılı!**\nUserbot gruba giriş yaptı.\nŞimdi indirmek istediğin mesajın linkini tekrar at.")
        else:
            await status_msg.edit("❌ **Giremedim!**\nLink bozuk olabilir veya userbotlarımın hepsi banlı/dolu.")
        return

    # B) MESAJ LİNKİ
    status_msg = await message.reply("🔍 **İçerik Aranıyor...**")
    
    try:
        clean = text.replace("https://t.me/", "").replace("@", "")
        if "c/" in clean:
            parts = clean.split("c/")[1].split("/")
            chat_id = int("-100" + parts[0])
            msg_id = int(parts[1])
        else:
            parts = clean.split("/")
            chat_id = parts[0]
            msg_id = int(parts[1])
            
        working_ub = None
        msg = None

        # Botları dene
        for ub in USERBOTS:
            try:
                msg = await ub.get_messages(chat_id, msg_id)
                if msg and not msg.empty:
                    working_ub = ub
                    break
            except: continue

        # Bulamazsa Zorla Tara
        if not working_ub:
            await status_msg.edit("🔄 **Sunucu Hafızası Tazeleniyor...**")
            working_ub = await force_scan_all_bots(chat_id)
            if working_ub:
                msg = await working_ub.get_messages(chat_id, msg_id)

        if not working_ub or not msg or msg.empty:
            raise ChannelPrivate("Erişim Yok")

        # İNDİRME
        await status_msg.edit("📥 **İndiriliyor...**")
        
        if msg.media:
            path = await working_ub.download_media(msg)
            if path:
                await status_msg.edit("📤 **Size Gönderiliyor...**")
                await client.send_document(user_id, path, caption=msg.caption or "")
                os.remove(path); await status_msg.delete()
        else:
            await client.send_message(user_id, msg.text)
            await status_msg.delete()

    except (ChannelPrivate, PeerIdInvalid):
        await status_msg.edit(
            "⛔ **ERİŞİM ENGELİ!**\n\n"
            "Userbotlarım bu grupta değil.\n"
            "👇 **Çözüm:**\n"
            "Grubun **Davet Linkini** (`t.me/+...`) bana atarsan otomatik girerim."
        )
    except Exception as e:
        await status_msg.edit(f"❌ **Hata:** {e}")

# ==================== 9. ZİNCİRLEME TRANSFER (Topic Destekli) ====================
ABORT_FLAG = False

@bot.on_message(filters.command("zincir") & filters.private)
async def chain_transfer_final(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    if not USERBOTS: await message.reply("❌ Userbot yok!"); return
    ub = USERBOTS[0]

    try:
        # KOMUT: /zincir [KAYNAK_LINK] [HEDEF_LINK]
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **KULLANIM:** `/zincir [KAYNAK_LINK] [HEDEF_LINK]`")
        return

    status = await message.reply("⚙️ **ZİNCİR BAŞLATILIYOR...**")

    # LİNK ÇÖZÜCÜ
    def resolve(link):
        data = {"id": None, "topic": None, "msg": 0}
        link = str(link).strip()
        try:
            if "c/" in link:
                clean = link.split("c/")[1].split("?")[0].split("/")
                data["id"] = int("-100" + clean[0])
                if len(clean) == 3: # Topicli: grup/topic/msg
                    data["topic"] = int(clean[1])
                    data["msg"] = int(clean[2])
                elif len(clean) == 2: # Topicsiz: grup/msg
                    data["msg"] = int(clean[1])
            elif "-100" in link:
                data["id"] = int(link)
        except: return None
        return data

    src = resolve(src_link)
    dst = resolve(dst_link)

    if not src or not dst: await status.edit("❌ Link Hatalı"); return

    # LİSTELEME
    await status.edit("📦 **LİSTE HAZIRLANIYOR...**")
    msg_ids = []
    
    try:
        async for m in ub.get_chat_history(src["id"]):
            if ABORT_FLAG: break
            if m.id < src["msg"]: continue # Eskileri atla
            
            # Kaynak Topic Filtresi
            if src["topic"]:
                try:
                    tid = getattr(m, "message_thread_id", None) or getattr(m, "reply_to_message_id", None)
                    if tid != src["topic"] and m.id != src["topic"]: continue
                except: continue
            
            msg_ids.append(m.id)
    except Exception as e:
        await status.edit(f"❌ Erişim Hatası: {e}"); return

    msg_ids.reverse() # Eskiden yeniye
    total = len(msg_ids)
    if total == 0: await status.edit("❌ Mesaj bulunamadı."); return

    await status.edit(f"🚀 **BAŞLADI**\nToplam: {total} Mesaj")

    # AKTARIM
    count = 0
    for msg_id in msg_ids:
        if ABORT_FLAG: await status.edit("🛑 Durduruldu."); return
        try:
            msg = await ub.get_messages(src["id"], msg_id)
            if not msg or msg.empty: continue

            # HEDEF TOPIC AYARI
            args = {}
            if dst["topic"]: args["reply_to_message_id"] = dst["topic"]

            # İNDİR VE GÖNDER
            if msg.media:
                try:
                    path = await ub.download_media(msg)
                    if path:
                        caption = msg.caption or ""
                        if msg.photo: await ub.send_photo(dst["id"], path, caption=caption, **args)
                        elif msg.video: await ub.send_video(dst["id"], path, caption=caption, **args)
                        elif msg.document: await ub.send_document(dst["id"], path, caption=caption, **args)
                        elif msg.audio: await ub.send_audio(dst["id"], path, caption=caption, **args)
                        elif msg.voice: await ub.send_voice(dst["id"], path, **args)
                        elif msg.sticker: await ub.send_sticker(dst["id"], path, **args)
                        elif msg.animation: await ub.send_animation(dst["id"], path, caption=caption, **args)
                        
                        os.remove(path)
                        count += 1
                except: pass
            
            elif msg.text and msg.text.strip():
                try:
                    await ub.send_message(dst["id"], msg.text, **args)
                    count += 1
                except: pass
            
            await asyncio.sleep(3) # Ban koruması
            
            if count % 5 == 0:
                try: await status.edit(f"🔄 **AKTARILIYOR...**\n✅ {count} / {total}")
                except: pass

        except FloodWait as e: await asyncio.sleep(e.value + 5)
        except: pass

    await status.edit(f"🏁 **TAMAMLANDI!**\n{count} mesaj aktarıldı.")

@bot.on_message(filters.command("iptal") & filters.private)
async def stop_process(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **DURDURULDU.**")

# ==================== 10. ADMİN ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅")
@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌")

# ==================== 11. BAŞLATMA ====================
async def main():
    print("Sistem Başlatılıyor...")
    keep_alive()
    await bot.start()
    for i, ub in enumerate(USERBOTS):
        try: await ub.start(); print(f"✅ Bot {i+1} Aktif!")
        except Exception as e: print(f"⚠️ Bot {i+1} Hata: {e}")
    await idle()
    await bot.stop()
    for ub in USERBOTS:
        try: await ub.stop()
        except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
