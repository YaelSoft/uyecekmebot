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
# ==================== 8. TRANSFER (V24 - SON NOKTA / HATA YUTUCU) ====================
import time
import asyncio
import os
from pyrogram.errors import FloodWait, PeerFlood, UserRestricted, MessageEmpty, MessageIdInvalid, BadRequest

ABORT_FLAG = False

# --- LOG SİSTEMİ ---
def save_progress(chat_id, last_id):
    with open(f"log_{chat_id}.txt", "w") as f: f.write(str(last_id))

def load_progress(chat_id):
    if os.path.exists(f"log_{chat_id}.txt"):
        with open(f"log_{chat_id}.txt", "r") as f: return int(f.read().strip())
    return 0

def get_progress_bar(current, total):
    if total < 1: return "[░░░░░░░░░░] %0"
    percentage = current / total
    finished_length = int(percentage * 10)
    bar = "▓" * finished_length + "░" * (10 - finished_length)
    return f"[{bar}] %{int(percentage * 100)}"

async def parse_input(input_str, ub):
    data = {"chat_id": None, "start_msg": 0}
    input_str = str(input_str).strip()
    if input_str.startswith("-100"):
        data["chat_id"] = int(input_str)
        return data
    if "t.me/" in input_str:
        try:
            if "+" in input_str or "joinchat" in input_str:
                try: chat = await ub.join_chat(input_str)
                except: chat = await ub.get_chat(input_str)
                data["chat_id"] = chat.id
            elif "c/" in input_str:
                parts = input_str.split("c/")[1].split("?")[0].split("/")
                data["chat_id"] = int("-100" + parts[0])
                if len(parts) >= 2: data["start_msg"] = int(parts[-1])
            else:
                parts = input_str.split("t.me/")[1].split("/")
                username = parts[0]
                chat = await ub.join_chat(username)
                data["chat_id"] = chat.id
                if len(parts) > 1: data["start_msg"] = int(parts[1])
        except Exception as e:
            print(f"Link Hatası: {e}")
    return data

@bot.on_message(filters.command("iptal") & filters.private)
async def stop_process(client, message):
    global ABORT_FLAG
    ABORT_FLAG = True
    await message.reply("🛑 **DURDURULDU.**")

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_v24_judgment(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    user_id = message.from_user.id
    active_bots = USERBOTS[:2]
    SAFETY_DELAY = 3 

    if not active_bots: await message.reply("❌ Userbot yok!"); return

    try:
        src_link = message.command[1]
        dst_link = message.command[2]
    except:
        await message.reply("⚠️ **Kullanım:** `/transfer [KAYNAK] [HEDEF]`")
        return

    status_msg = await message.reply(f"🛡️ **V24 TRANSFER BAŞLIYOR...**")

    scanner = active_bots[0]
    src = await parse_input(src_link, scanner)
    dst = await parse_input(dst_link, scanner)

    if not src["chat_id"] or not dst["chat_id"]:
        await status_msg.edit(f"❌ **HATA:** ID Bulunamadı."); return

    # LİSTELEME
    await status_msg.edit(f"📦 **LİSTE ÇEKİLİYOR...**")
    msg_ids = []
    try:
        async for msg in scanner.get_chat_history(src["chat_id"]):
            if ABORT_FLAG: break
            msg_ids.append(msg.id)
    except Exception as e:
        await status_msg.edit(f"❌ **Erişim Hatası:** {e}"); return

    if ABORT_FLAG: await status_msg.edit("🛑 İptal."); return

    msg_ids.reverse() 
    
    if src["start_msg"] > 0:
        todo_ids = [mid for mid in msg_ids if mid >= src["start_msg"]]
    else:
        last_processed = load_progress(src["chat_id"])
        todo_ids = [mid for mid in msg_ids if mid > last_processed]

    total_todo = len(todo_ids)
    if total_todo == 0: await status_msg.edit(f"✅ **Güncel!**"); return

    processed_count = 0
    bot_index = 0
    
    await status_msg.edit(f"🚀 **BAŞLIYOR...**\nKalan: {total_todo}")

    for current_msg_id in todo_ids:
        if ABORT_FLAG: await status_msg.edit("🛑 Durduruldu."); return

        sent = False
        retry = 0
        
        while not sent and retry < len(active_bots) * 2: 
            current_ub = active_bots[bot_index]
            try:
                # 1. MESAJI ÇEK
                try:
                    msg = await current_ub.get_messages(src["chat_id"], current_msg_id)
                except Exception:
                    # Mesaj çekilemiyorsa (Silinmişse) ATLA
                    sent = True; break

                # 2. BOŞ KONTROLÜ
                if not msg or msg.empty or msg.service:
                    sent = True; break

                # 3. İŞLEM (TRY-EXCEPT İÇİNDE TRY-EXCEPT)
                # Burası "Message Empty" hatasını yutar
                try:
                    if msg.media:
                        caption = msg.caption or ""
                        # İndir
                        file_path = await current_ub.download_media(msg)
                        
                        # DOSYA VAR MI VE DOLU MU?
                        if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                            if msg.photo: await current_ub.send_photo(dst["chat_id"], file_path, caption=caption)
                            elif msg.video: await current_ub.send_video(dst["chat_id"], file_path, caption=caption)
                            elif msg.document: await current_ub.send_document(dst["chat_id"], file_path, caption=caption)
                            elif msg.audio: await current_ub.send_audio(dst["chat_id"], file_path, caption=caption)
                            elif msg.voice: await current_ub.send_voice(dst["chat_id"], file_path)
                            elif msg.sticker: await current_ub.send_sticker(dst["chat_id"], file_path)
                            elif msg.animation: await current_ub.send_animation(dst["chat_id"], file_path, caption=caption)
                            else: await current_ub.send_document(dst["chat_id"], file_path, caption=caption)
                            
                            os.remove(file_path)
                            sent = True
                        else:
                            # Dosya inmemişse ATLA, hata verme
                            sent = True
                    
                    elif msg.text:
                        # Boş metin kontrolü
                        if msg.text.strip():
                            await current_ub.send_message(dst["chat_id"], msg.text)
                        sent = True
                    else:
                        sent = True

                except (MessageEmpty, BadRequest) as e:
                    # İŞTE BURASI HATAYI YUTAR
                    # 400 Hatası gelirse (Message Empty vb.)
                    print(f"⚠️ HATA YUTULDU (ID {current_msg_id}): {e}")
                    sent = True # Gönderilmiş say, döngüyü kır, sonraki mesaja geç
                    
                await asyncio.sleep(SAFETY_DELAY)

            except (FloodWait, PeerFlood, UserRestricted) as e:
                wait_sec = e.value if isinstance(e, FloodWait) else 60
                bot_index = (bot_index + 1) % len(active_bots)
                retry += 1; await asyncio.sleep(5) 
            except Exception as e:
                print(f"Genel Hata: {e}")
                # Kritik olmayan her hatada atla
                sent = True 
                await asyncio.sleep(1)

        if sent:
            processed_count += 1
            save_progress(src["chat_id"], current_msg_id)
            if processed_count % 5 == 0:
                try:
                    bar = get_progress_bar(processed_count, total_todo)
                    await status_msg.edit(f"🛡️ **V24 TRANSFER**\n{bar}\n✅ {processed_count} / {total_todo}")
                except: pass

    await status_msg.edit(f"🏁 **TAMAMLANDI!**\n{processed_count} içerik aktarıldı.")
    if os.path.exists(f"log_{src['chat_id']}.txt"): os.remove(f"log_{src['chat_id']}.txt")
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
# ==================== 9. TOPIC TRANSFER (KONUDAN KONUYA NOKTA ATIŞI) ====================
import time
import asyncio
import os
from pyrogram.errors import FloodWait, PeerFlood, UserRestricted

ABORT_FLAG = False

# --- LOG SİSTEMİ (Topic Bazlı) ---
# Her topic'in logunu ayrı tutuyoruz ki karışmasın
def save_topic_progress(chat_id, topic_id, last_id):
    filename = f"log_{chat_id}_{topic_id}.txt"
    with open(filename, "w") as f: f.write(str(last_id))

def load_topic_progress(chat_id, topic_id):
    filename = f"log_{chat_id}_{topic_id}.txt"
    if os.path.exists(filename):
        with open(filename, "r") as f: return int(f.read().strip())
    return 0

def get_progress_bar(current, total):
    if total < 1: return "[░░░░░░░░░░] %0"
    percentage = current / total
    finished_length = int(percentage * 10)
    bar = "▓" * finished_length + "░" * (10 - finished_length)
    return f"[{bar}] %{int(percentage * 100)}"

# --- LİNK/ID ÇÖZÜCÜ ---
async def join_and_resolve(input_str):
    target_id = None
    input_str = str(input_str).strip()
    for ub in USERBOTS:
        try:
            if "t.me" in input_str:
                if "+" in input_str or "joinchat" in input_str:
                    try: chat = await ub.join_chat(input_str)
                    except: chat = await ub.get_chat(input_str)
                elif "c/" in input_str:
                    clean = input_str.split("c/")[1].split("/")[0]
                    target_id = int("-100" + clean)
                    return target_id
                else:
                    username = input_str.split("t.me/")[-1].replace("/", "")
                    chat = await ub.join_chat(username)
                if chat: target_id = chat.id
            else:
                target_id = int(input_str)
                await ub.get_chat(target_id)
        except: pass
    return target_id

@bot.on_message(filters.command("topictransfer") & filters.private)
async def topic_transfer_safe(client, message):
    global ABORT_FLAG
    ABORT_FLAG = False
    
    user_id = message.from_user.id
    active_bots = USERBOTS[:2]
    
    # 🛡️ GÜVENLİK GECİKMESİ (4 Saniye)
    SAFETY_DELAY = 4

    if not active_bots: await message.reply("❌ Userbot yok!"); return

    try:
        # Komut: /topictransfer GRUP_ID KAYNAK_TOPIC HEDEF_GRUP HEDEF_TOPIC
        args = message.command
        src_grp_input = args[1]
        src_topic_id = int(args[2])
        dst_grp_input = args[3]
        dst_topic_id = int(args[4])
    except:
        await message.reply(
            "⚠️ **Kullanım:**\n"
            "`/topictransfer KAYNAK_GRUP TOPIC_ID HEDEF_GRUP HEDEF_TOPIC`\n\n"
            "📌 **Örnek:**\n"
            "`/topictransfer -10011111 45 -10022222 12`\n"
            "*(Kaynak Gruptaki 45 nolu konuyu, Hedef Gruptaki 12 nolu konuya atar)*"
        )
        return

    status_msg = await message.reply(f"🎯 **TOPIC SNIPER MODU**\nVeriler analiz ediliyor...")

    # Grupları Çöz
    src_id = await join_and_resolve(src_grp_input)
    dst_id = await join_and_resolve(dst_grp_input)

    if not src_id or not dst_id:
        await status_msg.edit(f"❌ **HATA:** Grup ID'leri bulunamadı.")
        return

    # 2. LİSTELEME (Sadece o Topic'i çeker)
    await status_msg.edit(f"📦 **KONU İÇERİĞİ ÇEKİLİYOR...**\nSadece {src_topic_id} nolu konu taranıyor.")
    
    msg_ids = []
    scanner = active_bots[0]
    
    try:
        # message_thread_id PARAMETRESİ KRİTİK NOKTADIR
        async for msg in scanner.get_chat_history(src_id, message_thread_id=src_topic_id):
            if ABORT_FLAG: break
            msg_ids.append(msg.id)
    except Exception as e:
        await status_msg.edit(f"❌ **Liste Hatası:** {e}\nTopic ID yanlış olabilir veya grup forum değildir.")
        return

    if ABORT_FLAG: await status_msg.edit("🛑 İptal."); return

    # 3. SIRALAMA
    msg_ids.reverse() # Eskiden Yeniye
    
    # O Topic için kaldığı yeri yükle
    last_processed_id = load_topic_progress(src_id, src_topic_id)
    todo_ids = [mid for mid in msg_ids if mid > last_processed_id]
    total_todo = len(todo_ids)
    
    if total_todo == 0:
        await status_msg.edit(f"✅ **Bu Konu Zaten Güncel!**")
        return

    # 4. TRANSFER
    processed_count = 0
    bot_index = 0
    bot_names = ["1 (Asıl)", "2 (Yedek)"]
    
    await status_msg.edit(f"🚀 **TRANSFER BAŞLADI**\nKonudan Konuya: {src_topic_id} -> {dst_topic_id}\nAdet: {total_todo}\nHız: 4sn (Güvenli)")

    for current_msg_id in todo_ids:
        if ABORT_FLAG: await status_msg.edit("🛑 Durduruldu."); return

        sent = False
        retry = 0
        
        while not sent and retry < len(active_bots) * 2: 
            current_ub = active_bots[bot_index]
            try:
                # Canlı Çekim
                msg = await current_ub.get_messages(src_id, current_msg_id)
                
                if not msg or msg.empty or msg.service:
                    sent = True; break

                # GÖNDERİM AYARLARI (message_thread_id EKLENDİ)
                if msg.media:
                    caption = msg.caption or ""
                    file_path = await current_ub.download_media(msg)
                    if file_path:
                        if msg.photo: await current_ub.send_photo(dst_id, file_path, caption=caption, message_thread_id=dst_topic_id)
                        elif msg.video: await current_ub.send_video(dst_id, file_path, caption=caption, message_thread_id=dst_topic_id)
                        elif msg.document: await current_ub.send_document(dst_id, file_path, caption=caption, message_thread_id=dst_topic_id)
                        elif msg.audio: await current_ub.send_audio(dst_id, file_path, caption=caption, message_thread_id=dst_topic_id)
                        elif msg.voice: await current_ub.send_voice(dst_id, file_path, message_thread_id=dst_topic_id)
                        os.remove(file_path)
                        sent = True
                elif msg.text:
                    await current_ub.send_message(dst_id, msg.text, message_thread_id=dst_topic_id)
                    sent = True
                
                # GÜVENLİK BEKLEMESİ
                await asyncio.sleep(SAFETY_DELAY) 

            except (FloodWait, PeerFlood, UserRestricted) as e:
                wait_sec = e.value if isinstance(e, FloodWait) else 120
                print(f"⚠️ Hız Limiti! Bot {bot_names[bot_index]} dinleniyor ({wait_sec}s).")
                bot_index = (bot_index + 1) % len(active_bots)
                retry += 1
                await asyncio.sleep(5) 
                
            except Exception as e:
                print(f"Hata: {e}")
                bot_index = (bot_index + 1) % len(active_bots)
                retry += 1
                await asyncio.sleep(2)

        if sent:
            processed_count += 1
            save_topic_progress(src_id, src_topic_id, current_msg_id)
            if processed_count % 5 == 0:
                try:
                    bar = get_progress_bar(processed_count, total_todo)
                    text = (f"🎯 **TOPIC SNIPER**\n{bar}\n✅ {processed_count} / {total_todo}\n🤖 Bot: {bot_names[bot_index]}")
                    await status_msg.edit(text)
                except: pass

    await status_msg.edit(f"🏁 **KONU TRANSFERİ BİTTİ!**\n{processed_count} içerik hedefe yerleştirildi.")
    if os.path.exists(f"log_{src_id}_{src_topic_id}.txt"): os.remove(f"log_{src_id}_{src_topic_id}.txt")
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())



















