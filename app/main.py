import io
import os
import re
import json
import base64
import random
import string
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import qrcode
from fastapi import FastAPI, Request, Form, File, UploadFile, Depends, HTTPException, status, Header, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import (
    PUBLIC_BASE_URL, TELEGRAM_BOT_TOKEN, GEMINI_API_KEY,
    ENABLE_MANAGED_BOTS, BUSINESSES_DIR, DOCS_DIR,
    MAX_BOTS_PER_USER, get_current_bot_token
)
from app.db import init_db, get_db, User, Business, Bot, Document, Passage
from app.models import (
    BusinessConfig, BotConfigSchema, ContactInfo, ServiceItem, PoliciesConfig,
    FAQItem, ResearchResult, ResearchField
)
from app.security import (
    hash_password, verify_password, sign_session, verify_session,
    generate_csrf_token, verify_csrf_token, mask_bot_token, decrypt_bot_token, encrypt_bot_token
)
from app.auth import get_current_user, require_login, verify_business_ownership, SESSION_COOKIE_NAME
from app.faq_generator import (
    generate_layer1_faqs, enrich_faqs_with_llm, generate_faqs_for_business,
    fetch_gmaps_info, run_business_research_pipeline
)
from app.gmaps_integration import run_gmaps_scraper
from app.matcher import build_business_index, get_embedding_backend
from app.bot_core import process_telegram_update
from app.bot_providers import BotFatherProvider
from app.documents import validate_pdf_bytes, extract_text_from_pdf, chunk_text_into_passages, extract_draft_faqs_from_pdf_llm
from app.telegram_api import get_me, set_webhook, delete_webhook, sync_bot_profile

# Setup Limiter for Rate Limiting login/signup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="BotBuilder", description="Telegram Chatbot Generator for Businesses")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount Static Files
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Setup Jinja2 Templates
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# --- Research Job Store ---
# In-memory store for research jobs. In production, this should be Redis or DB.
RESEARCH_JOBS: Dict[str, Dict[str, Any]] = {}

def update_research_job(job_id: str, status: str, progress: int, data: Optional[Dict] = None, error: Optional[str] = None):
    if job_id in RESEARCH_JOBS:
        RESEARCH_JOBS[job_id]["status"] = status
        RESEARCH_JOBS[job_id]["progress"] = progress
        if data:
            RESEARCH_JOBS[job_id]["data"] = data
        if error:
            RESEARCH_JOBS[job_id]["error"] = error

# ---------------------------

@app.on_event("startup")
async def on_startup():
    init_db()
    # Pre-load embedding model singleton once at startup
    get_embedding_backend()

    # Re-register active branded bot webhooks if PUBLIC_BASE_URL has changed
    db = next(get_db())
    try:
        branded_bots = db.query(Bot).filter(Bot.mode == "branded", Bot.is_active == True).all()
        for bot in branded_bots:
            if bot.encrypted_token:
                token = decrypt_bot_token(bot.encrypted_token)
                if token:
                    webhook_url = f"{PUBLIC_BASE_URL}/telegram/webhook/{bot.bot_key}"
                    await set_webhook(token, webhook_url, bot.secret_token)
    except Exception as e:
        print(f"[STARTUP WARNING] Webhook re-registration warning: {e}")
    finally:
        db.close()


def render(template_name: str, request: Request, context: dict):
    user = get_current_user(request, next(get_db()))
    session_val = request.cookies.get(SESSION_COOKIE_NAME, "")
    csrf_token = generate_csrf_token(session_val) if session_val else ""

    default_context = {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "enable_managed_bots": ENABLE_MANAGED_BOTS
    }
    default_context.update(context)
    return templates.TemplateResponse(request=request, name=template_name, context=default_context)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:30]


def generate_business_id(name: str) -> str:
    slug = slugify(name) or "biz"
    rand_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{slug}-{rand_chars}"


_SHARED_BOT_USERNAME_CACHE = None

def get_shared_bot_username() -> str:
    global _SHARED_BOT_USERNAME_CACHE
    if _SHARED_BOT_USERNAME_CACHE:
        return _SHARED_BOT_USERNAME_CACHE
    if TELEGRAM_BOT_TOKEN and ":" in TELEGRAM_BOT_TOKEN:
        try:
            import httpx
            resp = httpx.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=5.0)
            data = resp.json()
            if data.get("ok"):
                _SHARED_BOT_USERNAME_CACHE = data["result"].get("username", "bot")
                return _SHARED_BOT_USERNAME_CACHE
        except Exception as e:
            print(f"[BOT USERNAME ERROR] Could not fetch bot username: {e}")
    return "bot"


# Healthcheck Endpoint
@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "BotBuilder"}


# Webhook Endpoints
@app.post("/telegram/webhook/shared")
async def telegram_webhook_shared(request: Request, db: Session = Depends(get_db)):
    """Webhook handler for shared platform bot."""
    try:
        update = await request.json()
        await process_telegram_update(db, update, bot_key=None)
    except Exception as e:
        print(f"[SHARED WEBHOOK ERROR] {e}")
    return {"ok": True}


@app.post("/telegram/webhook/{bot_key}")
async def telegram_webhook_branded(
    bot_key: str,
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Webhook handler for custom branded bots with secret header verification."""
    bot = db.query(Bot).filter(Bot.bot_key == bot_key, Bot.is_active == True).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot webhook not found")

    # Reject requests whose secret token header doesn't match
    if bot.secret_token and x_telegram_bot_api_secret_token != bot.secret_token:
        raise HTTPException(status_code=403, detail="Invalid secret token header")

    try:
        update = await request.json()
        await process_telegram_update(db, update, bot_key=bot_key)
    except Exception as e:
        print(f"[BRANDED WEBHOOK ERROR] {e}")

    return {"ok": True}


# Landing Page
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render("landing.html", request, {})


# Auth Routes
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return render("signup.html", request, {})


@app.post("/signup")
@limiter.limit("5/minute")
def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    if len(password) < 6:
        return render("signup.html", request, {"error": "Password must be at least 6 characters long."})

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        return render("signup.html", request, {"error": "An account with this email already exists."})

    user = User(email=email_clean, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    cookie_val = sign_session(user.id)
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=cookie_val, httponly=True, samesite="lax")
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render("login.html", request, {})


@app.post("/login")
@limiter.limit("10/minute")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not verify_password(user.password_hash, password):
        return render("login.html", request, {"error": "Invalid email address or password."})

    cookie_val = sign_session(user.id)
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=cookie_val, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# Dashboard Page
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    businesses = db.query(Business).filter(Business.owner_id == user.id).order_by(Business.created_at.desc()).all()
    return render("dashboard.html", request, {"businesses": businesses})


# --- Google ADK Business Research API ---

@app.post("/api/business/research")
async def api_business_research(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_login)
):
    """
    Starts an asynchronous research job using the Google ADK multi-agent pipeline.
    Returns a job_id for polling.
    """
    try:
        data = await request.json()
        gmaps_url = data.get("gmaps_url", "").strip()
        if not gmaps_url:
            return JSONResponse({"success": False, "error": "Google Maps URL is required."}, status_code=400)

        # Integrated Playwright Scraper
        extracted = run_gmaps_scraper(gmaps_url)
        if extracted:
            return JSONResponse({"success": True, "data": extracted})
        else:
            return JSONResponse({"success": False, "error": "Failed to extract data from Google Maps."}, status_code=500)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/business/research/{job_id}")
async def api_get_research_status(job_id: str, user: User = Depends(require_login)):
    """
    Polls the status and results of a research job.
    """
    job = RESEARCH_JOBS.get(job_id)
    if not job:
        return JSONResponse({"success": False, "error": "Job not found."}, status_code=404)

    return JSONResponse({
        "success": True,
        "status": job["status"],
        "progress": job["progress"],
        "data": job["data"],
        "error": job["error"]
    })


# Legacy Endpoint - Kept for compatibility but can be deprecated
@app.post("/api/fetch-gmaps-info")
async def api_fetch_gmaps_info(
    request: Request,
    user: User = Depends(require_login)
):
    try:
        data = await request.json()
        gmaps_url = data.get("gmaps_url", "").strip()
        if not gmaps_url:
            return JSONResponse({"success": False, "error": "Google Maps URL is required."})

        # Now simply calls the same pipeline but synchronously (not recommended)
        # For backward compatibility, we call the old function or a simplified version
        # but since we are upgrading, we'll use the pipeline synchronously here if needed.
        # However, the new frontend should use /api/business/research.
        from app.faq_generator import fetch_gmaps_info
        extracted = await fetch_gmaps_info(gmaps_url)
        return JSONResponse({"success": True, "data": extracted})
    except Exception as e:
        print(f"[API FETCH GMAPS ERROR] {e}")
        return JSONResponse({"success": False, "error": str(e)})


# Business Creation Form
@app.get("/create", response_class=HTMLResponse)
def create_page(request: Request, user: User = Depends(require_login)):
    return render("create.html", request, {})


@app.post("/create")
def create_submit(
    request: Request,
    name: str = Form(...),
    industry: str = Form(""),
    description: str = Form(""),
    tone: str = Form("friendly"),
    languages: str = Form("English"),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    website: str = Form(""),
    gmaps_url: str = Form(""),
    mon_sat_hours: str = Form(""),
    sun_hours: str = Form(""),
    service_name: List[str] = Form([]),
    service_price: List[str] = Form([]),
    service_details: List[str] = Form([]),
    refund_policy: str = Form(""),
    booking_policy: str = Form(""),
    payment_methods: str = Form(""),
    welcome_message: str = Form(""),
    fallback_message: str = Form(""),
    bot_token: str = Form(""),
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    # Enforce limit of 4 chatbots per account
    user_biz_count = db.query(Business).filter(Business.owner_id == user.id).count()
    if user_biz_count >= MAX_BOTS_PER_USER:
        return render("create.html", request, {
            "error": f"Account limit reached. You can create a maximum of {MAX_BOTS_PER_USER} chatbots per account."
        })

    biz_id = generate_business_id(name)

    # Build services list
    services = []
    for s_name, s_price, s_det in zip(service_name, service_price, service_details):
        if s_name and s_name.strip():
            services.append(ServiceItem(name=s_name.strip(), price=s_price.strip(), details=s_det.strip()))

    hours = {}
    if mon_sat_hours.strip():
        hours["mon-sat"] = mon_sat_hours.strip()
    if sun_hours.strip():
        hours["sun"] = sun_hours.strip()

    cfg = BusinessConfig(
        business_id=biz_id,
        owner_id=user.id,
        bot=BotConfigSchema(mode="shared", username=""),
        name=name.strip(),
        industry=industry.strip(),
        description=description.strip(),
        tone=tone.strip(),
        languages=[l.strip() for l in languages.split(",") if l.strip()],
        contact=ContactInfo(
            phone=phone.strip(),
            email=email.strip(),
            address=address.strip(),
            website=website.strip(),
            gmaps_url=gmaps_url.strip()
        ),
        hours=hours,
        services=services,
        policies=PoliciesConfig(refund=refund_policy.strip(), booking=booking_policy.strip(), payment_methods=payment_methods.strip()),
        welcome_message=welcome_message.strip(),
        fallback_message=fallback_message.strip(),
        faqs=[]
    )

    # Priority 1: AI Maximum FAQ Generation (Fallback: Layer 1 Rule Engine)
    cfg.faqs = generate_faqs_for_business(cfg)

    # Persist Business record in DB
    business = Business(
        business_id=biz_id,
        owner_id=user.id,
        name=cfg.name,
        industry=cfg.industry,
        is_published=False
    )
    business.set_config_dict(cfg.dict())
    db.add(business)

    # Dedicated Bot Registration if token provided
    registered_branded_bot = False
    if bot_token and bot_token.strip():
        token_clean = bot_token.strip()
        try:
            # Validate token via Telegram API
            import asyncio
            bot_info = asyncio.run(get_me(token_clean))
            bot_username = bot_info.get("username", "")

            # Encrypt token at rest
            enc_token = encrypt_bot_token(token_clean)
            bot_key = f"branded-{biz_id}"
            secret_tok = generate_csrf_token(biz_id)[:32]

            cfg.bot.mode = "branded"
            cfg.bot.username = bot_username

            # Replace default Bot record with branded Bot record
            bot_rec = Bot(
                business_id=biz_id,
                mode="branded",
                bot_key=bot_key,
                encrypted_token=enc_token,
                bot_username=bot_username,
                secret_token=secret_tok,
                is_active=True
            )
            db.add(bot_rec)
            db.commit()
            registered_branded_bot = True

            # Auto-sync Telegram profile (setMyName, setMyDescription, setMyShortDescription)
            bio_text = f"Official AI Assistant for {cfg.name} ({cfg.industry or 'Business'})"
            desc_text = cfg.welcome_message or f"Welcome to {cfg.name}! Ask any question about our services."
            asyncio.create_task(sync_bot_profile(token_clean, cfg.name, desc_text, bio_text))

        except Exception as bot_err:
            print(f"[DEDICATED BOT REGISTRATION WARNING] {bot_err}")

    if not registered_branded_bot:
        # Create default shared Bot record
        bot_key = f"shared-{biz_id}"
        bot_rec = Bot(
            business_id=biz_id,
            mode="shared",
            bot_key=bot_key,
            secret_token=bot_key,
            is_active=True
        )
        db.add(bot_rec)
        db.commit()

    # Automatically sync Telegram Bot Profile (setMyName, setMyDescription, setMyShortDescription)
    active_token = get_current_bot_token()
    if active_token and ":" in active_token:
        try:
            import asyncio
            bio_text = f"Official AI Assistant for {cfg.name} ({cfg.industry or 'Business'})"
            desc_text = cfg.welcome_message or f"Welcome to {cfg.name}! Ask any question about our services."
            asyncio.create_task(sync_bot_profile(active_token, cfg.name, desc_text, bio_text))
        except Exception as sync_err:
            print(f"[PROFILE SYNC WARNING] {sync_err}")


    # Write to data/businesses/<business_id>.json
    json_path = BUSINESSES_DIR / f"{biz_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cfg.dict(), f, indent=2, ensure_ascii=False)

    return RedirectResponse(url=f"/review/{biz_id}", status_code=status.HTTP_303_SEE_OTHER)


# Review & Edit FAQs Page
@app.get("/review/{business_id}", response_class=HTMLResponse)
def review_page(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    cfg = business.get_config_dict()
    faqs = cfg.get("faqs", [])
    return render("review.html", request, {"business": business, "faqs": faqs})


@app.post("/review/{business_id}")
async def review_submit(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    form_data = await request.form()

    faq_ids = form_data.getlist("faq_ids[]")
    updated_faqs: List[FAQItem] = []

    for fid_str in faq_ids:
        q_val = form_data.get(f"faq_q_{fid_str}", "").strip()
        alt_str = form_data.get(f"faq_alt_{fid_str}", "").strip()
        a_val = form_data.get(f"faq_a_{fid_str}", "").strip()
        label_val = form_data.get(f"faq_button_label_{fid_str}", "").strip()
        show_btn = form_data.get(f"faq_show_button_{fid_str}") in ("true", "on", "1")

        if q_val and a_val:
            alt_list = [alt.strip() for alt in alt_str.split(",") if alt.strip()]
            updated_faqs.append(FAQItem(
                id=int(fid_str) if fid_str.isdigit() else len(updated_faqs) + 1,
                q=q_val,
                alt_questions=alt_list,
                a=a_val,
                button_label=label_val or q_val[:20],
                show_as_button=show_btn
            ))

    cfg_dict = business.get_config_dict()
    cfg_dict["faqs"] = [f.dict() for f in updated_faqs]
    business.set_config_dict(cfg_dict)
    business.is_published = True
    db.commit()

    # Save to data/businesses/<business_id>.json
    json_path = BUSINESSES_DIR / f"{business_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cfg_dict, f, indent=2, ensure_ascii=False)

    # Collect passages from database for vector index
    passages = []
    db_passages = db.query(Passage).filter(Passage.business_id == business_id).all()
    for p in db_passages:
        passages.append({"id": p.id, "content": p.content})

    # Build embedding index .npz
    build_business_index(business_id, updated_faqs, passages=passages)

    return RedirectResponse(url=f"/done/{business_id}", status_code=status.HTTP_303_SEE_OTHER)


# Done / Chat Link Page
@app.get("/done/{business_id}", response_class=HTMLResponse)
def done_page(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)

    # Get shared bot username dynamically from Telegram API
    shared_bot_username = get_shared_bot_username()

    # If business has a connected branded bot
    if business.bot and business.bot.mode == "branded" and business.bot.bot_username:
        telegram_link = f"https://t.me/{business.bot.bot_username}"
    else:
        telegram_link = f"https://t.me/{shared_bot_username}?start={business_id}"

    # Generate QR Code image in memory
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(telegram_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return render("done.html", request, {
        "business": business,
        "telegram_link": telegram_link,
        "qr_code_b64": qr_b64
    })


# Edit Details Page
@app.get("/edit/{business_id}", response_class=HTMLResponse)
def edit_page(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    cfg = business.get_config_dict()
    return render("edit.html", request, {"business": business, "cfg": cfg})


@app.post("/edit/{business_id}")
def edit_submit(
    business_id: str,
    request: Request,
    name: str = Form(...),
    industry: str = Form(""),
    description: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    website: str = Form(""),
    mon_sat_hours: str = Form(""),
    sun_hours: str = Form(""),
    service_name: List[str] = Form([]),
    service_price: List[str] = Form([]),
    service_details: List[str] = Form([]),
    welcome_message: str = Form(""),
    fallback_message: str = Form(""),
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    cfg_dict = business.get_config_dict()

    services = []
    for s_name, s_price, s_det in zip(service_name, service_price, service_details):
        if s_name and s_name.strip():
            services.append({"name": s_name.strip(), "price": s_price.strip(), "details": s_det.strip()})

    hours = {}
    if mon_sat_hours.strip():
        hours["mon-sat"] = mon_sat_hours.strip()
    if sun_hours.strip():
        hours["sun"] = sun_hours.strip()

    cfg_dict["name"] = name.strip()
    cfg_dict["industry"] = industry.strip()
    cfg_dict["description"] = description.strip()
    cfg_dict["contact"] = {"phone": phone.strip(), "email": email.strip(), "address": address.strip(), "website": website.strip()}
    cfg_dict["hours"] = hours
    cfg_dict["services"] = services
    if welcome_message.strip():
        cfg_dict["welcome_message"] = welcome_message.strip()
    if fallback_message.strip():
        cfg_dict["fallback_message"] = fallback_message.strip()

    business.name = name.strip()
    business.industry = industry.strip()
    business.set_config_dict(cfg_dict)
    db.commit()

    return RedirectResponse(url=f"/review/{business_id}", status_code=status.HTTP_303_SEE_OTHER)


# Branded Bot Settings Page
@app.get("/bot/{business_id}", response_class=HTMLResponse)
def bot_settings_page(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    bot = business.bot
    masked_token = "****"
    if bot and bot.encrypted_token:
        raw_t = decrypt_bot_token(bot.encrypted_token)
        masked_token = mask_bot_token(raw_t)

    return render("bot.html", request, {
        "business": business,
        "bot": bot,
        "masked_token": masked_token
    })


@app.post("/bot/{business_id}")
async def bot_settings_connect(
    business_id: str,
    request: Request,
    bot_token: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    provider = BotFatherProvider()

    try:
        res = await provider.connect_bot(db, business, bot_token)
        return render("bot.html", request, {
            "business": business,
            "bot": business.bot,
            "masked_token": mask_bot_token(bot_token),
            "success": f"Successfully connected bot @{res['bot_username']}!"
        })
    except Exception as e:
        return render("bot.html", request, {
            "business": business,
            "bot": business.bot,
            "masked_token": "****",
            "error": str(e)
        })


@app.post("/bot/{business_id}/disconnect")
async def bot_settings_disconnect(
    business_id: str,
    request: Request,
    bot_token: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    provider = BotFatherProvider()
    await provider.disconnect_bot(db, business)
    return RedirectResponse(url=f"/bot/{business_id}", status_code=status.HTTP_303_SEE_OTHER)


# PDF Documents Page
@app.get("/documents/{business_id}", response_class=HTMLResponse)
def documents_page(
    business_id: str,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    documents = db.query(Document).filter(Document.business_id == business_id).all()
    return render("documents.html", request, {"business": business, "documents": documents})


@app.post("/documents/{business_id}")
async def documents_upload(
    business_id: str,
    request: Request,
    pdf_file: UploadFile = File(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)

    # Check max file count
    current_count = db.query(Document).filter(Document.business_id == business_id).count()
    if current_count >= 5:
        documents = db.query(Document).filter(Document.business_id == business_id).all()
        return render("documents.html", request, {
            "business": business,
            "documents": documents,
            "error": "Maximum file limit reached (5 PDFs per business)."
        })

    try:
        contents = await pdf_file.read()
        validate_pdf_bytes(contents)

        # Save to data/docs/
        stored_filename = f"{business_id}_{random.randint(1000, 9999)}_{pdf_file.filename}"
        doc_path = DOCS_DIR / stored_filename
        with open(doc_path, "wb") as f:
            f.write(contents)

        # Extract text
        extracted_text = extract_text_from_pdf(doc_path)
        passages = chunk_text_into_passages(extracted_text)

        # Save Document & Passages to DB
        doc_rec = Document(
            business_id=business_id,
            filename=pdf_file.filename,
            stored_filename=stored_filename,
            file_size=len(contents)
        )
        db.add(doc_rec)
        db.commit()
        db.refresh(doc_rec)

        for idx, passage_str in enumerate(passages):
            p_rec = Passage(
                document_id=doc_rec.id,
                business_id=business_id,
                content=passage_str,
                chunk_index=idx
            )
            db.add(p_rec)

        # Optional LLM draft FAQ extraction
        if GEMINI_API_KEY:
            draft_res = extract_draft_faqs_from_pdf_llm(extracted_text)
            draft_faqs = draft_res.get("faqs", [])
            if draft_faqs:
                cfg_dict = business.get_config_dict()
                current_faqs = cfg_dict.get("faqs", [])
                next_id = max([f.get("id", 0) for f in current_faqs], default=0) + 1
                for df in draft_faqs:
                    current_faqs.append({
                        "id": next_id,
                        "q": df.get("q", ""),
                        "alt_questions": df.get("alt_questions", []),
                        "a": df.get("a", ""),
                        "button_label": df.get("button_label", df.get("q", "")[:20]),
                        "show_as_button": False
                    })
                    next_id += 1
                cfg_dict["faqs"] = current_faqs
                business.set_config_dict(cfg_dict)
        db.commit()

        # Rebuild vector index with updated passages
        cfg_dict = business.get_config_dict()
        faq_objs = [FAQItem(**f) for f in cfg_dict.get("faqs", [])]
        all_passages = [{"id": p.id, "content": p.content} for p in db.query(Passage).filter(Passage.business_id == business_id).all()]
        build_business_index(business_id, faq_objs, passages=all_passages)

        documents = db.query(Document).filter(Document.business_id == business_id).all()
        return render("documents.html", request, {
            "business": business,
            "documents": documents,
            "success": f"Successfully processed '{pdf_file.filename}' into {len(passages)} passages!"
        })

    except ValueError as ve:
        documents = db.query(Document).filter(Document.business_id == business_id).all()
        return render("documents.html", request, {
            "business": business,
            "documents": documents,
            "error": str(ve)
        })
    except Exception as e:
        documents = db.query(Document).filter(Document.business_id == business_id).all()
        return render("documents.html", request, {
            "business": business,
            "documents": documents,
            "error": f"Upload failed: {str(e)}"
        })


@app.post("/documents/{business_id}/delete/{doc_id}")
def documents_delete(
    business_id: str,
    doc_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    business = verify_business_ownership(db, business_id, user.id)
    doc_rec = db.query(Document).filter(Document.id == doc_id, Document.business_id == business_id).first()

    if doc_rec:
        # Delete file on disk
        doc_path = DOCS_DIR / doc_rec.stored_filename
        if doc_path.exists():
            try:
                os.remove(doc_path)
            except Exception:
                pass

        db.delete(doc_rec)
        db.commit()

        # Rebuild vector index
        cfg_dict = business.get_config_dict()
        faq_objs = [FAQItem(**f) for f in cfg_dict.get("faqs", [])]
        all_passages = [{"id": p.id, "content": p.content} for p in db.query(Passage).filter(Passage.business_id == business_id).all()]
        build_business_index(business_id, faq_objs, passages=all_passages)

    return RedirectResponse(url=f"/documents/{business_id}", status_code=status.HTTP_303_SEE_OTHER)
