import os
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- AYARLAR (Direkt Giriş Yapılmış Hali) ---
API_ID = 30647156
API_HASH = "11d0174f807a8974a955520b8c968b4d"

# Senin daha önce verdiğin Session String (Bunu kullandığımız için telefon sormaz)
SESSION_STRING = "BAIr9ZEAs6XG1sZgMbfPRuME_g8c93kmDRKEXh6U_2AXJhLXPeJ0S-4saI1Yzt8dF4peKFnDT-EEiZkIe4GGhSjZill45gStwqAxOk4yMuqiL4yVdir9x7jiDRFWWgKHurPYVA-X1YR-1rUMtXV-5tMaYpZAkpnXwWKfqxmuyGO0ORR1iBX_oNv2iHALR72jFJNEUfiDINiW5VGQsbr7K6tLjjhdO4WoVTt7oiwukoLaKwM3ymIC0OitaUzZGiyfJ_QYfu4kX-AiOizlvLPXI5SuLO3-lGt_2yz9EpJMq3MuDY_FA848K_vjSrvSsTqEixdKHTr1JEx4yTgzaBIrrDE7XNkl6wAAAAH4WvQ0AA"

# StringSession kullanarak başlatıyoruz (Dosya oluşturmaya çalışmaz)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

print("✅ Userbot Oturum Açtı ve Hazır!")
print("Kullanım: .basla <KAYNAK_LINK> <HEDEF_LINK>")

@client.on(events.NewMessage(pattern=r"^\.basla"))
async def restricted_copy(event):
    args = event.message.text.split()
    if len(args) != 3:
        await event.edit("❌ **HATA:** `.basla https://t.me/kaynak https://t.me/hedef` şeklinde yaz.")
        return

    source_url = args[1]
    target_url = args[2]

    await event.edit(f"🚀 **Hazırlanıyor...**\nKaynak: {source_url}\nHedef: {target_url}")

    try:
        # Entityleri çöz (Peer ID Invalid Fix)
        source_entity = await client.get_entity(source_url)
        target_entity = await client.get_entity(target_url)
        
        await event.edit(f"✅ **Kanallar Tanımlandı!**\n📥 Kaynak: `{source_entity.title}`\n📤 Hedef: `{target_entity.title}`\n\n⏳ **İşlem Başlıyor... (Gizli içerik modu aktif)**")
        await asyncio.sleep(2)

    except Exception as e:
        await event.edit(f"❌ **HATA:** Kanallar bulunamadı!\nDetay: `{e}`\n\n*Lütfen linkleri kontrol et ve o kanallara üye olduğundan emin ol.*")
        return

    total = 0
    success = 0
    error = 0
    UPDATE_INTERVAL = 5 

    async for message in client.iter_messages(source_entity):
        total += 1
        
        status_msg = (
            f"🔄 **Kopyalanıyor...**\n"
            f"Sıra: `{total}` | ✅: `{success}` | ❌: `{error}`"
        )
        
        if total % UPDATE_INTERVAL == 0:
            try:
                await event.edit(status_msg)
            except:
                pass

        try:
            # --- BYPASS MANTIĞI ---
            if message.media:
                # İletim kapalıysa indirip yeniden yükle
                file_path = await client.download_media(message, file="temp_media/")
                
                if file_path:
                    await client.send_file(
                        target_entity, 
                        file_path, 
                        caption=message.text or ""
                    )
                    os.remove(file_path)
                    success += 1
                else:
                    pass

            elif message.text:
                await client.send_message(target_entity, message.text)
                success += 1

            await asyncio.sleep(0.5)

        except Exception as e:
            error += 1
            continue

    await event.edit(
        f"🏁 **TAMAMLANDI!**\n\n"
        f"Toplam: `{total}`\n"
        f"✅ Başarılı: `{success}`\n"
        f"❌ Hatalı: `{error}`"
    )

    try:
        os.rmdir("temp_media")
    except:
        pass

client.start()
client.run_until_disconnected()
