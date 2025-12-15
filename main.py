import os
import asyncio
import threading
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError
from flask import Flask

# --- 1. RENDER İÇİN WEB SUNUCUSU (Uyumaması İçin) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Telethon Userbot Aktif!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- 2. AYARLAR (Render Environment Variables'dan Alır) ---
# Eğer Render'a girmezsen varsayılan değerler hata verir.
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# Admin ID (Virgülle ayırarak birden fazla girebilirsin)
ALLOWED_USERS = list(map(int, os.environ.get("ALLOWED_USERS", "").split(","))) if os.environ.get("ALLOWED_USERS") else []

# --- 3. CLIENT BAŞLATMA ---
if not SESSION_STRING:
    print("HATA: SESSION_STRING bulunamadı! Render ayarlarına ekle.")
    exit(1)

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- 4. YARDIMCI FONKSİYONLAR ---
def is_authorized(user_id):
    """Kullanıcı yetkisi kontrolü"""
    if not ALLOWED_USERS: return True # Liste boşsa herkese açık (Riskli olabilir)
    return user_id in ALLOWED_USERS

async def get_message_from_link(link):
    """Mesaj linkinden mesaj objesini alır (Private/Public fark etmez)"""
    try:
        link = link.strip().split('?')[0] # Linki temizle
        parts = link.rstrip('/').split('/')
        message_id = int(parts[-1])

        if 't.me/c/' in link:
            # Özel kanal/grup: https://t.me/c/1234567890/123
            # Telethon'da private ID'ler -100 ile başlamaz, direkt ID verilir ama 
            # PeerChannel oluştururken -100 gerekebilir.
            # En garantisi entity'yi çözümlemektir.
            channel_id = int(parts[-2])
            # Telethon'da private kanallar için -100 ekleyip get_entity yapmak genelde çalışır
            entity = await client.get_entity(int(f'-100{channel_id}'))
        else:
            # Public kanal: https://t.me/kanaladi/123
            username = parts[-2]
            entity = await client.get_entity(username)

        return await client.get_messages(entity, ids=message_id)

    except FloodWaitError as e:
        print(f"⏳ FloodWait: {e.seconds} saniye bekleniyor...")
        await asyncio.sleep(e.seconds + 2)
        return await get_message_from_link(link)
    except Exception as e:
        print(f"Mesaj alma hatası: {e}")
        return None

# --- 5. KOMUTLAR ---

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    if not is_authorized(event.sender_id): return
    await event.respond(
        "🤖 **Telethon Userbot Aktif!**\n\n"
        "⚡ **İletim Kapalı İçerik Çekici**\n"
        "`/copy [link]` - Metni kopyalar\n"
        "`/getmedia [link]` - Medyayı indirip atar\n"
        "`/transfer [kaynak] [hedef] [adet]` - Toplu aktarım\n"
    )

@client.on(events.NewMessage(pattern='/copy'))
async def copy_text(event):
    if not is_authorized(event.sender_id): return
    try:
        link = event.message.text.split(' ', 1)[1]
        msg = await get_message_from_link(link)
        if msg and msg.text:
            await event.respond(f"📄 **İçerik:**\n\n{msg.text}")
        else:
            await event.respond("❌ Metin bulunamadı.")
    except: await event.respond("Kullanım: /copy link")

@client.on(events.NewMessage(pattern='/getmedia'))
async def get_media(event):
    if not is_authorized(event.sender_id): return
    try:
        link = event.message.text.split(' ', 1)[1]
        status = await event.respond("⏳ **İndiriliyor...**")
        
        msg = await get_message_from_link(link)
        
        if not msg or not msg.media:
            await status.edit("❌ Medya bulunamadı veya erişilemedi.")
            return

        # Render diskine indir
        file_path = await client.download_media(msg.media)
        
        await status.edit("⬆️ **Yükleniyor...**")
        
        # Gönder
        await client.send_file(event.chat_id, file_path, caption=msg.text or "")
        
        # Sil (Disk dolmasın)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        await status.delete()

    except Exception as e:
        await event.respond(f"❌ Hata: {str(e)}")

@client.on(events.NewMessage(pattern='/transfer'))
async def transfer(event):
    if not is_authorized(event.sender_id): return
    try:
        args = event.message.text.split()
        if len(args) < 4:
            await event.respond("Kullanım: `/transfer [kaynak] [hedef] [adet]`")
            return

        src = args[1]
        dst = args[2]
        limit = int(args[3])
        
        status = await event.respond(f"🚀 **Transfer Başlıyor...**\nLimit: {limit}")
        
        # Hedef entity
        if 't.me/' in dst:
            dst_entity = await client.get_entity(dst.split('/')[-1])
        else:
            dst_entity = await client.get_entity(dst)

        # Kaynak entity (get_message_from_link mantığına benzer, tüm mesajları çekeceğiz)
        if 't.me/c/' in src:
            cid = int(src.split('/')[-2])
            src_entity = await client.get_entity(int(f'-100{cid}'))
        else:
            src_entity = await client.get_entity(src.split('/')[-1])

        count = 0
        async for msg in client.iter_messages(src_entity, limit=limit):
            if msg.media:
                try:
                    path = await client.download_media(msg.media)
                    await client.send_file(dst_entity, path, caption=msg.text)
                    if os.path.exists(path): os.remove(path)
                    count += 1
                    if count % 5 == 0: await status.edit(f"✅ {count} adet aktarıldı...")
                except Exception as e:
                    print(f"Hata: {e}")
                    continue
        
        await status.edit(f"🏁 **Tamamlandı!** Toplam {count} medya aktarıldı.")

    except Exception as e:
        await event.respond(f"❌ Hata: {e}")

# --- 6. BAŞLATMA ---
def main():
    # Flask'ı ayrı thread'de başlat
    threading.Thread(target=run_web).start()
    
    print("Userbot Başlatılıyor...")
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':
    main()
