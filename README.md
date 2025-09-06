# 🤖 Engineer Personal Messenger Bot (Telegram)

A **privacy-first, admin-routed Telegram messenger bot**. Messages are delivered to the admin, who can reply anonymously via the bot. Includes admin tools (ban/unban, who, stats) and personal utilities (notes, tasks, reminders, export, file vault).

---

# 🤖 ربات پیام‌رسان شخصی مهندسی (تلگرام)

یک **بات پیام‌رسان خصوصی و امن** برای مدیریت گفتگوهای شخصی در تلگرام. پیام‌ها به صورت ناشناس بین کاربر و ادمین ردوبدل می‌شوند و امکانات مدیریتی و ابزارهای شخصی در آن تعبیه شده است.

---

## ✨ Features | ویژگی‌ها

* 🔒 Private routing | مسیریابی خصوصی: user → bot → admin → bot → user
* 🕵️ Anonymous replies | پاسخ ناشناس: هویت ادمین مخفی می‌ماند
* ⌨️ Admin keyboard | کیبورد مدیریتی برای عملیات سریع (Reply, Ban, Unban, Who, Stats)
* 📋 User registry | رجیستری کاربران با آخرین زمان فعالیت
* 🚫 Moderation | مدیریت کاربران (بن/آن‌بن)
* 🛠 Utilities (admin-only) | ابزارها: یادداشت‌ها، تسک‌ها، یادآورها، جستجو، اکسپورت، فایل‌والت
* 💾 SQLite storage | ذخیره‌سازی ساده و پرتابل با SQLite

---

## 🚀 Quickstart | شروع سریع

```bash
# 1. Setup environment
cp .env.example .env  # set BOT_TOKEN and ADMIN_ID

# 2. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
python -m bot.main
```

---

## ⚙️ Environment Variables | متغیرهای محیطی

* `BOT_TOKEN` → Bot token from @BotFather | توکن از @BotFather
* `ADMIN_ID` → Your Telegram user ID | آیدی عددی ادمین
* `ALLOWED_USER_IDS` → Optional comma-separated IDs | آیدی‌های مجاز (اختیاری)
* `DB_PATH` → SQLite database path (default: `data/bot.db`)

---

## 📲 User Flow | جریان کاربر و ادمین

* **User | کاربر:** sends a message → bot forwards → admin replies anonymously
* **Admin | ادمین:** receives messages with quick-action keyboard

  * Reply directly or enter reply mode
  * Use Quick Replies (prefilled answers)
  * Open profile links / direct chat

---

## 🛡️ Admin Commands | دستورات مدیریتی

* `/ban <user_id> [reason]` → Ban user | بن کاربر
* `/unban <user_id>` → Unban user | آن‌بن کاربر
* `/who <user_id>` → Show user info | نمایش اطلاعات
* `/stats` → Show statistics | آمار
* Notes | یادداشت‌ها: `/note`, `/notes`, `/delnote`
* Tasks | تسک‌ها: `/task`, `/tasks`, `/done`, `/deltask`
* Reminders | یادآورها: `/remind in 10m <text>` | `at YYYY-MM-DD HH:MM <text>`
* Search & Export | جستجو و اکسپورت: `/search <query>`, `/export notes|tasks`

---

## 🗄 Data Model (SQLite) | مدل داده‌ها

* `users` → User info | کاربران
* `bans` → Bans | لیست بن‌ها
* `relays` → Message routing | مسیر پیام‌ها
* `messages` → Messages | پیام‌ها
* `notes` → Notes | یادداشت‌ها
* `tasks` → Tasks | تسک‌ها
* `reminders` → Reminders | یادآورها
* `files` → Files | فایل‌ها

---

## 🔐 Security | امنیت

* `.env` is gitignored | فایل `.env` نباید لو برود
* Rotate leaked tokens immediately | در صورت لو رفتن توکن، سریعاً ریست کنید
* Only admin has access to management | دسترسی مدیریتی فقط برای ادمین

---

## 📦 Deploy | دیپلوی

* **Local | لوکال:** use Quickstart steps
* **Server | سرور:** run with systemd, pm2, docker

```ini
[Service]
WorkingDirectory=/path/to/repo
ExecStart=/path/to/python -m bot.main
```

---

## 📌 Roadmap Ideas | نقشه راه

* 🚧 Anti-spam | آنتی‌اسپم پیشرفته
* 📑 Reply templates | مدیریت قالب‌های پاسخ
* 🔍 FTS5 search | جستجوی پیشرفته
* 🧵 Ticket/thread grouping | گروه‌بندی گفتگوها
* 👥 Multi-admin support | چندادمینی

---

## ✅ GitHub Launch Checklist | چک‌لیست لانچ

* [x] `.env.example` ready | آماده
* [x] `.gitignore` updated | کامل
* [x] README clear | شفاف و کامل
* [ ] Add license if public | افزودن لایسنس

---

📌 Built with ❤️ for secure Telegram communication | ساخته‌شده با ❤️ برای مدیریت امن تلگرام
