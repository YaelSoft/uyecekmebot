from telethon import TelegramClient, events, types
import asyncio
import sys

# --- AYARLAR ---
# Buraya kendi bilgilerini gir (Önceki konuşmalardan hatırla: API ID ve Hash'in sende var)
API_ID = 30647156  
API_HASH = "11d0174f807a8974a955520b8c968b4d"
SESSION_NAME = 'user' 

# Kaynak ve Hedef (Link veya ID olarak string girebilirsin)
# Örnek: "https://t.me/kaynakkanal" veya "https://t.me/+AbCdEfGh..."
SOURCE_LINK = input("Kaynak Kanal/Grup Linki veya ID'si: ")
TARGET_LINK = input("Hedef Grup Linki veya ID'si: ")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def main():
    print("\n--- Userbot Başlatılıyor... ---")
    await client.start()
    
    # 1. ADIM: HEDEF VE KAYNAĞI TANIMLAMA (PEER ID FIX)
    try:
        print(f"⏳ Kaynak çözümleniyor: {SOURCE_LINK}")
        source_entity = await client.get_entity(SOURCE_LINK)
        print(f"✅ Kaynak bulundu: {source_entity.title}")

        print(f"⏳ Hedef çözümleniyor: {TARGET_LINK}")
        target_entity = await client.get_entity(TARGET_LINK)
        print(f"✅ Hedef bulundu: {target_entity.title}")
    except Exception as e:
        print(f"\n❌ HATA: Kanal/Grup bulunamadı! Linkleri kontrol et.")
        print(f"Hata detayı: {e}")
        print("İPUCU: Hedef gruba zaten üye olduğundan emin ol.")
        return

    # İstatistik Sayaçları
    total_count = 0
    success_count = 0
    error_count = 0
    skipped_count = 0

    print("\n--- Kopyalama İşlemi Başlıyor ---\n")

    # Mesajları tersten (eskiden yeniye) almak için 'reverse=True' kullanabilirsin.
    # Şu anki ayar: En son mesajdan geriye doğru gider.
    async for message in client.iter_messages(source_entity, limit=None):
        total_count += 1
        
        # İlerleme durumunu ekrana bas (Her mesajda bir satır yazar)
        sys.stdout.write(f"\rİşlenen Mesaj: {total_count} | Başarılı: {success_count} | Hatalı: {error_count}")
        sys.stdout.flush()

        try:
            if message.text or message.media:
                # Mesajı hedefe gönder
                await client.send_message(target_entity, message)
                success_count += 1
                
                # Spam koruması için çok kısa bir bekleme (isteğe bağlı, kaldırırsan hızlanır ama risk artar)
                await asyncio.sleep(0.5) 
            else:
                # Boş veya servis mesajıysa (örn: gruba biri katıldı mesajı)
                skipped_count += 1

        except Exception as e:
            error_count += 1
            # Hata detayını görmek istersen alt satırı aç:
            # print(f"\n[!] Mesaj {message.id} kopyalanamadı: {e}")
            continue

    print("\n\n" + "="*30)
    print("      İŞLEM TAMAMLANDI")
    print("="*30)
    print(f"Toplam Taranan : {total_count}")
    print(f"✅ Başarılı     : {success_count}")
    print(f"❌ Hatalı       : {error_count}")
    print(f"⏭️ Atlanan      : {skipped_count}")
    print("="*30)

with client:
    client.loop.run_until_complete(main())
