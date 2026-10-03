# BotBuilder Implementation Plan

## Project Overview
BotBuilder is a web application that enables business owners to generate, customize, and publish Telegram chatbots powered by their business details and uploaded PDF documents. Replies are selected via strict rule matching, button navigation, and embedding similarity (without live LLM generation during chat execution).

---

## Target File Structure
```
botbuilder/
├── app/
│   ├── __init__.py
│   ├── config.py           # App settings, paths, similarity thresholds, feature flags
│   ├── db.py               # SQLAlchemy database setup & ORM models (User, Business, Bot, ChatMapping, Document)
│   ├── models.py           # Pydantic data schemas (BusinessConfig, FAQ, Services, etc.)
│   ├── security.py         # Password hashing (Argon2), Fernet token encryption, CSRF tokens, session signing
│   ├── auth.py             # Auth logic, login/signup handlers, session management, ownership guards
│   ├── faq_generator.py    # Layer 1 deterministic FAQ generator + Layer 2 optional Gemini LLM enrichment
│   ├── documents.py        # PDF validation (header magic bytes), pypdf text extraction, passage chunking
│   ├── matcher.py          # Embedding backend interface (SentenceTransformers / fallback), vector index builder (.npz), cosine similarity
│   ├── telegram_api.py     # Async Telegram Bot API helper using httpx (sendMessage, setWebhook, deleteWebhook, getMe)
│   ├── bot_providers.py    # BotProvider interface for BotFather token integration and Managed Bots stub
│   ├── bot_core.py         # Unified Telegram update handler (resolving business via chat mapping or branded bot, scoring queries)
│   └── main.py             # FastAPI app initialization, routes, CSRF middleware, webhooks (/telegram/webhook/*), /healthz
├── templates/              # Jinja2 HTML templates with modern glassmorphic aesthetics
│   ├── base.html
│   ├── landing.html
│   ├── signup.html
│   ├── login.html
│   ├── dashboard.html
│   ├── create.html
│   ├── review.html
│   ├── done.html
│   ├── edit.html
│   ├── bot.html
│   └── documents.html
├── static/
│   ├── css/style.css       # Premium CSS design system (glassmorphism, subtle micro-animations, vibrant dark palette)
│   └── js/app.js           # Client-side dynamic interactivity (dynamic services, FAQ reorder, copy link)
├── data/
│   ├── businesses/         # JSON config export files
│   ├── index/              # Business embedding index files (.npz)
│   └── docs/               # Uploaded PDF document storage (outside static web root)
├── scripts/
│   └── set_webhook.py      # Script to register/unregister shared/branded bot webhooks
├── tests/
│   ├── test_auth.py        # Accounts, session, ownership checks
│   ├── test_faq.py         # Layer 1 deterministic FAQ generation
│   ├── test_matcher.py     # Vector indexing and similarity match tests
│   ├── test_bot_core.py    # Telegram reply logic and fallback testing
│   ├── test_documents.py   # PDF magic byte validation, text extraction, passage chunking
│   └── test_security.py    # Encryption at rest, secret token verification
├── run_web.py              # Runner script for FastAPI web application
├── run_polling.py          # Development runner for shared bot long polling
├── Dockerfile              # Production Dockerfile with pre-downloaded sentence-transformers model
├── docker-compose.yml      # Multi-container compose configuration (web + optional postgres + volume persistence)
├── requirements.txt        # Python dependency manifest
├── .env.example            # Sample environment variables template
└── README.md               # Complete setup, deployment, tunnel, and threshold tuning documentation
```

---

## Key Milestones & Execution Flow

1. **Milestone 1: Project Skeleton & Configuration**
   - Setup `requirements.txt`, `.env.example`, `config.py`, SQLAlchemy models in `db.py`.
   - Verify DB creation and environment variable loading.

2. **Milestone 2: Accounts & Authentication**
   - Argon2 password hashing in `security.py`.
   - Cookie-based session handling, CSRF protection, rate limiting (`slowapi`).
   - Ownership validation helper (`verify_business_ownership`).
   - Web routes: `/signup`, `/login`, `/logout`, `/dashboard`.

3. **Milestone 3: Business Config Creation**
   - `/create` multi-step form and Pydantic schema validation (`models.py`).
   - Business slugification and persistence to SQLite + `data/businesses/{business_id}.json`.

4. **Milestone 4: Layer 1 FAQ Generation**
   - Deterministic rule-based FAQ generator (`faq_generator.py`) for hours, contact, services, policies.
   - Comprehensive unit test verifying generation without LLM dependencies.

5. **Milestone 5: Review / Edit Page & Publishing Flow**
   - UI `/review/{business_id}` for editing, adding, deleting, reordering, and toggling `show_as_button`.
   - FAQ publishing state mutation and index trigger.

6. **Milestone 6: Matcher & Vector Indexing**
   - `EmbeddingBackend` abstract class and `SentenceTransformerBackend` (model `all-MiniLM-L6-v2`) in `matcher.py`.
   - Matrix building, `.npz` storage in `data/index/`, cosine similarity query function with confidence scores.
   - Unit tests for question rephrasings (e.g., "when do u start the day?" -> "Opening hours").

7. **Milestone 7: Shared Telegram Bot Core**
   - Deep link handler `/start {business_id}` and `(bot_id, chat_id) -> business_id` chat mapping.
   - Unified update handling logic in `bot_core.py`.
   - High threshold (0.60), Low threshold (0.40) handling with top 3 "Did you mean:" buttons.
   - Polling script `run_polling.py` for dev mode.

8. **Milestone 8: Done Page & Edit Flow**
   - `/done/{business_id}` page displaying Telegram deep link, generated QR code (`qrcode`), and copy button.
   - `/edit/{business_id}` form to re-edit business details and re-generate/re-index FAQs.

9. **Milestone 9: Branded Bots (BotFather Method)**
   - Fernet encryption for stored bot tokens (`security.py`).
   - Token validation via `getMe`, `setWebhook` with per-bot `secret_token` header.
   - Branded bot webhook router `/telegram/webhook/{bot_key}` verifying `X-Telegram-Bot-Api-Secret-Token`.
   - Disconnect (`deleteWebhook` + token deletion) and Reconnect management via `/bot/{business_id}`.

10. **Milestone 10: PDF Processing & Passage Fallback**
    - File signature check (`%PDF-`), size limit (10MB), max 5 files per business.
    - Text extraction using `pypdf`, handling scanned PDFs (error on empty text).
    - Passage chunking (400-600 chars with overlap).
    - Indexing passages and implementing Telegram bot fallback (score >= 0.50).

11. **Milestone 11: Layer 2 LLM Enrichment (Optional)**
    - Gemini integration (`google-genai`) when `GEMINI_API_KEY` is present.
    - FAQ enrichment with alt_questions and candidate questions.
    - PDF FAQ extraction into draft FAQs.

12. **Milestone 12: Managed Bots Stub**
    - Managed bots connection stub behind `ENABLE_MANAGED_BOTS=false` feature flag.

13. **Milestone 13: Webhook Deployment & Production Readiness**
    - Production FastAPI web app handling shared and branded bot webhooks.
    - Startup re-registration of webhooks if `PUBLIC_BASE_URL` changes.
    - `/healthz` endpoint, Dockerfile with pre-warmed sentence-transformers model, `docker-compose.yml`, `scripts/set_webhook.py`.

14. **Milestone 14: Final Testing & Documentation**
    - Execute end-to-end verification tests.
    - Write complete `README.md` covering setup, BotFather steps, tunneling, deployment, and threshold tuning.

---

## Identified Technical Risks & Mitigation
- **PyTorch/RAM Overhead**: `sentence-transformers` can use ~300MB RAM. *Mitigation*: The backend architecture is hidden behind `EmbeddingBackend` in `matcher.py` allowing instant switch to fastembed/ONNX if memory constrained.
- **Telegram Webhook Security**: Malicious actors calling webhook endpoints directly. *Mitigation*: Telegram's `X-Telegram-Bot-Api-Secret-Token` header is strictly checked for both shared and branded bot webhooks.
- **Scanned / Image PDFs**: Users uploading non-searchable PDFs. *Mitigation*: Verify `%PDF-` binary magic bytes and test for non-zero extracted text, returning clear UI feedback if text extraction yields empty content.
