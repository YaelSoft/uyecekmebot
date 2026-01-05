import asyncio
import os
import threading
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask

# --- AYARLAR ---
API_ID = 30647156
API_HASH = "11d0174f807a8974a955520b8c968b4d"

# User String (Bypass ve Veri Çekme için)
USER_SESSION = "BAIr9ZEAs6XG1sZgMbfPRuME_g8c93kmDRKEXh6U_2AXJhLXPeJ0S-4saI1Yzt8dF4peKFnDT-EEiZkIe4GGhSjZill45gStwqAxOk4yMuqiL4yVdir9x7jiDRFWWgKHurPYVA-X1YR-1rUMtXV-5tMaYpZAkpnXwWKfqxmuyGO0ORR1iBX_oNv2iHALR72jFJNEUfiDINiW5VGQsbr7K6tLjjhdO4WoVTt7oiwukoLaKwM3ymIC0OitaUzZGiyfJ_QYfu4kX-AiOizlvLPXI5SuLO3-lGt_2yz9EpJMq3MuDY_FA848K_vjSrvSsTqEixdKHTr1JEx4yTgzaBIrrDE7XNkl6wAAAAH4WvQ0AA"

# KENDİ BOT TOKENİNİ YAZ
BOT_TOKEN = "8315294005:AAF0yUM1NRt8bbcO1wXBVuoGWBxfHSzUDv4"

# --- FLASK SERVER (Render Ayakta Kalsın Diye) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Çalışıyor!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- TELEGRAM BOT KISMI ---

# 1. Bot Client (Komutları dinler)
bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# 2. User Client (Veriyi çeker)
user = Client("user_session", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION)

is_busy = False

def get_topic_id_from_link(link):
    """Linkten Topic ID'sini ayıklar"""
    # Link formatı genelde: https://t.me/c/123456789/155
    if "/c/" in link:
        parts = link.split("/")
        if len(parts) > 0 and parts[-1].isdigit():
            return int(parts[-1]) # Sondaki sayı Topic ID'dir
    return None

@bot.on_message(filters.command("copy"))
async def copy_topic(client, message: Message):
    global is_busy
    
    if is_busy:
        await message.reply_text("⚠️ Başka bir işlem sürüyor, bekle.")
        return

    try:
        _, source_link, target_link = message.text.split()
    except:
        await message.reply_text("❌ **Hata:** `/copy KAYNAK_LINK HEDEF_LINK`")
        return

    status_msg = await message.reply_text(f"🔍 **Topic Analiz Ediliyor...**\n`{source_link}`")
    is_busy = True

    try:
        # Linkten Topic ID var mı kontrol et
        topic_id = get_topic_id_from_link(source_link)
        
        # User client ile sohbeti bul
        chat = await user.get_chat(source_link)
        target_chat = await user.get_chat(target_link)
        
        info_text = f"✅ **Bulundu:** `{chat.title}`\n"
        if topic_id:
            info_text += f"📌 **Hedef Topic ID:** `{topic_id}` (Sadece bu başlık kopyalanacak)\n"
        else:
            info_text += "⚠️ **Uyarı:** Topic ID bulunamadı, tüm grup taranabilir!\n"
            
        await status_msg.edit(info_text + "🚀 **İşlem Başlıyor...**")

        total = 0
        success = 0
        
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        # ITERASYON: Eğer topic_id varsa, sadece o thread'e yanıt olanları (reply_to_message_id) filtreleriz.
        # Pyrogram'da Topic içindeki mesajları çekmek için reply_to_message_id parametresi kullanılır.
        
        history_args = {"chat_id": chat.id}
        if topic_id:
            history_args["reply_to_message_id"] = topic_id

        # En eskiden en yeniye doğru gelmesi için reverse=True diyebilirsin ama 
        # Pyrogram iter_history varsayılan olarak yeniden eskiye gider. 
        # Mesaj sırası düzgün olsun diye listeye alıp ters çevireceğiz.
        
        messages = []
        async for msg in user.get_chat_history(**history_args):
            messages.append(msg)
        
        # Listeyi ters çevir (Eskiden Yeniye) - Böylece konu bütünlüğü bozulmaz
        messages.reverse()

        total_msgs = len(messages)
        await status_msg.edit(f"📥 **{total_msgs} Mesaj Tespit Edildi.** Aktarım Başlıyor...")

        for msg in messages:
            total += 1
            
            # İlerleme (Her 5 mesajda bir güncelle)
            if total % 5 == 0:
                try:
                    await status_msg.edit(f"🔄 **Aktarılıyor...**\nSıra: {total}/{total_msgs}")
                except:
                    pass

            try:
                # --- İÇERİK TİPİNE GÖRE İŞLEM ---
                caption = msg.caption or ""
                
                # 1. Metin
                if msg.text:
                    await user.send_message(target_chat.id, msg.text)
                    success += 1
                
                # 2. Medya (Foto/Video/Belge) - İndirip Yükle
                elif msg.media:
                    file_path = await user.download_media(msg, file_name="downloads/")
                    
                    if file_path:
                        if msg.photo:
                            await user.send_photo(target_chat.id, file_path, caption=caption)
                        elif msg.video:
                            await user.send_video(target_chat.id, file_path, caption=caption)
                        elif msg.document:
                            await user.send_document(target_chat.id, file_path, caption=caption)
                        
                        os.remove(file_path)
                        success += 1
                
                await asyncio.sleep(1.5) # FloodWait yememek için bekleme

            except Exception as e:
                print(f"Mesaj atlama hatası: {e}")
                continue

        await status_msg.edit(f"🏁 **BİTTİ!**\n\n✅ Başarılı: {success}/{total_msgs}")

    except Exception as e:
        await status_msg.edit(f"❌ **Kritik Hata:** {e}")
    
    finally:
        is_busy = False
        # Temizlik
        if os.path.exists("downloads"):
            for f in os.listdir("downloads"):
                os.remove(os.path.join("downloads", f))

# --- BAŞLATMA ---
if __name__ == "__main__":
    # Flask'ı ayrı thread'de başlat
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    print("Bot başlatılıyor...")
    
    # User ve Bot'u başlat
    user.start()
    bot.run() # bot.run() pyrogram'da idle tutar
