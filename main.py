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
SESSION3 = os.environ.get("SESSION_STRING_3", "")

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
if SESSION3: USERBOTS.append(Client("ub3", api_id=API_ID, api_hash=API_HASH, session_string=SESSION3, in_memory=True))

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
# ==================== 8. ULTRA TRANSFER (RESTRICTED + ROTASYONLU) ====================
import time

# İlerleme durumunu kaydetmek için
def save_progress(chat_id, last_id):
    with open(f"log_{chat_id}.txt", "w") as f:
        f.write(str(last_id))

def load_progress(chat_id):
    if os.path.exists(f"log_{chat_id}.txt"):
        with open(f"log_{chat_id}.txt", "r") as f:
            return int(f.read().strip())
    return 0

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_restricted(client, message):
    user_id = message.from_user.id
    access, status = check_user_access(user_id)
    
    # Sadece VIP ve Admin
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Bu özellik VVIP müşterilere özeldir.**\nDevasa arşivleri sıfır hatayla taşır."); return

    if not USERBOTS: await message.reply("❌ Sistemde Userbot yok!"); return

    try:
        args = message.command
        # Komut: /transfer KAYNAK_ID HEDEF_ID LIMIT
        src_id = int(args[1])
        dst_id = int(args[2])
        limit_count = int(args[3])
    except:
        await message.reply("⚠️ **Kullanım:** `/transfer -100KaynakID -100HedefID 500`\n(Limit yerine 0 yazarsan hepsini dener)")
        return

    status_msg = await message.reply(f"🚀 **Transfer Başlatılıyor...**\n\n🎯 Kaynak: `{src_id}`\n🎯 Hedef: `{dst_id}`\n🤖 Bot Sayısı: {len(USERBOTS)}\n\n⏳ **Analiz yapılıyor, lütfen bekle...**")

    # 1. Userbot ile kanala erişim kontrolü
    active_bot_index = 0
    main_ub = USERBOTS[0]
    
    try: await main_ub.get_chat(src_id)
    except: 
        await status_msg.edit("⚠️ Userbot kanalı göremiyor! Link ile katılması lazım.")
        return

    # 2. Mesajları Çek ve Sırala (Eskiden Yeniye)
    all_messages = []
    # Son kalınan yeri yükle
    last_processed_id = load_progress(src_id)
    
    await status_msg.edit("📦 **Mesajlar taranıyor... (Bu işlem medya sayısına göre sürer)**")
    
    # 0 limitse çoklu çeker, değilse limit kadar
    limit_val = limit_count if limit_count > 0 else 5000 
    
    async for msg in main_ub.get_chat_history(src_id, limit=limit_val):
        all_messages.append(msg)
    
    # LİSTEYİ TERS ÇEVİR (ESKİDEN YENİYE OLMASI İÇİN)
    all_messages.reverse()
    
    total_count = len(all_messages)
    processed = 0
    
    await status_msg.edit(f"✅ **Analiz Bitti!**\nToplam: {total_count} Mesaj\nKaldığım ID: {last_processed_id}\n\n🚀 **Transfer Başlıyor...**")

    for msg in all_messages:
        # Eğer bu mesajı daha önce işlediysek atla
        if msg.id <= last_processed_id:
            continue

        # Boş mesajları veya servis mesajlarını atla
        if msg.service or msg.empty:
            continue

        # ROTASYON DÖNGÜSÜ (Hata alırsak diğer bota geçmek için)
        sent = False
        retry_count = 0
        
        while not sent and retry_count < 3:
            current_ub = USERBOTS[active_bot_index]
            
            try:
                # EĞER MEDYA VARSA (İNDİR -> YÜKLE -> SİL)
                if msg.media:
                    caption = msg.caption or ""
                    
                    # Dosyayı İndir
                    file_path = await current_ub.download_media(msg)
                    
                    if file_path:
                        # Dosyayı Yükle (Caption ile)
                        if msg.photo:
                            await current_ub.send_photo(dst_id, file_path, caption=caption)
                        elif msg.video:
                            await current_ub.send_video(dst_id, file_path, caption=caption)
                        elif msg.document:
                            await current_ub.send_document(dst_id, file_path, caption=caption)
                        elif msg.audio:
                            await current_ub.send_audio(dst_id, file_path, caption=caption)
                        elif msg.voice:
                            await current_ub.send_voice(dst_id, file_path)
                        
                        # Render diskini doldurmamak için SİL
                        os.remove(file_path)
                        sent = True
                
                # SADECE YAZIYSA
                elif msg.text:
                    await current_ub.send_message(dst_id, msg.text)
                    sent = True
                
                # Başarılı olursa bekleme süresi (Spam yememek için)
                time.sleep(3) 

            except FloodWait as e:
                wait_time = e.value
                print(f"⚠️ Bot {active_bot_index+1} FloodWait yedi: {wait_time} saniye.")
                
                # DİĞER BOTA GEÇ
                active_bot_index = (active_bot_index + 1) % len(USERBOTS)
                print(f"🔄 Bot Değiştirildi -> Bot {active_bot_index+1} Devrede!")
                
                # Eğer yeni geçen bot da cezalıysa azıcık uyu
                time.sleep(2)
                retry_count += 1
            
            except Exception as e:
                print(f"Hata: {e}")
                retry_count += 1
                time.sleep(1)

        if sent:
            processed += 1
            save_progress(src_id, msg.id) # İlerlemeyi kaydet
            
            # Her 10 mesajda bir bilgi ver
            if processed % 10 == 0:
                try:
                    await status_msg.edit(f"🚀 **Transfer Devam Ediyor...**\n\n✅ İşlenen: {processed} / {total_count}\n🤖 Aktif Bot: {active_bot_index+1}")
                except: pass

    await status_msg.edit(f"🏁 **TRANSFER TAMAMLANDI!**\n\nToplam {processed} içerik başarıyla kopyalandı.")
    # İş bitince log dosyasını silebilirsin istersen
    if os.path.exists(f"log_{src_id}.txt"): os.remove(f"log_{src_id}.txt")


# ==================== 9. ADMİN ====================
@bot.on_message(filters.command("addvip") & filters.user(OWNER_ID))
async def addvip(c, m): set_vip(int(m.command[1]), True); await m.reply("✅")
@bot.on_message(filters.command("delvip") & filters.user(OWNER_ID))
async def delvip(c, m): set_vip(int(m.command[1]), False); await m.reply("❌")
# ==================== ID BULUCU (GİZLİ & YASAKLI GRUP FİX) ====================
@bot.on_message(filters.command("id") & filters.private)
async def id_finder(client, message):
    user_id = message.from_user.id
    
    # 1. VIP Kontrolü
    access, status = check_user_access(user_id)
    if "VIP" not in status and user_id != OWNER_ID:
        await message.reply("🔒 **Bu özellik sadece VIP müşteriler içindir.**")
        return

    # 2. Userbot Kontrolü
    if not USERBOTS:
        await message.reply("❌ Sistemde aktif Userbot yok!")
        return
    ub = USERBOTS[0] # İlk userbotu kullan

    # 3. Link Kontrolü
    if len(message.command) < 2:
        await message.reply(
            "🆔 **ID Bulucu**\n\n"
            "Grubun linkini yanına yazman lazım.\n"
            "İletim yasağı olsa bile ID'yi bulabilirim.\n\n"
            "📌 **Örnek:**\n"
            "`/id https://t.me/+AhmetinGrubu...`"
        )
        return

    link = message.text.split(None, 1)[1].strip()
    status_msg = await message.reply("🕵️ **Link taranıyor...**")

    try:
        chat = None
        
        # A) GİZLİ LİNK (+Link veya joinchat)
        if "+" in link or "joinchat" in link:
            try:
                # Önce girmeye çalış
                chat = await ub.join_chat(link)
            except UserAlreadyParticipant:
                # Zaten içerdeysek, içeride olduğumuz yetkisiyle bilgileri çek
                chat = await ub.get_chat(link)
        
        # B) GENEL LİNK (@kullaniciadi)
        else:
            chat = await ub.get_chat(link)

        # SONUÇ
        if chat:
            chat_id = chat.id
            title = chat.title
            # Üye sayısını güvenli çekme
            members = chat.members_count if chat.members_count else "Gizli"
            
            text = (
                f"✅ **Hedef Bulundu!**\n\n"
                f"📛 **Grup:** {title}\n"
                f"🆔 **ID:** `{chat_id}`\n"
                f"👥 **Üye:** {members}\n\n"
                f"👇 **Transfer Kodu:**\n"
                f"`/transfer {chat_id} HEDEF_KANAL_ID 100`"
            )
            await status_msg.edit(text)

    except InviteHashExpired:
        await status_msg.edit("❌ **Linkin süresi dolmuş!** Müşteriden yeni link iste.")
    except FloodWait as e:
        await status_msg.edit(f"⏳ **Çok hızlı işlem.** {e.value} saniye bekle.")
    except Exception as e:
        await status_msg.edit(f"❌ **Hata:** Gruba erişemedim. Userbot'un banlanmadığından emin ol.\n`{e}`")
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

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())


