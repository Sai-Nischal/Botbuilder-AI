# Botbuilder-AI
# BotBuilder ⚡ — Telegram Chatbot Generator for Businesses

BotBuilder is a full-featured web application that enables business owners to generate, customize, and publish interactive Telegram chatbots powered by their business details and PDF documents.

Replies are selected using **strict rule matching, button navigation, and vector embedding similarity** — ensuring **zero live LLM generation costs** during customer chat sessions.

---

## 🌟 Key Features
- **Deterministic FAQ Generation (Layer 1)**: Automatically structures FAQs from opening hours, location, contact, service pricing, and company policies without requiring an LLM.
- **Optional Gemini LLM Enrichment (Layer 2)**: Automatically enriches FAQs with alternative customer phrasings and extracts draft FAQs from uploaded PDFs if `GEMINI_API_KEY` is present.
- **Vector Embedding Similarity Engine**: Powered by `sentence-transformers` (`all-MiniLM-L6-v2`) with normalized matrix dot products and threshold scoring (`HIGH_THRESHOLD=0.60`, `LOW_THRESHOLD=0.40`).
- **PDF Document Intelligence**: Upload menus, brochures, or price lists (max 10MB, up to 5 files per business). Extracts passages (400-600 chars) and uses them as fallback answers (`PASSAGE_THRESHOLD=0.50`).
- **Shared & Branded Bot Modes**:
  - **Shared Platform Bot**: Deep link support (`https://t.me/<shared_bot>?start=<business_id>`) with persistent chat-to-business mapping.
  - **Branded Custom Bot**: Connect custom bot tokens created via Telegram's `@BotFather`. Tokens are encrypted at rest with Fernet cryptography and webhooks are verified via `X-Telegram-Bot-Api-Secret-Token`.
- **Security & Accounts**: Argon2 password hashing, HttpOnly SameSite=Lax signed session cookies, CSRF protection, rate limiting (`slowapi`), and strict business ownership isolation.

---

## 🚀 Quick Start & Local Setup

### 1. Requirements
- Python 3.11+
- Virtualenv
- Telegram Bot Token from `@BotFather`

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```
Example `.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
ENCRYPTION_KEY=dGhpcy1pcy1hLXRlc3QtZmVybmV0LWtleS0xMjM0NTY3ODk9
PUBLIC_BASE_URL=http://localhost:8000
GEMINI_API_KEY=
DATABASE_URL=sqlite:///./botbuilder.db
DEBUG=true
ENABLE_MANAGED_BOTS=false
```

### 3. Installation
Create virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Running locally (Web + Polling)
In development, run the web application server and the shared bot polling process concurrently:

**Terminal 1 (Web Server):**
```bash
python run_web.py
# Web app will be accessible at http://localhost:8000
```

**Terminal 2 (Shared Bot Polling):**
```bash
python run_polling.py
```

---

## 🤖 Creating & Connecting Branded Bots (@BotFather)

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow instructions to name your bot and choose a username.
3. Copy the HTTP API token provided by BotFather.
4. In BotBuilder, navigate to your Business Dashboard → Click **Custom Bot** (`/bot/<business_id>`).
5. Paste your token and click **Validate & Register Bot Webhook**.

*Note for local webhook testing*: Telegram requires a public HTTPS URL for webhooks. Use a tunneling tool like `ngrok` or `cloudflared`:
```bash
cloudflared tunnel --url http://localhost:8000
# Update PUBLIC_BASE_URL in .env with your https tunnel URL
```

---

## 🧪 Running Automated Tests
Run the complete test suite covering auth, FAQ generation, vector matcher, PDF parsing, and Fernet token encryption:
```bash
PYTHONPATH=. pytest -v
```

---

## 🐳 Docker & Production Deployment

### 1. Build and Run with Docker Compose
```bash
docker-compose up --build -d
```
The Docker container automatically pre-downloads and warms the `all-MiniLM-L6-v2` sentence-transformers model during image build time so first request latencies are minimized.

### 2. Healthcheck Endpoint
The application exposes a `/healthz` endpoint returning `{"status": "ok"}`.

### 3. Setting Shared Bot Webhook in Production
To switch the shared platform bot to webhook mode on a public host:
```bash
python scripts/set_webhook.py --action set --url https://your-domain.com/telegram/webhook/shared
```

---

## ⚙️ Threshold Tuning & Memory Optimization

### Similarity Thresholds (`app/config.py`)
- `HIGH_THRESHOLD` (Default `0.60`): Queries scoring above this score return the exact stored FAQ answer.
- `LOW_THRESHOLD` (Default `0.40`): Queries scoring between 0.40 and 0.60 return a "Did you mean:" prompt with top 3 FAQ suggestions.
- `PASSAGE_THRESHOLD` (Default `0.50`): If no FAQ reaches `LOW_THRESHOLD`, PDF document passages scoring above 0.50 are returned as smart fallbacks.

### Memory Constrained Hosts (< 1GB RAM)
For deployment on small hosts, `app/matcher.py` provides an abstract `EmbeddingBackend` interface. If `sentence-transformers` is omitted, the system seamlessly falls back to character n-gram TF-IDF matching or lightweight ONNX backends (such as `fastembed`).
