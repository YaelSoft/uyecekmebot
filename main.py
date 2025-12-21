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

# ÇİFT MOTOR İÇİN SESSIONLAR
SESSION1 = os.environ.get("SESSION_STRING", "")
SESSION2 = os.environ.get("SESSION_STRING_2", "") 

# ==================== 2. WEB SERVER ====================
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route('/')
def home(): return "YaelSaver V59 (Dual + Fix) Active! 🟢"

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
        return True, "🟢 Deneme"
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

# ==================== 4. İSTEMCİLER (ÇOKLU MOTOR) ====================
init_db()
bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

USERBOTS = []
# 1. Botu Ekle
if SESSION1:
    USERBOTS.append(Client("ub1", api_id=API_ID, api_hash=API_HASH, session_string=SESSION1, in_memory=True))
# 2. Botu Ekle (Varsa)
if SESSION2:
    USERBOTS.append(Client("ub2", api_id=API_ID, api_hash=API_HASH, session_string=SESSION2, in_memory=True))

# ==================== 5. MENÜLER ====================
def main_menu(user_id):
    btns = [
        [InlineKeyboardButton("📥 İçerik İndir", callback_data="help_dl"),
         InlineKeyboardButton("👤 Hesabım", callback_data="my_account")],
        [InlineKeyboardButton("👑 VIP Menüsü", callback_data="vip_menu")],
        [InlineKeyboardButton("🛠 Satın Al: @yasin33", url="https://t.me/yasin33")]
    ]
    if user_id == OWNER_ID: btns.append([InlineKeyboardButton("👮‍♂️ Admin", callback_data="admin_panel")])
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
def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="main")]])

# ==================== 6. START & CALLBACKS ====================
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply(f"⛔ **Süre Doldu!**"); return
    
    count = len(USERBOTS)
    await message.reply(f"👋 **YaelSaver V59**\nℹ️ Durum: {status}\n🤖 Motorlar: {count} Adet Aktif", reply_markup=main_menu(user_id))

@bot.on_callback_query()
async def cb_handler(client, cb):
    uid = cb.from_user.id
    data = cb.data
    if data == "main": await cb.message.edit_text("👋 **Ana Menü**", reply_markup=main_menu(uid))
    elif data == "help_dl": await cb.message.edit_text("📥 Link at (`t.me/c/...`).", reply_markup=back_btn())
    elif data == "my_account": _, st = check_user_access(uid); await cb.message.edit_text(f"📊 {st}", reply_markup=back_btn())
    elif data == "vip_menu": await cb.message.edit_text("👑 **VIP**", reply_markup=vip_menu())
    elif data == "help_trans": await cb.message.edit_text("🔄 `/transfer Kaynak Hedef Limit`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="vip_menu")]]))
    elif data == "admin_panel":
        if uid != OWNER_ID: await cb.answer("Yasak!", show_alert=True); return
        await cb.message.edit_text("👮‍♂️ Admin", reply_markup=admin_menu())
    elif data == "how_add": await cb.message.edit_text("`/addvip ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))
    elif data == "how_del": await cb.message.edit_text("`/delvip ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))

# ==================== 7. ÇİFT MOTORLU ZEKA (BRAIN) ====================

async def force_scan_all_bots(target_id):
    """
    Tüm botlar sırayla hafızasını tazeler ve kanalı arar.
    Bulunan ilk botu döndürür.
    """
    for ub in USERBOTS:
        try:
            # Hafızayı tazele
            async for dialog in ub.get_dialogs(limit=50): pass 
            
            # Kanalı tanıyor mu bak
            try:
                await ub.get_chat(target_id)
                return ub # Bu bot kanalı tanıyor!
            except:
                continue
        except: continue
    return None

async def try_join_all(link):
    """Bütün botlarla girmeyi dener."""
    for ub in USERBOTS:
        try:
            await ub.join_chat(link)
            return True, ub # Girdi
        except UserAlreadyParticipant:
            return True, ub # Zaten içeride
        except:
            continue
    return False, None

@bot.on_message(filters.regex(r"t\.me/") & filters.private)
async def link_handler(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if not access: await message.reply("⛔ **Süre Doldu!**"); return

    text = message.text.strip()
    
    # A) DAVET LİNKİ
    if "+" in text or "joinchat" in text:
        status_msg = await message.reply("🕵️ **Motorlar Deneniyor...**")
        success, _ = await try_join_all(text)
        
        if success:
            await status_msg.edit("✅ **Giriş Başarılı!**\nBir userbot gruba girdi. Şimdi içerik linkini at.")
        else:
            await status_msg.edit("❌ **Hiçbir bot giremedi!** Link bozuk veya hepsi banlı.")
        return

    # B) MESAJ LİNKİ
    status_msg = await message.reply("🔍 **Veri Aranıyor...**")
    
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
            
        # 1. Hangi bot kanalı görüyor?
        working_ub = None
        msg = None

        # Botları sırayla dene
        for ub in USERBOTS:
            try:
                msg = await ub.get_messages(chat_id, msg_id)
                if msg and not msg.empty:
                    working_ub = ub
                    break
            except (PeerIdInvalid, ChannelInvalid):
                continue # Bu bot görmüyor, diğerine geç
            except:
                continue

        # Eğer hiçbir bot bulamadıysa, Zorla Tarama (Force Scan) yap
        if not working_ub:
            await status_msg.edit("🔄 **Derin Tarama Yapılıyor (Hafıza Tazeleme)...**")
            working_ub = await force_scan_all_bots(chat_id)
            
            if working_ub:
                # Bulduysak tekrar çekmeyi dene
                msg = await working_ub.get_messages(chat_id, msg_id)

        if not working_ub or not msg or msg.empty:
            raise ChannelPrivate("Hiçbir bot erişemedi")

        # İNDİRME
        await status_msg.edit("📥 **İndiriliyor...**")
        
        if msg.media:
            # Doğru bot ile indir
            path = await working_ub.download_media(msg)
            if path:
                await status_msg.edit("📤 **Gönderiliyor...**")
                await client.send_document(user_id, path, caption=msg.caption or "")
                os.remove(path); await status_msg.delete()
        else:
            await client.send_message(user_id, msg.text)
            await status_msg.delete()

    except (ChannelPrivate, PeerIdInvalid):
        await status_msg.edit("⛔ **ERİŞİM YOK!**\nAktif botların hiçbiri bu grupta değil.\nLütfen Davet Linki at.")
    except Exception as e:
        await status_msg.edit(f"❌ **Hata:** {e}")

# ==================== 8. TRANSFER ====================
@bot.on_message(filters.command("transfer") & filters.private)
async def transfer(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Sadece VIP!**"); return

    if not USERBOTS: await message.reply("❌ Userbot yok!"); return

    try:
        args = message.command
        src, dst, limit = int(args[1]), int(args[2]), int(args[3])
        status_msg = await message.reply("🚀 **Başlıyor...**")
        
        # Transfer için 1. Botu kullanalım (Varsayılan)
        ub = USERBOTS[0]
        
        # Ön kontrol
        try: await ub.get_chat(src)
        except: await force_scan_all_bots(src)

        count = 0
        async for msg in ub.get_chat_history(src, limit=limit):
            try:
                if msg.media: await msg.copy(dst, caption=msg.caption)
                elif msg.text: await ub.send_message(dst, msg.text)
                count += 1
                await asyncio.sleep(2)
                if count % 10 == 0: await status_msg.edit(f"🚀 Taşınan: {count}...")
            except FloodWait as e: await asyncio.sleep(e.value + 5)
            except: pass
        await status_msg.edit(f"✅ **Bitti!** Toplam: {count}")
    except: await message.reply("❌ Hata! `/transfer Kaynak Hedef Limit`")

# ==================== 9. ADMİN ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅")
@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌")

# ==================== 10. BAŞLATMA ====================
async def main():
    print("Sistem Başlatılıyor...")
    keep_alive()
    await bot.start()
    
    print(f"Toplam {len(USERBOTS)} Bot Başlatılıyor...")
    for i, ub in enumerate(USERBOTS):
        try:
            await ub.start()
            print(f"✅ Bot {i+1} Aktif!")
        except Exception as e:
            print(f"⚠️ Bot {i+1} Hatası: {e}")

    await idle()
    await bot.stop()
    for ub in USERBOTS:
        try: await ub.stop()
        except: pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
