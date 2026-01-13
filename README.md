# Lotareya Telegram Bot

**Sovrin:** iPhone 16 Pro Max  \
**Jami chiptalar:** 300 ta  \
**Chipta narxi:** 50 000 so'm

Bot foydalanuvchilarga karta orqali to'lov qilib, chek yuborish va tasdiqlangach, tasodifiy chipta raqamlarini olish imkonini beradi. Admin paneli to'lovlarni tasdiqlash, kengaytirilgan statistika va ommaviy xabar yuborish imkoniyatlarini taqdim etadi.

## Asosiy imkoniyatlar

- Emoji bilan boyitilgan foydalanuvchi menyusi: chiptalar sotib olish, chiptalarni ko'rish, lotareya haqida ma'lumot.
- Chek yuborilganda admin uchun avtomatik xabar, tasdiqlash/rad etish tugmalari va foydalanuvchi bildirishnomalari.
- Tasdiqlangach, 1-300 oralig'ida bo'sh chiptalardan tasodifiy raqam ajratish.
- Admin panelida to'liq analitika: foydalanuvchilar soni, sotilgan chiptalar, daromad, kutilayotgan to'lovlar va eng faol ishtirokchilar.
- Admin uchun global xabar yuborish (matn, rasm yoki video) va start xabarini matn/rasm/video formatida tahrirlash.
- Majburiy kanal obunasi boshqaruvi: kanallarni qo'shish/o'chirish, xabarni tahrirlash va holatni yoqish/o'chirish.
- Foydalanuvchi telefon raqamini yig'ish va tasdiqlangan to'lovlar bo'yicha Excel hisobotini eksport qilish.

## O'rnatish

1. **Muqitni tayyorlash**

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Konfiguratsiya**

    - `.env.example` faylini `.env` nomiga ko'chiring.
    - Quyidagi qiymatlarni yangilang (kerak bo'lsa):

     ```ini
     BOT_TOKEN=telegram-bot-token
     ADMIN_ID=5425876649
     CARD_NUMBER=9860 1901 0198 2212
       PRIZE_NAME=iPhone 16 Pro Max
     ```

3. **Ishga tushirish**

   ```powershell
   python main.py
   ```

## Foydalanish

- `/start` - foydalanuvchi menyusini ochadi va start xabarini ko'rsatadi.
- `🎟 Chiptani sotib olish` - chipta sonini tanlash, to'lov qilish va chek yuborish jarayoni.
- `📋 Mening chiptalarim` - tasdiqlangan chipta raqamlarini ko'rsatadi.
- `ℹ️ O'yin haqida` - lotareya shartlari.
- Admin uchun `/admin` - panelni ochib, quyidagi tugmalar orqali ishlaydi:
   - `📊 Statistika` - batafsil analitika va eng faol foydalanuvchilar.
   - `🧾 Kutilayotgan to'lovlar` - tasdiqlash kutilayotgan cheklarni ko'rish.
   - `✉️ Xabar yuborish` - barcha bot foydalanuvchilariga xabar jo'natish (bekor qilish tugmasi mavjud).
   - `✏️ Start xabarini tahrirlash` - `/start` xabari uchun matn, rasm yoki video shablonni yangilash.
   - `📡 Kanal boshqaruvi` - majburiy obuna kanallarini qo'shish/o'chirish, holatini yoqish va foydalanuvchi xabarini sozlash.
   - `📥 Excel eksport` - tasdiqlangan to'lovlar va chipta raqamlarini Excel faylida yuklab olish.

## Strukturasi

```text
lottery_bot/
  config.py         # Muqitdan sozlamalarni o'qish
  storage.py        # JSON asosidagi ma'lumotlar ombori
  keyboards.py      # Qayta ishlatiladigan tugmalar
  handlers/
    user.py         # Foydalanuvchi oqimlari
    admin.py        # Admin oqimlari
main.py              # Botni ishga tushirish nuqtasi
```

## Eslatma

- Chiptalar soni, narxi yoki karta raqamini o'zgartirish uchun `.env` faylidan foydalaning.
- `PRIZE_NAME` yordamida sovrin nomini moslashtirishingiz mumkin.
- `✏️ Start xabarini tahrirlash` bo'limida quyidagi o'zgaruvchilardan foydalanish mumkin: `{prize}`, `{total_tickets}`, `{remaining_tickets}`, `{ticket_price}`.
- `📡 Kanal boshqaruvi` orqali majburiy obuna xabarini sozlashda `{channels}` o'zgaruvchisi kanal ro'yxati bilan almashtiriladi.
- `data/store.json` fayli bot ishlash jarayonida avtomatik yaratiladi va yangilanadi. Uni o'chirib yuborsangiz, mavjud chiptalar yana 300 tadan boshlanadi.

## Railway.app da Deploy

1. **GitHub'ga yuklash**

   ```bash
   git add .
   git commit -m "Railway deploy tayyorlash"
   git push origin master
   ```

2. **Railway.app orqali deploy**

   - [Railway.app](https://railway.app) ga kiring va GitHub orqali tizimga kiring.
   - "New Project" → "Deploy from GitHub repo" ni tanlang.
   - `lotareyabot` repositoriyasini tanlang.
   - Deploy avtomatik boshlanadi.

3. **Environment Variables**

   Railway proyektingizda quyidagi muhit o'zgaruvchilarini sozlang:
   - `BOT_TOKEN` - Telegram bot tokeni
   - `ADMIN_ID` - Admin Telegram ID raqami
   - `CARD_NUMBER` - To'lov uchun karta raqami
   - `PRIZE_NAME` - Sovrin nomi (masalan: iPhone 16 Pro Max)
   - `TOTAL_TICKETS` - Jami chiptalar soni (masalan: 300)
   - `TICKET_PRICE` - Chipta narxi (masalan: 50000)

4. **Redeploy**

   Environment o'zgaruvchilarini qo'shgandan so'ng "Deploy" tugmasini bosing.

5. **Logs**

   Botning ishlashini tekshirish uchun "Deployments" → "View Logs" ni ko'ring.

