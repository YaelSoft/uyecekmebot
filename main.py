import telebot
import sqlite3
import time
import threading
import random
import string
from flask import Flask

# --- AYARLAR ---
BOT_TOKEN = "7960144659:AAHp07olQd3eMD_36rNLUnZV3Dqs91Xk02w"
ADMIN_ID = 8102629232 # Kendi ID'n (Mutlaka sayı olarak gir)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- VERİTABANI ---
DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    # Kullanıcılar Tablosu: ID, Rol (admin/vip/user), Kredi (Hak)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'user',
            credits INTEGER DEFAULT 0
        )
    """)
    # Deneme Kodları Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            credits INTEGER
        )
    """)
    conn.commit()
    conn.close()

# Veritabanı Yardımcıları
def get_user(user_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id):
    if not get_user(user_id):
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        role = 'admin' if user_id == ADMIN_ID else 'user'
        cursor.execute("INSERT INTO users (user_id, role, credits) VALUES (?, ?, 0)", (user_id, role))
        conn.commit()
        conn.close()

def update_role(user_id, role):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    conn.commit()
    conn.close()

def add_credits(user_id, amount):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def deduct_credit(user_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- YARDIMCI FONKSİYONLAR ---
def generate_random_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def check_permission(user_id):
    """
    Dönüş: (İzin Var mı?, Mesaj, Tip)
    Tip: 'unlimited' (Admin/VIP) veya 'credit' (Normal)
    """
    user = get_user(user_id)
    if not user:
        register_user(user_id)
        return False, "⚠️ Sisteme kayıtlı değilsin. /start yaz.", None
    
    role = user[1]
    credits = user[2]

    if user_id == ADMIN_ID or role == 'admin':
        return True, "Admin", 'unlimited'
    elif role == 'vip':
        return True, "VIP", 'unlimited'
    elif credits > 0:
        return True, "User", 'credit'
    else:
        return False, "⛔ Hakkınız kalmadı! Admin'den kod isteyin.", None

# --- KOMUTLAR (ADMIN) ---

@bot.message_handler(commands=['vipekle'])
def vip_add(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        register_user(target_id) # Yoksa oluştur
        update_role(target_id, 'vip')
        bot.reply_to(message, f"✅ {target_id} ID'li kullanıcı artık **VIP**!")
    except:
        bot.reply_to(message, "Hata! Kullanım: `/vipekle 12345678`")

@bot.message_handler(commands=['vipsil'])
def vip_remove(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        update_role(target_id, 'user')
        bot.reply_to(message, f"❌ {target_id} ID'li kullanıcının VIP yetkisi alındı.")
    except:
        bot.reply_to(message, "Hata! Kullanım: `/vipsil 12345678`")

@bot.message_handler(commands=['viplist'])
def vip_list(message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE role = 'vip'")
    vips = cursor.fetchall()
    conn.close()
    
    msg = "💎 **VIP LİSTESİ** 💎\n\n"
    for vip in vips:
        msg += f"👤 `{vip[0]}`\n"
    bot.reply_to(message, msg if vips else "Listede VIP yok.")

@bot.message_handler(commands=['denemekod'])
def create_code(message):
    if message.from_user.id != ADMIN_ID: return
    code = generate_random_code()
    rights = 5 # Varsayılan hak sayısı
    
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO codes (code, credits) VALUES (?, ?)", (code, rights))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"🎟️ **Yeni Kod Oluşturuldu!**\n\nKod: `{code}`\nHak Sayısı: {rights}\n\nKullanıcı bu kodu `/kodkullan {code}` yazarak kullanabilir.")

# --- KOMUTLAR (GENEL) ---

@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.from_user.id)
    bot.reply_to(message, "👋 Hoş geldin! ID'niz kaydedildi.\n\nEğer kodun varsa `/kodkullan KOD` yazarak 5 hak kazanabilirsin.")

@bot.message_handler(commands=['kodkullan'])
def redeem(message):
    user_id = message.from_user.id
    try:
        code_input = message.text.split()[1]
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM codes WHERE code = ?", (code_input,))
        result = cursor.fetchone()
        
        if result:
            amount = result[0]
            add_credits(user_id, amount)
            cursor.execute("DELETE FROM codes WHERE code = ?", (code_input,))
            conn.commit()
            bot.reply_to(message, f"✅ Tebrikler! Hesabınıza **{amount}** transfer hakkı tanımlandı.")
        else:
            bot.reply_to(message, "❌ Geçersiz veya kullanılmış kod.")
        conn.close()
    except:
        bot.reply_to(message, "Lütfen kodu yazın. Örn: `/kodkullan A1B2C3D4`")

@bot.message_handler(commands=['idbul'])
def get_id_info(message):
    # Kullanıcılara ID'nin ne olduğunu öğretmek için
    bot.reply_to(message, f"🆔 Sizin ID'niz: `{message.chat.id}`\n\nTransfer yapacağınız grubun ID'sini bulmak için o gruba 'Rose' botunu ekleyip /id yazabilirsiniz.\n\n⚠️ **UYARI:** Linkler (`https://t.me/...`) transfer komutunda çalışmaz! Mutlaka `-100` ile başlayan ID kullanmalısınız.")

# --- TRANSFER VE MEDYA İŞLEMLERİ ---

@bot.message_handler(commands=['medyacek'])
def single_media(message):
    user_id = message.from_user.id
    allowed, msg, type_ = check_permission(user_id)
    
    if not allowed:
        bot.reply_to(message, msg)
        return

    try:
        # /medyacek KAYNAK_ID HEDEF_ID MESAJ_ID
        args = message.text.split()
        src = int(args[1])
        dst = int(args[2])
        msg_id = int(args[3])
        
        bot.copy_message(dst, src, msg_id)
        
        if type_ == 'credit':
            deduct_credit(user_id)
            bot.reply_to(message, f"✅ Medya gönderildi. (1 Hak düştü)")
        else:
            bot.reply_to(message, "✅ Medya gönderildi. (VIP/Admin Sınırsız)")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Hata! ID'lerin sayı olduğundan ve botun kanallarda admin olduğundan emin olun.\nHata detayı: {e}")

@bot.message_handler(commands=['transfer'])
def bulk_transfer(message):
    user_id = message.from_user.id
    allowed, msg, type_ = check_permission(user_id)
    
    if not allowed:
        bot.reply_to(message, msg)
        return

    # Argüman Kontrolü
    try:
        args = message.text.split()
        src = int(args[1])
        dst = int(args[2])
        start_msg = int(args[3])
        end_msg = int(args[4]) # Sadece bu kadar mesaj deneyecek
    except ValueError:
        bot.reply_to(message, "❌ **YANLIŞ KOMUT!**\nLink kullanamazsınız. Sadece Sayısal ID geçerlidir.\n\nDoğrusu:\n`/transfer -10012345 -10067890 10 15`\n\nID bulmak için gruba Rose botu ekleyip /id yazın.")
        return
    except IndexError:
        bot.reply_to(message, "❌ Eksik bilgi. Örn: `/transfer KAYNAK HEDEF BAŞLANGIÇ BİTİŞ`")
        return

    # Kredi Kontrolü (Toplu işlemde 1 hak = 1 toplu işlem mi yoksa mesaj başı mı? Burada işlem başı 1 hak düşüyorum)
    if type_ == 'credit':
        deduct_credit(user_id)
        bot.reply_to(message, "🎫 İşlem başladı. (Hesabınızdan 1 hak düşüldü)")
    else:
        bot.reply_to(message, "👑 VIP/Admin işlem başlatılıyor...")

    success = 0
    fail = 0
    status_msg = bot.send_message(message.chat.id, "🚀 Başlıyor...")

    for i in range(start_msg, end_msg + 1):
        try:
            bot.copy_message(dst, src, i)
            success += 1
            time.sleep(1.5) # Flood koruması
        except:
            # Copy başarısızsa Forward dene
            try:
                bot.forward_message(dst, src, i)
                success += 1
                time.sleep(1.5)
            except:
                fail += 1
                time.sleep(1) # Hata alınca bekle
        
        if i % 10 == 0:
            try: 
                bot.edit_message_text(f"📊 İşleniyor: {i}\n✅: {success} ❌: {fail}", message.chat.id, status_msg.message_id)
            except: pass

    bot.send_message(message.chat.id, f"🏁 **Tamamlandı!**\nToplam Başarılı: {success}\nHata: {fail}")

# --- WEB SERVER (RENDER İÇİN) ---
@app.route('/')
def home():
    return "Bot Aktif!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    init_db()
    # 409 Hatası Önleyici Blok
    try:
        bot.delete_webhook()
        time.sleep(1)
    except: pass
    
    while True:
        try:
            print("Bot bağlanıyor...")
            bot.infinity_polling(skip_pending=True, timeout=90)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(5)

if __name__ == "__main__":
    t = threading.Thread(target=run_web)
    t.start()
    run_bot()

