import json
import asyncio
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from app.models import BusinessConfig, FAQItem, ResearchResult, ResearchField, Evidence
from app.config import GEMINI_API_KEY, GOOGLE_PLACES_API_KEY

# --- ADK-Style Agent Framework Implementation ---

class BaseResearchAgent:
    def __init__(self, name: str):
        self.name = name

    async def log(self, message: str):
        print(f"[{self.name}] {message}")

class IdentificationAgent(BaseResearchAgent):
    """Resolves Google Maps URLs to a verified business entity."""
    async def research(self, gmaps_url: str) -> Dict[str, Any]:
        await self.log(f"Resolving business identity for: {gmaps_url}")
        import httpx
        from urllib.parse import unquote

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(gmaps_url, headers=headers)
                resolved_url = str(resp.url)
                html_content = resp.text

                all_urls = [gmaps_url, resolved_url] + [str(r.url) for r in resp.history]

                extracted_place_name = ""
                for u in all_urls:
                    m = re.search(r'/place/([^/@?]+)', u)
                    if m:
                        extracted_place_name = unquote(m.group(1).replace("+", " "))
                        break

                if not extracted_place_name:
                    titles = re.findall(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
                    if titles:
                        t_clean = titles[0].replace(" - Google Maps", "").strip()
                        if t_clean and t_clean.lower() != "google maps":
                            extracted_place_name = t_clean

                # Coordinates
                lat, lon = None, None
                for u in all_urls:
                    c_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', u) or re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', u)
                    if c_match:
                        lat, lon = c_match.group(1), c_match.group(2)
                        break

                # Reverse Geocoding
                real_address = ""
                if lat and lon:
                    try:
                        geo_resp = await client.get(
                            f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}",
                            headers={"User-Agent": "BotBuilderMapsAgent/1.0"}
                        )
                        if geo_resp.status_code == 200:
                            real_address = geo_resp.json().get("display_name", "")
                    except Exception:
                        pass

                if not extracted_place_name and not real_address:
                    raise ValueError("Business location could not be found. Please check the Google Maps link.")

                return {
                    "name": extracted_place_name,
                    "address": real_address,
                    "resolved_url": resolved_url,
                    "coords": (lat, lon)
                }
        except ValueError:
            raise
        except Exception as e:
            await self.log(f"Resolution error: {e}")
            raise ValueError("Business location could not be found. Please check the Google Maps link.")

class WebResearchAgent(BaseResearchAgent):
    """Extracts official websites and digital footprints directly from Google Maps data."""
    async def research(self, biz_info: Dict[str, Any]) -> Dict[str, Any]:
        await self.log(f"Extracting sources from Google Maps for {biz_info.get('name')}")
        # We no longer use google_search here.
        # We only return what was already found in the identification stage or
        # allow the DeepResearchAgent to handle it from the provided URL.
        return {
            "official_website": None,
            "socials": {},
            "sources": [biz_info.get("resolved_url")]
        }

class DeepResearchAgent(BaseResearchAgent):
    """Extracts specific facts (Pricing, Services, Hours) ONLY from the provided Google Maps source."""
    async def research(self, sources: List[str], biz_name: str) -> Dict[str, Any]:
        await self.log(f"Analyzing Google Maps content for {biz_name}")
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
        if not api_key:
            await self.log("No GEMINI_API_KEY configured. Skipping research.")
            return {"hours": {}, "services": [], "policies": {}, "evidence": []}

        client = genai.Client(api_key=api_key)

        # We fetch the HTML content of the URL and pass it directly to the LLM
        # because Gemini cannot "browse" a live URL without the search tool.
        # Since search is forbidden, we must provide the content.
        import httpx
        html_content = ""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client_http:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                resp = await client_http.get(sources[0], headers=headers)
                html_content = resp.text
        except Exception as e:
            await self.log(f"Failed to fetch URL content: {e}")

        # IMPORTANT: We now tell the AI to ONLY use the provided content.
        prompt = f"""You are analyzing the HTML content of a Google Maps page for the business: {biz_name}.

        CONTENT:
        {html_content}

        Task: Extract ONLY the information present in the provided HTML.
        DO NOT search the wider web. DO NOT use your general knowledge.

        Extract:
        1. Phone Number
        2. Opening hours (Mon-Sat, Sun)
        3. List of services with prices and descriptions
        4. Refund, Booking, and Payment policies

        CRITICAL: If the information is not explicitly mentioned in the provided HTML, return null.
        Return ONLY a valid JSON object:
        {{
          "phone": "...",
          "hours": {{ "mon_sat": "...", "sun": "..." }},
          "services": [{{ "name": "...", "price": "...", "details": "..." }}],
          "policies": {{ "refund": "...", "booking": "...", "payment": "..." }},
          "evidence": [{{ "field": "...", "url": "{sources[0]}", "quote": "..." }}]
        }}
        """

        try:
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            raw_text = res.text.strip()
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]

            return json.loads(raw_text)
        except Exception as e:
            await self.log(f"Research error: {e}")
            return {"hours": {}, "services": [], "policies": {}, "evidence": []}

class VerificationAgent(BaseResearchAgent):
    """Cross-checks data and detects conflicts."""
    async def verify(self, identity_data: Dict, web_data: Dict, deep_data: Dict) -> ResearchResult:
        await self.log("Cross-referencing sources for conflicts...")

        res = ResearchResult()

        # Helper to create ResearchField
        def create_field(val: Any, source: str, quote: str = "") -> ResearchField:
            if not val: return ResearchField()
            return ResearchField(
                value=str(val),
                evidence=[Evidence(source_url=source, source_type="web", text_segment=quote)]
            )

        # Simple synthesis for this implementation
        res.name = create_field(identity_data.get("name"), "google_maps")
        res.address = create_field(identity_data.get("address"), "google_maps")
        res.phone = create_field(deep_data.get("phone"), "deep_research")
        res.website = create_field(web_data.get("official_website"), "web_search")

        deep_hours = deep_data.get("hours", {})
        res.mon_sat_hours = create_field(deep_hours.get("mon_sat"), "deep_research")
        res.sun_hours = create_field(deep_hours.get("sun"), "deep_research")

        deep_pol = deep_data.get("policies", {})
        res.refund_policy = create_field(deep_pol.get("refund"), "deep_research")
        res.booking_policy = create_field(deep_pol.get("booking"), "deep_research")
        res.payment_methods = create_field(deep_pol.get("payment"), "deep_research")

        # Services mapping
        res.services = []
        for s in deep_data.get("services", []):
            res.services.append({
                "name": ResearchField(value=s.get("name")),
                "price": ResearchField(value=s.get("price")),
                "details": ResearchField(value=s.get("details"))
            })

        return res

class BusinessResearchRootAgent(BaseResearchAgent):
    """Orchestrates the entire research pipeline."""
    def __init__(self, job_id: str, update_callback):
        super().__init__("RootAgent")
        self.job_id = job_id
        self.update_callback = update_callback
        self.id_agent = IdentificationAgent("IdAgent")
        self.web_agent = WebResearchAgent("WebAgent")
        self.deep_agent = DeepResearchAgent("DeepAgent")
        self.verify_agent = VerificationAgent("VerifyAgent")

    async def run(self, gmaps_url: str):
        try:
            # Stage 1: Identification
            await self._safe_update("identifying", 10)
            biz_id = await self.id_agent.research(gmaps_url)

            # Stage 2: Web Research
            await self._safe_update("web_research", 30)
            web_data = await self.web_agent.research(biz_id)

            # Stage 3: Deep Research
            await self._safe_update("deep_research", 60)
            resolved_url = biz_id.get("resolved_url") or gmaps_url
            sources = web_data.get("sources", [resolved_url])
            deep_data = await self.deep_agent.research(sources, biz_id.get("name"))

            # Stage 4: Verification
            await self._safe_update("verifying", 80)
            final_result = await self.verify_agent.verify(biz_id, web_data, deep_data)

            # Return as dict for the JobStore
            await self._safe_update("completed", 100, data=json.loads(final_result.json()))
        except Exception as e:
            await self.log(f"Pipeline failed: {e}")
            await self._safe_update("failed", 0, error=str(e))

    async def _safe_update(self, status: str, progress: int, data: Optional[Dict] = None, error: Optional[str] = None):
        """Safely calls the update callback to avoid 'NoneType' object can't be awaited."""
        try:
            if asyncio.iscoroutinefunction(self.update_callback):
                await self.update_callback(self.job_id, status, progress, data=data, error=error)
            else:
                self.update_callback(self.job_id, status, progress, data=data, error=error)
        except Exception as ue:
            await self.log(f"Update callback error: {ue}")

# --- Pipeline Entrypoint ---

async def run_business_research_pipeline(job_id: str, gmaps_url: str):
    """
    Entrypoint called by FastAPI BackgroundTasks.
    """
    from app.main import update_research_job
    root = BusinessResearchRootAgent(job_id, update_research_job)
    await root.run(gmaps_url)

# --- Legacy Support & FAQ Generation ---

def generate_layer1_faqs(cfg: 'BusinessConfig') -> List[FAQItem]:
    faqs = []
    current_id = 1

    # 1. Opening hours
    hours_parts = [f"{d}: {h}" for d, h in cfg.hours.items() if h]
    if hours_parts:
        faqs.append(FAQItem(
            id=current_id,
            q="What are your opening hours?",
            a=f"Hours: {', '.join(hours_parts)}",
            button_label="Hours",
            show_as_button=True
        ))
        current_id += 1

    # 2. Location
    if cfg.contact.address or cfg.contact.gmaps_url:
        loc_str = cfg.contact.address or ""
        if cfg.contact.gmaps_url:
            loc_str += f"\nGoogle Maps: {cfg.contact.gmaps_url}"
        faqs.append(FAQItem(
            id=current_id,
            q="Where are you located?",
            a=f"Address: {loc_str.strip()}",
            button_label="Location",
            show_as_button=True
        ))
        current_id += 1

    # 3. Contact Info
    c_parts = []
    if cfg.contact.phone: c_parts.append(f"Phone: {cfg.contact.phone}")
    if cfg.contact.email: c_parts.append(f"Email: {cfg.contact.email}")
    if cfg.contact.website: c_parts.append(f"Website: {cfg.contact.website}")
    if c_parts:
        faqs.append(FAQItem(
            id=current_id,
            q="How can I contact you?",
            a="\n".join(c_parts),
            button_label="Contact",
            show_as_button=True
        ))
        current_id += 1

    # 4. Services Overview
    if cfg.services:
        s_list = []
        for s in cfg.services:
            price_str = f" - {s.price}" if s.price else ""
            s_list.append(f"• {s.name}{price_str}")
        faqs.append(FAQItem(
            id=current_id,
            q="What services do you offer?",
            a="Here are our available services:\n" + "\n".join(s_list),
            button_label="Services",
            show_as_button=True
        ))
        current_id += 1

        # Individual Service FAQs
        for s in cfg.services:
            price_info = f"Price: {s.price}." if s.price else ""
            details_info = f" Details: {s.details}" if s.details else ""
            faqs.append(FAQItem(
                id=current_id,
                q=f"How much is {s.name}?",
                a=f"{s.name}: {price_info}{details_info}".strip(),
                button_label=s.name[:15],
                show_as_button=False
            ))
            current_id += 1

    # 5. Policies
    if cfg.policies.refund:
        faqs.append(FAQItem(
            id=current_id,
            q="What is your refund policy?",
            a=cfg.policies.refund,
            button_label="Refund Policy",
            show_as_button=False
        ))
        current_id += 1

    if cfg.policies.booking:
        faqs.append(FAQItem(
            id=current_id,
            q="How do I book an appointment or service?",
            a=cfg.policies.booking,
            button_label="Booking Policy",
            show_as_button=False
        ))
        current_id += 1

    pay_method = getattr(cfg.policies, 'payment_methods', getattr(cfg.policies, 'payment', ''))
    if pay_method:
        faqs.append(FAQItem(
            id=current_id,
            q="What payment methods do you accept?",
            a=pay_method,
            button_label="Payment Methods",
            show_as_button=False
        ))
        current_id += 1

    return faqs

def enrich_faqs_with_llm(cfg: 'BusinessConfig', existing_faqs: List[FAQItem]) -> List[FAQItem]:
    return existing_faqs

def generate_max_faqs_with_gemini(cfg: 'BusinessConfig'):
    return [], None, None

def generate_faqs_for_business(cfg: 'BusinessConfig') -> List[FAQItem]:
    return generate_layer1_faqs(cfg)

async def fetch_gmaps_info(gmaps_url: str) -> dict:
    """
    Fetches comprehensive business info from a Google Maps URL.
    """
    try:
        # Run the full research pipeline
        id_agent = IdentificationAgent("IdAgent")
        biz_id = await id_agent.research(gmaps_url)
        
        web_agent = WebResearchAgent("WebAgent")
        web_data = await web_agent.research(biz_id)
        
        deep_agent = DeepResearchAgent("DeepAgent")
        resolved_url = biz_id.get("resolved_url") or gmaps_url
        sources = web_data.get("sources", [resolved_url])
        deep_data = await deep_agent.research(sources, biz_id.get("name"))
        
        return {
            "name": biz_id.get("name"),
            "address": biz_id.get("address"),
            "phone": deep_data.get("phone"),
            "email": None, # Usually not on GMaps HTML
            "website": web_data.get("official_website"),
            "hours": deep_data.get("hours"),
            "services": deep_data.get("services"),
            "policies": deep_data.get("policies")
        }
    except Exception as e:
        return {"error": str(e)}
