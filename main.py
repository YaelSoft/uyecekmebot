import asyncio
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, UserPrivacyRestricted, UserAlreadyParticipant, UserNotParticipant, UsernameInvalid, PeerIdInvalid, ChatAdminRequired
import threading
from flask import Flask

# --- AYARLAR ---
API_ID = 37107052
API_HASH = "afc7a787cbde453b8fc7134383658b30"
BOT_TOKEN = "BURAYA_BOT_FATHER_TOKENINI_YAZ"
SESSION_STRING = "BURAYA_SESSION_STRING_YAZ"
ADMIN_ID = 8102629232 

# --- FLASK (Sırf Render Kapanmasın Diye) ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Sistem Ayakta."
def run_flask(): app_web.run(host='0.0.0.0', port=5000)

# --- BOTLARI BAŞLAT ---
bot = Client("Manager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
worker = Client("Worker", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, in_memory=True)

# --- START KOMUTU ---
@bot.on_message(filters.command("start"))
async def start(c, m):
    await m.reply("⚡ **Son Deneme Modu**\nDirekt komutu ver: `/uyecek @kaynak @hedef`")

# --- ÜYE ÇEKME KOMUTU ---
@bot.on_message(filters.command("uyecek"))
async def scrape(client, message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        args = message.text.split()
        source = args[1].replace("@", "").replace("https://t.me/", "")
        target = args[2].replace("@", "").replace("https://t.me/", "")

        status_msg = await message.reply(f"🔨 **{source}** grubuna Balyoz ile giriliyor...")

        # 1. ADIM: İŞÇİ HESAP GRUBA GİRSİN
        try:
            await worker.join_chat(source)
            await status_msg.edit(f"✅ **{source}** grubuna başarıyla girdim!")
        except UserAlreadyParticipant:
            await status_msg.edit(f"ℹ️ Zaten **{source}** grubundayım, devam ediyorum...")
        except Exception as e:
            await status_msg.edit(f"❌ **HATA:** Kaynak gruba giremedim. Bu fake hesap banlı olabilir veya grup kapalı. Hata: {e}")
            return

        # 2. ADIM: LİSTEYİ AL
        await status_msg.edit("📋 Liste çekiliyor (Limit yok, ne varsa alacağım)...")
        members = []
        
        try:
            # Agresif Tarama
            async for m in worker.get_chat_members(source):
                if m.user and not m.user.is_bot and not m.user.is_deleted:
                    members.append(m.user.id)
        except ChatAdminRequired:
            await status_msg.edit(f"⛔ **GİZLİ ÜYE SORUNU!**\nKnk sorun kodda değil. **{source}** grubu 'Üyeleri Gizle' ayarını açmış. Admin olmayan kimse listeyi göremez.")
            return
        except Exception as e:
            await status_msg.edit(f"❌ Liste çekilirken patladı: {e}")
            return

        if len(members) == 0:
            await status_msg.edit("❌ **LİSTE BOŞ!** Telegram bu hesabın üyeleri görmesini engelliyor (Shadowban) veya grupta kimse yok.")
            return

        # 3. ADIM: EKLEME
        await status_msg.edit(f"😈 **{len(members)}** kişi bulundu. **{target}** grubuna basıyorum...")

        count = 0
        for uid in members:
            try:
                await worker.add_chat_members(target, uid)
                count += 1
                await asyncio.sleep(0.5) # Çok az bekleme
                
                # Her 20 kişide bir bilgi ver ki dondu sanma
                if count % 20 == 0:
                    await status_msg.edit(f"🔥 {count} kişi eklendi... Devam ediyorum.")

            except FloodWait as e:
                await status_msg.edit(f"⏳ **Telegram Durdurdu (FloodWait):** {e.value} saniye bekleyip devam edeceğim.")
                await asyncio.sleep(e.value)
            except UserPrivacyRestricted:
                continue
            except UserAlreadyParticipant:
                continue
            except Exception:
                continue

        await status_msg.edit(f"🏁 **İŞLEM BİTTİ!**\nToplam {count} sağlam üye eklendi.")

    except Exception as e:
        await message.reply(f"💥 Genel Hata: {e}")

# --- BAŞLATMA ---
async def main():
    threading.Thread(target=run_flask).start()
    await bot.start()
    await worker.start()
    await idle()
    await bot.stop()
    await worker.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
