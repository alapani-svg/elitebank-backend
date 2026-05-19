# Elite Bank  Fullstack Digital Banking App

Institut Universitaire Saint Jean  Saint Jean Ingénieur
End-of-Semester Project · Fullstack Web Development (Django REST + Angular)
Student:AGOUFACK ALAPANI CORANTIN JUNIOR · Year 2 · 2025–2026
Supervisor: Mr. KINKEU FRANCK DANIEL

A premium digital-banking platform for Cameroon featuring peer-to-peer transfers,
mobile-money deposit/withdrawal (Orange · MTN), utility-bill payments (ENEO, CAMWATER,
CANAL+, CAMTEL), airtime purchases, saved beneficiaries, an in-app notification feed,
and PDF / CSV account statements  all behind JWT authentication, with full English ↔
French i18n.

---

## 🏗 Tech Stack

| Layer    | Technology                                                                |
|----------|---------------------------------------------------------------------------|
| Backend  | Django 4.2 · Django REST Framework · `djangorestframework-simplejwt`      |
| Auth     | JWT with refresh-token blacklisting on logout                             |
| Admin    | Jazzmin (custom theme + icons + ordering)                                 |
| Docs     | drf-spectacular (Swagger UI + ReDoc)                                      |
| PDF      | ReportLab                                                                 |
| Frontend | Angular 21 (standalone components, signals-friendly)                      |
| Forms    | Reactive Forms with client-side validators                                |
| Styling  | SCSS + Material Symbols Outlined (offline) + Manrope                      |
| i18n     | Custom lightweight pipe-based service (en + fr) synced with user profile  |
| Deploy   | Backend → Render · Frontend → Vercel                                      |

---

## ✨ Features

### 👤 Account & Auth
- Email + password registration / login (JWT access + refresh)
- Profile: edit name & phone, change password, 2FA toggle, language switch (en/fr)
- Avatar upload (10 MB max, image formats)
- Auto-save preferences (Email notifications, SMS alerts, Language) — one-click persist
- Logout blacklists the refresh token server-side
- 1800 ms global HTTP timeout interceptor; spinners never run more than twice

### 💸 Transactions (every attempt audited)
| Type          | Endpoint                                  | Description                                        |
|---------------|-------------------------------------------|----------------------------------------------------|
| Transfer      | `POST /api/transactions/transfer/`        | Peer-to-peer transfer with `SELECT FOR UPDATE`     |
| Deposit       | `POST /api/transactions/deposit/initiate/`| Mobile-money recharge (Orange / MTN, NotchPay)    |
| Withdrawal    | `POST /api/transactions/withdrawal/`      | Cash-out to mobile-money                           |
| Bill payment  | `POST /api/transactions/bill-payment/`    | ENEO, CAMWATER, CANAL+, CAMTEL                     |
| Airtime       | `POST /api/transactions/airtime/`         | MTN / Orange top-up                                |

References follow `ELITE-{TXN|DEP|WTH|PAY|AIR}-XXXXXXXX`. Failed transfers persist as
`FAILED` records so audit trails remain complete.

### 🔖 Beneficiaries
- `GET /POST /api/auth/beneficiaries/` · `DELETE /api/auth/beneficiaries/<uuid>/`
- Three categories (Transfer / Airtime / Bill_Payment) with provider validation
- Inline "Save Beneficiary" prompts after successful transactions
- Saved-recipient chips on Transfer and Payments pages

### 🔔 Notifications
- Persistent `Notification` model with categories & severity (`INFO`/`SUCCESS`/`WARNING`/`ERROR`)
- Bell-dropdown component in every topbar — shared state, polls every 30 s
- Dedicated `/notifications` page with filters, mark-all-read, delete
- Automatically created on transfer / deposit / withdrawal / bill / airtime / 2FA / password change

### 📄 Statement Download
- `GET /api/transactions/statement/?from=YYYY-MM-DD&to=YYYY-MM-DD&fmt=pdf|csv`
- PDF: branded layout, color-coded status pills + amount signs (green/red), summary card
- CSV: full machine-readable export

### 🛡 Health & Docs
- `GET /healthz/` — liveness probe
- `GET /readyz/` — readiness probe (DB connectivity)
- `GET /api/schema/` — OpenAPI 3.0 YAML
- `GET /api/docs/` — Swagger UI (interactive)
- `GET /api/redoc/` — ReDoc alternative

---

## 📁 Repository Layout

```
elite-bank-final/
├── backend/                         Django REST API
│   ├── accounts/                    Custom User + Beneficiary + Notification models
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py                 Jazzmin-flavoured ModelAdmin
│   │   ├── services/                sms / storage / notifications helpers
│   │   └── management/commands/
│   │       └── seed_demo.py         Populate realistic demo data
│   ├── transactions/                Transaction model, transfer/deposit/etc.
│   │   ├── models.py                Transaction with typed ELITE- references
│   │   ├── serializers.py           Business-rule validation
│   │   ├── views.py                 TransferView, DepositInitiateView, WithdrawalView…
│   │   └── services/                notchpay / email / statement
│   ├── core/
│   │   ├── settings.py              Reads .env via decouple
│   │   ├── urls.py                  + health + Swagger
│   │   └── health.py
│   ├── smoke_test.py                40+ endpoint end-to-end smoke test
│   ├── requirements.txt
│   ├── render.yaml                  ← Render Blueprint
│   ├── Procfile                     ← Render fallback
│   └── manage.py
└── frontend/                        Angular 21 SPA
    └── src/app/
        ├── auth/                    login + register (Reactive forms)
        ├── pages/
        │   ├── home/                Landing
        │   ├── dashboard/           Balance card + recent transactions
        │   ├── profile/             Settings + Help modal
        │   ├── transactions/        List + Statement modal
        │   │   ├── transfer/
        │   │   ├── deposit/
        │   │   └── withdrawal/
        │   ├── payments/            Bills + Airtime
        │   └── notifications/
        ├── components/
        │   ├── navbar/              Landing navbar
        │   ├── hero/  features/  cta/  footer/
        │   ├── notif-bell/          Shared notification dropdown
        │   └── user-avatar/         Avatar with initials fallback
        ├── services/                auth, user, transaction, beneficiary,
        │                            notification, language
        ├── interceptors/            auth.interceptor + http-timeout.interceptor
        ├── guards/                  authGuard
        ├── pipes/                   t.pipe (i18n)
        ├── i18n/                    translations.ts (en + fr dictionary)
        └── environments/            environment.ts + environment.prod.ts
```

---

## ⚙ Local Setup

### Prerequisites
- Python 3.11+
- Node 20+
- npm 10+

### 1. Backend
```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser           # for /admin/
python manage.py seed_demo --wipe --users 3  # optional demo data
python manage.py runserver
```
Backend live at <http://127.0.0.1:8000/>.

### 2. Frontend (separate terminal)
```bash
cd frontend
npm install
npm start    # ng serve, http://localhost:4200/
```

### 3. Verify everything works (optional but recommended)
```bash
cd backend
python manage.py shell -c "exec(open('smoke_test.py', encoding='utf-8').read())"
```
Expected: **40+ PASS, 0 FAIL** — hits every public endpoint end-to-end.

---

## 🔑 Demo Credentials

After running `python manage.py seed_demo --wipe --users 3`:

| Email                 | Password   | Notes                                  |
|-----------------------|------------|----------------------------------------|
| alice@demo.local      | demo1234   | Full transaction history seeded        |
| bob@demo.local        | demo1234   | Receives transfers from Alice           |
| claire@demo.local     | demo1234   | Recent transfers + deposits             |

Admin: created via `createsuperuser`, e.g. `admin@elite-bank.cm` / your choice.

---

## 🚀 Deployment

### Backend → Render

This repo ships with [`backend/render.yaml`](backend/render.yaml). Steps:

1. Push the repo to GitHub.
2. On **render.com** → **New +** → **Blueprint** → select your repo.
3. Render reads `render.yaml` and provisions:
   - A free PostgreSQL instance
   - A web service running `gunicorn core.wsgi:application`
   - Build step running `pip install`, `migrate`, `collectstatic`
4. After the first deploy, set these env vars in the Render dashboard if not auto-generated:
   - `SECRET_KEY` → 50+ random characters
   - `DEBUG` → `False`
   - `ALLOWED_HOSTS` → `<your-service>.onrender.com`
   - `FRONTEND_URL` → `https://<your-frontend>.vercel.app`
   - `NOTCHPAY_PUBLIC_KEY` → leave empty for demo mode, or set your sandbox key

Your API will live at `https://<service>.onrender.com/` with docs at `/api/docs/`.

### Frontend → Vercel

1. Edit [`frontend/src/environments/environment.prod.ts`](frontend/src/environments/environment.prod.ts):
   ```ts
   export const environment = {
     production: true,
     apiUrl: 'https://<your-service>.onrender.com'
   };
   ```
2. On **vercel.com** → **Add New** → **Project** → import the repo.
3. **Root Directory**: `frontend`
4. **Build Command**: `npm run build`
5. **Output Directory**: `dist/frontend/browser`
6. The bundled [`frontend/vercel.json`](frontend/vercel.json) handles SPA route rewrites
   (every path → `index.html`).

Your app will live at `https://<your-project>.vercel.app/`.

---

## 🔐 JWT Flow

```
POST /api/auth/login/  → { user, tokens: { access, refresh } }
        ↓
AuthService.storeTokens()  → localStorage
        ↓
Every request: authInterceptor adds  Authorization: Bearer <access>
                          httpTimeoutInterceptor enforces 1800 ms
        ↓
On 401:  TokenRefreshView consumed via /api/auth/token/refresh/
        ↓
Logout:  blacklists refresh token server-side, clears local storage,
         stops the notification polling loop
```

---

## 🌍 Languages

Switching the profile language dropdown:

1. Calls `LanguageService.use('fr')` → flips UI immediately (optimistic).
2. PATCHes `/api/auth/me/` with the new language.
3. On next login, `UserService` reads `user.language` and replays it.

Translation keys live in [`src/app/i18n/translations.ts`](frontend/src/app/i18n/translations.ts).
The `{{ 'key.path' | t }}` pipe is impure → re-renders the entire UI when the language flips.

---

## 🧪 Testing

| Layer    | How                                                           |
|----------|---------------------------------------------------------------|
| Backend  | `python manage.py shell -c "exec(open('smoke_test.py')...)"` |
| Backend  | `python manage.py check`                                       |
| Frontend | `npx ng build --configuration development`                    |

---

## 📜 Endpoints Reference

### Auth
| Method | Path                                       | Auth   | Purpose                                                      |
|--------|--------------------------------------------|--------|--------------------------------------------------------------|
| POST   | `/api/auth/register/`                      | Public | Create account, returns JWT                                  |
| POST   | `/api/auth/login/`                         | Public | Login. If 2FA on: returns `{ requires_otp, challenge_id }`   |
| POST   | `/api/auth/logout/`                        | JWT    | Blacklist refresh token                                      |
| POST   | `/api/auth/token/refresh/`                 | —      | Refresh access token                                         |
| GET    | `/api/auth/me/`                            | JWT    | Current user profile                                         |
| PATCH  | `/api/auth/me/`                            | JWT    | Update name/phone/language/prefs                             |
| POST   | `/api/auth/change-password/`               | JWT    | Change password                                              |
| POST   | `/api/auth/password-reset/request/`        | Public | Email a reset link (always 200 — no email enumeration)       |
| POST   | `/api/auth/password-reset/confirm/`        | Public | Submit signed token + new password                            |
| POST   | `/api/auth/2fa/`                           | JWT    | Toggle 2FA flag                                              |
| POST   | `/api/auth/2fa/verify/`                    | Public | Verify OTP after 2FA-enabled login → returns JWT             |
| POST   | `/api/auth/2fa/resend/`                    | Public | Re-issue a fresh OTP for the same challenge                  |
| POST   | `/api/auth/avatar/`                        | JWT    | Upload avatar                                                |

### Beneficiaries
| Method | Path                                       | Purpose                |
|--------|--------------------------------------------|------------------------|
| GET    | `/api/auth/beneficiaries/?category=…`      | List                   |
| POST   | `/api/auth/beneficiaries/`                 | Create                 |
| GET    | `/api/auth/beneficiaries/<uuid>/`          | Retrieve               |
| DELETE | `/api/auth/beneficiaries/<uuid>/`          | Delete                 |

### Notifications
| Method | Path                                                | Purpose                         |
|--------|-----------------------------------------------------|---------------------------------|
| GET    | `/api/auth/notifications/?unread=1&limit=20`        | List with unread_count          |
| POST   | `/api/auth/notifications/<uuid>/read/`              | Mark read                       |
| POST   | `/api/auth/notifications/mark-all-read/`            | Mark all read                   |
| DELETE | `/api/auth/notifications/<uuid>/delete/`            | Delete                          |

### Transactions
| Method | Path                                               | Purpose                          |
|--------|----------------------------------------------------|----------------------------------|
| GET    | `/api/transactions/?type=…&status=…`               | List user's transactions         |
| GET    | `/api/transactions/<uuid>/`                        | Retrieve                         |
| POST   | `/api/transactions/transfer/`                      | Peer-to-peer transfer            |
| POST   | `/api/transactions/deposit/initiate/`              | Mobile-money deposit             |
| GET    | `/api/transactions/deposit/status/<ref>/`          | Poll deposit status              |
| POST   | `/api/transactions/deposit/callback/`              | NotchPay webhook                 |
| POST   | `/api/transactions/withdrawal/`                    | Mobile-money withdrawal          |
| POST   | `/api/transactions/bill-payment/`                  | Utility bill payment             |
| POST   | `/api/transactions/airtime/`                       | Airtime purchase                 |
| GET    | `/api/transactions/statement/?from=…&to=…&fmt=…`   | Download statement (PDF / CSV)   |

### Ops
| Method | Path             | Purpose                       |
|--------|------------------|-------------------------------|
| GET    | `/healthz/`      | Liveness probe                |
| GET    | `/readyz/`       | Readiness probe + DB check    |
| GET    | `/api/schema/`   | OpenAPI 3.0 YAML              |
| GET    | `/api/docs/`     | Swagger UI                    |
| GET    | `/api/redoc/`    | ReDoc                         |
| GET    | `/admin/`        | Django Admin (Jazzmin theme)  |

---

## 📌 Live URLs

- **Source code:** <https://github.com/alapani-svg/EliteBank-cm>
- **Backend (Render):** `https://_____.onrender.com` _(fill in after first deploy)_
- **Frontend (Vercel):** `https://_____.vercel.app` _(fill in after first deploy)_
- **Swagger docs:** `https://_____.onrender.com/api/docs/`

---

## 🙏 Credits

Built by CORANTIN Yaoundé, Cameroon · © 2026
Contact: promptforge237@gmail.com
