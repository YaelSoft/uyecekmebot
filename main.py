import os
import asyncio
from telethon import TelegramClient, events

# --- SENİN BİLGİLERİN ---
API_ID = 30647156
API_HASH = "11d0174f807a8974a955520b8c968b4d"
SESSION_NAME = 'user'

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

print("✅ Userbot Hazır!")
print("Kullanım: .basla <KAYNAK_LINK> <HEDEF_LINK>")
print("NOT: İçerik korumalı olduğu için medyaları önce indirip sonra yükler. İnternet hızına göre zaman alabilir.")

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
        
        await event.edit(f"✅ **Kanallar Tanımlandı!**\n\n📥 Kaynak: `{source_entity.title}`\n📤 Hedef: `{target_entity.title}`\n\n⏳ **İşlem Başlıyor... (Gizli içerik modu aktif)**")
        await asyncio.sleep(2)

    except Exception as e:
        await event.edit(f"❌ **HATA:** Kanallar bulunamadı!\nDetay: `{e}`\n\n*Lütfen linkleri kontrol et ve o kanallara üye olduğundan emin ol.*")
        return

    total = 0
    success = 0
    error = 0
    
    # İlerlemeyi ne sıklıkla güncellesin (Mesaj başı)
    UPDATE_INTERVAL = 5 

    # Mesajları tara (Eskiden yeniye doğru istiyorsan reverse=True ekle: iter_messages(..., reverse=True))
    async for message in client.iter_messages(source_entity):
        total += 1
        
        # Durum mesajını hazırla
        status_msg = (
            f"🔄 **Kopyalanıyor...**\n"
            f"Sıra: `{total}` | ✅: `{success}` | ❌: `{error}`\n"
            f"📂 Son İşlem: Mesaj ID `{message.id}` işleniyor..."
        )
        
        if total % UPDATE_INTERVAL == 0:
            try:
                await event.edit(status_msg)
            except:
                pass

        try:
            # --- BYPASS MANTIĞI BURADA ---
            # Eğer mesajda medya varsa (Foto/Video/Belge)
            if message.media:
                # İletim kapalı olduğu için 'download_media' yapmak zorundayız
                file_path = await client.download_media(message, file="temp_media/")
                
                if file_path:
                    # Medyayı hedefe yükle
                    await client.send_file(
                        target_entity, 
                        file_path, 
                        caption=message.text or ""
                    )
                    
                    # İndirilen dosyayı sil (Diski doldurmasın)
                    os.remove(file_path)
                    success += 1
                else:
                    # Medya var ama indirilemedi (Bazen çıkartma vs olabilir)
                    pass

            # Sadece yazı ise
            elif message.text:
                await client.send_message(target_entity, message.text)
                success += 1

            # Spam koruması (Upload yaparken zaten zaman geçtiği için kısa tuttum)
            await asyncio.sleep(0.5)

        except Exception as e:
            error += 1
            # Hata durumunda devam et
            continue

    # Bitiş
    await event.edit(
        f"🏁 **TAMAMLANDI!**\n\n"
        f"Toplam: `{total}`\n"
        f"✅ Başarılı: `{success}`\n"
        f"❌ Hatalı: `{error}`"
    )

    # Varsa temp klasörünü temizle (boşsa siler)
    try:
        os.rmdir("temp_media")
    except:
        pass

client.start()
client.run_until_disconnected()
