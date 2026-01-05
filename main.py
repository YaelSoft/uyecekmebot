from telethon import TelegramClient, events
import asyncio

# --- AYARLAR (Senin Bilgilerin) ---
API_ID = 30647156
API_HASH = "11d0174f807a8974a955520b8c968b4d"
SESSION_NAME = 'user'

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

print("Userbot Aktif! Telegram'da Kayıtlı Mesajlar'a veya herhangi bir yere komutu yazabilirsin.")
print("Komut formatı: .basla <KAYNAK_LINK> <HEDEF_LINK>")

@client.on(events.NewMessage(pattern=r"^\.basla"))
async def kopyalama_baslat(event):
    # Komuttan linkleri ayıkla
    args = event.message.text.split()
    if len(args) != 3:
        await event.edit("❌ **HATA:** Eksik bilgi.\nKullanım: `.basla https://t.me/kaynak https://t.me/hedef`")
        return

    source_url = args[1]
    target_url = args[2]

    await event.edit(f"🔄 **Bağlantılar Çözümleniyor...**\nKaynak: {source_url}\nHedef: {target_url}")

    try:
        # 1. ADIM: Entityleri zorla tanımla (PEER_ID_INVALID Çözümü)
        # Link bir mesaj linki olsa bile (t.me/c/xxx/123) get_entity kanalı bulur.
        source_entity = await client.get_entity(source_url)
        target_entity = await client.get_entity(target_url)
        
        await event.edit(f"✅ **Hedefler Bulundu!**\n📥 Kaynak: {source_entity.title}\n📤 Hedef: {target_entity.title}\n\n🚀 **İşlem Başlıyor...**")
        await asyncio.sleep(2) # Okuman için bekleme

    except Exception as e:
        await event.edit(f"❌ **HATA: Kanal/Grup Bulunamadı!**\n\nDetay: `{str(e)}`\n\n⚠️ *Lütfen linklerin doğru olduğundan ve hedef gruba üye olduğundan emin ol.*")
        return

    # İstatistikler
    total = 0
    success = 0
    error = 0
    
    # İlerleme çubuğu güncelleme sıklığı (Her 20 mesajda bir editler, yoksa Telegram engel atar)
    UPDATE_INTERVAL = 20 

    # Mesajları döngüye al (Eskiden yeniye veya tersten alabilirsin, şu an en son mesajdan geriye gider)
    async for message in client.iter_messages(source_entity):
        total += 1
        
        try:
            if message.text or message.media:
                await client.send_message(target_entity, message)
                success += 1
                # Spam koruması
                await asyncio.sleep(0.5)
            
        except Exception as e:
            error += 1
            # Hata durumunda (FloodWait vs) biraz daha uzun bekle
            await asyncio.sleep(2)

        # Durum Güncellemesi (Her 20 mesajda bir)
        if total % UPDATE_INTERVAL == 0:
            status_text = (
                f"🔄 **Kopyalama Sürüyor...**\n\n"
                f"📊 **Toplam İşlenen:** `{total}`\n"
                f"✅ **Başarılı:** `{success}`\n"
                f"❌ **Hatalı:** `{error}`"
            )
            try:
                await event.edit(status_text)
            except:
                pass # Edit hatası verirse (hız sınırı) işlemi durdurma, devam et.

    # Bitiş Raporu
    final_text = (
        f"🏁 **İŞLEM TAMAMLANDI!**\n\n"
        f"📊 **Toplam Taranan:** `{total}`\n"
        f"✅ **Kopyalanan:** `{success}`\n"
        f"❌ **Başarısız:** `{error}`"
    )
    await event.edit(final_text)

client.start()
client.run_until_disconnected()
