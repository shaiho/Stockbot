# Stockbot



בוט טלגרם לניהול תיקי השקעות — מניות, ETF, מזומן (₪/$), P&L, דוח מס, watchlist והתראות.



## דרישות



- Python 3.11+

- Bot Token מ-[@BotFather](https://t.me/BotFather)

- Finnhub API Key (חינם) מ-[finnhub.io](https://finnhub.io)



## התקנה מקומית



```bash

cd Stockbot

python -m venv .venv

.venv\Scripts\activate   # Windows

# source .venv/bin/activate  # Linux

pip install -r requirements.txt

copy .env.example .env     # Windows

# cp .env.example .env     # Linux

# ערוך .env — הוסף TELEGRAM_BOT_TOKEN ו-FINNHUB_API_KEY

```



## הרצה



```bash

python -m src.main

```



## יכולות



- עד **5 תיקים** עם כינוי per משתמש

- onboarding: שפה, מזומן פתיחה, ניירות + מחיר ממוצע

- קנייה/מכירה עם **עמלות** וולידציית מכירה

- סיכום תיק, החזקות, מחיר, P&L (ממומש/לא ממומש)

- **דוח מס שנתי** (25%, למידע בלבד)

- watchlist + צפייה בחדשות

- התראות: מחיר יעד, תזוזה יומית, pre/after market, נפח, חדשות, שווי תיק, יום אדום, milestone

- דוחות יומיים per תיק — **שעות מותאמות אישית** (ברירת מחדל 09:00 / 23:00, שעון ישראל)

- **ייבוא JSON** לתיק (⚙️ הגדרות → 📥 ייבוא JSON)



### פורמט ייבוא JSON



```json

{

  "cash": { "ILS": 100000, "USD": 0 },

  "holdings": [

    { "symbol": "AAPL", "market": "US", "quantity": 10, "avg_cost": 150.5, "date": "15/03/2024" },

    { "symbol": "TEVA", "market": "IL", "quantity": 100, "avg_cost": 5200, "currency": "ILS", "date": "2024-06-01" }

  ]

}

```



## פריסה על VPS (Ubuntu + systemd)



### 1. הכנת השרת



```bash

sudo apt update && sudo apt upgrade -y

sudo apt install -y python3 python3-venv python3-pip git

sudo useradd -m -s /bin/bash stockbot

sudo mkdir -p /opt/stockbot

sudo chown stockbot:stockbot /opt/stockbot

```



### 2. העתקת הקוד



```bash

sudo -u stockbot git clone <YOUR_REPO_URL> /opt/stockbot

# או: scp/rsync מהמחשב המקומי

cd /opt/stockbot

sudo -u stockbot python3 -m venv .venv

sudo -u stockbot .venv/bin/pip install -r requirements.txt

sudo -u stockbot cp .env.example .env

sudo -u stockbot nano .env   # TELEGRAM_BOT_TOKEN, FINNHUB_API_KEY

```



### 3. systemd



```bash

sudo cp deploy/stockbot.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable stockbot

sudo systemctl start stockbot

sudo systemctl status stockbot

```



### 4. לוגים ותחזוקה



```bash

journalctl -u stockbot -f          # לוגים חיים

sudo systemctl restart stockbot    # אחרי עדכון קוד

```



ה-DB נשמר ב-`data/stockbot.db` (ניתן לשנות ב-`DATABASE_PATH` ב-`.env`).

### Supabase (PostgreSQL)

לפרודקשן מומלץ Supabase במקום SQLite מקומי.

1. ב-Supabase: **Project Settings → Database → Connection string**
2. **Windows / רשת IPv4:** אל תשתמש ב-Direct (`db.[project-ref].supabase.co`) — הוא IPv6 בלבד.
   בחר **Session pooler** (גם הוא פורט **5432**, אבל עובד ב-IPv4):
3. הוסף ל-`.env`:

```env
DATABASE_URL=postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
```

> **Direct vs Session:** שני החיבורים על פורט 5432, אבל ה-host שונה. Direct = IPv6 בלבד. Session pooler = IPv4 + IPv6.

> **DNS:** אם מקבלים `getaddrinfo failed`, שנה ב-Windows את ה-DNS ל-`8.8.8.8` / `1.1.1.1`.

3. העבר נתונים קיימים מ-SQLite (פעם אחת):

```bash
python -m scripts.migrate_sqlite_to_postgres
```

4. הפעל מחדש את הבוט. כש-`DATABASE_URL` מוגדר, הבוט משתמש ב-Postgres ומתעלם מ-`DATABASE_PATH`.

**הערה:** אם אין לך עדיין נתונים ב-SQLite, אפשר לדלג על שלב 3 — הבוט ייצור את הטבלאות אוטומטית בהפעלה הראשונה.




## אתר ניהול (PHP)

אתר ב-`web/` שעובד ישירות על אותו DB של הבוט (Supabase Postgres, `DATABASE_URL`), בלי שכבת סנכרון — כל שינוי באתר נראה מיד בבוט ולהיפך.
מנהל: תיקים והגדרות עמלות, עסקאות (קנייה/מכירה/דיבידנד), מזומן, watchlist, התראות והגדרות משתמש; מציג החזקות, רווח/הפסד ומחירים חיים.

דרישות: PHP 8.1+ עם `pdo_pgsql`, `curl`, `mbstring`.

```bash
sudo apt install -y php-pgsql php-curl php-mbstring   # + שרת web: ראו "פריסה" למטה (Apache / nginx)
```

ב-`.env` (אותו קובץ של הבוט) מוסיפים:

```env
WEB_PASSWORD=סיסמה-חזקה
WEB_TELEGRAM_ID=123456789   # ה-Telegram ID שהחשבונות שלו מנוהלים באתר
```

- אפשר גם hash במקום סיסמה גלויה: `php -r "echo password_hash('הסיסמה', PASSWORD_DEFAULT);"` ולהדביק ב-`WEB_PASSWORD`.
- `FINNHUB_API_KEY` (אופציונלי) משמש גם את האתר למחירי US; בלעדיו Yahoo בלבד. מחירים נשמרים ב-cache של 5 דקות (`PRICE_CACHE_SECONDS`).
- `WEB_DEBUG=1` מציג את הודעת השגיאה המלאה בדפדפן (לא להשאיר בפרודקשן).

הרצה מקומית לבדיקה:

```bash
php -S 127.0.0.1:8080 -t web/public
```

פריסה על ה-VPS (ליד הבוט) — הכנה משותפת:

```bash
sudo mkdir -p /opt/stockbot/web/cache
sudo chown -R www-data:www-data /opt/stockbot/web/cache
sudo chmod 640 /opt/stockbot/.env && sudo chgrp www-data /opt/stockbot/.env
```

**Apache, בלי HTTPS** (`deploy/apache-stockbot-web.conf` מאזין רק ל-`127.0.0.1:8080`; הגישה דרך מנהרת SSH, כך שהסיסמה לא עוברת גלויה ברשת):

```bash
sudo apt install -y apache2 libapache2-mod-php php-pgsql php-curl php-mbstring
sudo cp deploy/apache-stockbot-web.conf /etc/apache2/sites-available/stockbot-web.conf
sudo a2ensite stockbot-web
sudo apache2ctl configtest && sudo systemctl reload apache2
```

מהמחשב שלך:

```bash
ssh -L 8080:127.0.0.1:8080 user@VPS_IP
# ואז בדפדפן: http://localhost:8080
```

חשיפה ציבורית ב-HTTP (לא מומלץ): בקובץ ה-conf מחליפים `127.0.0.1` ב-`*` ומפעילים `Require ip <ה-IP שלך>`. ה-IP allowlist מגביל מי יכול לנסות להתחבר, אבל הסיסמה עדיין עוברת לא מוצפנת.

**nginx + HTTPS** (אם יתאפשר): `deploy/nginx-stockbot-web.conf` ואז `sudo certbot --nginx -d stockbot.example.com`.

הערות:
- ה-document root הוא `web/public` בלבד; `.env` וקוד המקור לא נגישים מהרשת.
- האתר לא יוצר טבלאות — הן נוצרות על ידי הבוט בהפעלה הראשונה. האתר תומך רק ב-Postgres.
- תאריכי עסקאות נשמרים כרגע אמיתי (UTC) ומוצגים לפי `TIMEZONE`; עסקה עם תאריך בלבד נשמרת ב-12:00 שעון ישראל, כמו בבוט.

## מבנה



```

src/

  main.py           # entry point

  db/               # SQLite / Supabase Postgres

  bot/handlers/     # Telegram handlers

  market/           # Finnhub + yfinance

  portfolio/        # P&L, formatters, import

  scheduler/        # דוחות + alerts
web/                # אתר ניהול PHP (public/ = document root)

```



## הערות



- מחירי TASE via yfinance (`.TA`) — שעות רגילות

- pre/post market — US via Finnhub / yfinance

- דוח מס — **לא ייעוץ מס**

