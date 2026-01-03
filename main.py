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
    
    # MÜŞTERİ DOSTU KARŞILAMA MESAJI
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
    
    # --- KOMUTLAR BÖLÜMÜ ---
    elif data == "cmd_list":
        msg = (
            "📚 **Komut Listesi**\n\n"
            "1️⃣ **Link Gönderme:**\n"
            "Direkt mesaj linkini (`t.me/c/...`) atarsan indiririm.\n\n"
            "2️⃣ **Davet Linki:**\n"
            "Eğer 'Erişim Yok' dersem, grubun davet linkini (`t.me/+...`) at, ben girerim.\n\n"
            "3️⃣ **Transfer (Sadece VIP):**\n"
            "`/transfer KaynakID HedefID Limit`\n"
            "Bir kanaldaki mesajları başka kanala kopyalar."
        )
        await cb.message.edit_text(msg, reply_markup=back_btn())

    # --- NASIL İNDİRİLİR ---
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
    elif data == "help_trans": await cb.message.edit_text("🔄 **Toplu Transfer**\n\nKomut: `/transfer -100xxx -100yyy 50`\n(KaynakID, HedefID, Adet)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="vip_menu")]]))
    
    elif data == "admin_panel":
        if uid != OWNER_ID: await cb.answer("Yasak!", show_alert=True); return
        await cb.message.edit_text("👮‍♂️ **Yönetici Paneli**", reply_markup=admin_menu())
    elif data == "how_add": await cb.message.edit_text("VIP Ekleme:\n`/addvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))
    elif data == "how_del": await cb.message.edit_text("VIP Silme:\n`/delvip KULLANICI_ID`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_panel")]]))

# ==================== 7. ÇİFT MOTORLU ZEKA (AYNI MANTIK) ====================

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

@bot.on_message(filters.regex(r"t\.me/") & filters.private)
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
# ==================== TEK VE NET TRANSFER KODU (MANUEL GİRİŞ) ====================

@bot.on_message(filters.command("baslat") & filters.private)
async def transfer_manuel_fix(client, message):
    # Kullanıcı ID kontrolü (İstersen burayı açarsın)
    # if message.from_user.id != OWNER_ID: return

    try:
        # KOMUT: /baslat KAYNAK_ID HEDEF_ID HEDEF_TOPIC_ID BASLANGIC_MESAJ_ID
        args = message.command
        src_id = int(args[1])
        dst_id = int(args[2])
        dst_topic = int(args[3])
        start_id = int(args[4])
    except:
        await message.reply("⚠️ **KULLANIM:** `/baslat -100KAYNAK -100HEDEF KONU_ID BASLANGIC_ID`")
        return

    status = await message.reply(f"🚀 **BAŞLIYOR...**\nKaynak: `{src_id}`\nHedef: `{dst_id}` (Konu: `{dst_topic}`)\nBaşlangıç: `{start_id}`")

    ub = USERBOTS[0] # İlk botu kullan
    msg_ids = []

    # 1. LİSTELEME (Sadece ID çeker, hata vermez)
    try:
        async for msg in ub.get_chat_history(src_id):
            # Sadece senin istediğin mesajdan yeni olanları listeye al
            if msg.id >= start_id:
                msg_ids.append(msg.id)
    except Exception as e:
        await status.edit(f"❌ **LİSTE ÇEKİLEMEDİ:** {e}\n(Bot kaynak grupta mı?)")
        return

    # Eskiden yeniye sırala
    msg_ids.reverse()
    total = len(msg_ids)

    if total == 0:
        await status.edit("❌ **MESAJ BULUNAMADI.** Başlangıç ID'si çok büyük olabilir.")
        return

    await status.edit(f"✅ **LİSTE TAMAM.**\nToplam: {total} mesaj aktarılacak.")
    
    count = 0
    
    # 2. AKTARIM DÖNGÜSÜ
    for msg_id in msg_ids:
        try:
            # Mesajı getir
            msg = await ub.get_messages(src_id, msg_id)
            
            # Boşsa geç
            if not msg or msg.empty or msg.service: continue

            # --- HEDEF KONU AYARI (ESKİ SÜRÜM GARANTİSİ) ---
            # Mesaja 'reply' atarak topic'e düşmesini sağlarız.
            target_params = {"reply_to_message_id": dst_topic}

            # İNDİRME VE GÖNDERME
            if msg.media:
                try:
                    path = await ub.download_media(msg)
                    if path:
                        caption = msg.caption or ""
                        if msg.photo: await ub.send_photo(dst_id, path, caption=caption, **target_params)
                        elif msg.video: await ub.send_video(dst_id, path, caption=caption, **target_params)
                        elif msg.document: await ub.send_document(dst_id, path, caption=caption, **target_params)
                        elif msg.audio: await ub.send_audio(dst_id, path, caption=caption, **target_params)
                        elif msg.voice: await ub.send_voice(dst_id, path, **target_params)
                        elif msg.sticker: await ub.send_sticker(dst_id, path, **target_params)
                        
                        os.remove(path)
                        count += 1
                except Exception as e:
                    print(f"Medya hatası (ID: {msg_id}): {e}")
                    # Hata varsa geç, durma
                    pass

            elif msg.text:
                if msg.text.strip():
                    await ub.send_message(dst_id, msg.text, **target_params)
                    count += 1

            # 3 SANİYE BEKLE (Ban yememek için)
            await asyncio.sleep(3)

            # Her 10 mesajda bir bilgi ver
            if count % 10 == 0:
                try: await status.edit(f"🔄 **AKTARILIYOR...**\n{count} / {total}")
                except: pass

        except FloodWait as e:
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            print(f"Genel Hata (ID: {msg_id}): {e}")
            pass # Hata olsa da durma, devam et

    await status.edit(f"🏁 **BİTTİ!** Toplam {count} mesaj aktarıldı.")
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
    for i, ub in enumerate(USERBOTS):
        try: await ub.start(); print(f"✅ Bot {i+1} Aktif!")
        except Exception as e: print(f"⚠️ Bot {i+1} Hata: {e}")
    await idle()
    await bot.stop()
    for ub in USERBOTS:
        try: await ub.stop()
        except: pass

    if os.path.exists(f"log_{src_id}_{src_topic_id}.txt"): os.remove(f"log_{src_id}_{src_topic_id}.txt")
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())


























