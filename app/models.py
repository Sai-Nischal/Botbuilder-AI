from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, EmailStr

# --- Existing Models ---

class FAQItem(BaseModel):
    id: int
    q: str
    alt_questions: List[str] = Field(default_factory=list)
    a: str
    button_label: str
    show_as_button: bool = True


class BotConfigSchema(BaseModel):
    mode: str = "shared"
    username: str = ""


class ContactInfo(BaseModel):
    phone: str = ""
    email: str = ""
    address: str = ""
    website: str = ""
    gmaps_url: str = ""


class ServiceItem(BaseModel):
    name: str
    price: str = ""
    details: str = ""


class PoliciesConfig(BaseModel):
    refund: str = ""
    booking: str = ""
    payment_methods: str = ""


class BusinessConfig(BaseModel):
    business_id: str
    owner_id: int
    bot: BotConfigSchema = Field(default_factory=BotConfigSchema)
    name: str
    industry: str = ""
    description: str = ""
    tone: str = "friendly"
    languages: List[str] = Field(default_factory=lambda: ["English"])
    contact: ContactInfo = Field(default_factory=ContactInfo)
    hours: Dict[str, str] = Field(default_factory=dict)
    services: List[ServiceItem] = Field(default_factory=list)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    welcome_message: str = ""
    fallback_message: str = ""
    faqs: List[FAQItem] = Field(default_factory=list)


# Form models
class SignupForm(BaseModel):
    email: EmailStr
    password: str


class LoginForm(BaseModel):
    email: EmailStr
    password: str


class BusinessCreateForm(BaseModel):
    name: str
    industry: str = ""
    description: str = ""
    tone: str = "friendly"
    languages: str = "English"
    phone: str = ""
    email: str = ""
    address: str = ""
    website: str = ""
    mon_sat_hours: str = ""
    sun_hours: str = ""
    refund_policy: str = ""
    booking_policy: str = ""
    payment_methods: str = ""
    welcome_message: str = ""
    fallback_message: str = ""


# Gemini LLM validation schemas
class LLMFAQItem(BaseModel):
    q: str
    alt_questions: List[str] = Field(default_factory=list)
    a: str
    button_label: str = ""


class LLMEnrichmentResult(BaseModel):
    new_faqs: List[LLMFAQItem] = Field(default_factory=list)
    faq_alt_questions: Dict[str, List[str]] = Field(default_factory=dict)


class LLMDocumentExtractResult(BaseModel):
    faqs: List[LLMFAQItem] = Field(default_factory=list)
    services: List[ServiceItem] = Field(default_factory=list)

# --- Google ADK Research Models ( arc.txt requirements ) ---

class Evidence(BaseModel):
    source_url: str
    source_type: str  # e.g., "official_website", "google_maps", "directory"
    text_segment: str # The exact quote from the source

class ResearchField(BaseModel):
    value: Optional[str] = None
    evidence: List[Evidence] = Field(default_factory=list)
    conflict: Optional[str] = None # Description of discrepancy between sources

class ResearchResult(BaseModel):
    name: ResearchField = Field(default_factory=ResearchField)
    industry: ResearchField = Field(default_factory=ResearchField)
    description: ResearchField = Field(default_factory=ResearchField)
    phone: ResearchField = Field(default_factory=ResearchField)
    email: ResearchField = Field(default_factory=ResearchField)
    address: ResearchField = Field(default_factory=ResearchField)
    website: ResearchField = Field(default_factory=ResearchField)
    mon_sat_hours: ResearchField = Field(default_factory=ResearchField)
    sun_hours: ResearchField = Field(default_factory=ResearchField)
    refund_policy: ResearchField = Field(default_factory=ResearchField)
    booking_policy: ResearchField = Field(default_factory=ResearchField)
    payment_methods: ResearchField = Field(default_factory=ResearchField)
    welcome_message: ResearchField = Field(default_factory=ResearchField)
    fallback_message: ResearchField = Field(default_factory=ResearchField)
    services: List[Dict[str, Any]] = Field(default_factory=list) # Each dict contains ResearchFields for name, price, details
    social_media: Dict[str, ResearchField] = Field(default_factory=dict) # instagram, facebook, etc.
    sources: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
