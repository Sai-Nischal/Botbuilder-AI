import pytest
from app.models import BusinessConfig, ContactInfo, ServiceItem, PoliciesConfig
from app.faq_generator import generate_layer1_faqs


def test_layer1_faq_generation():
    cfg = BusinessConfig(
        business_id="sunrise-dental-a1b2",
        owner_id=1,
        name="Sunrise Dental Clinic",
        industry="healthcare",
        contact=ContactInfo(
            phone="+1 555-0192",
            email="info@sunrisedental.com",
            address="123 Main St",
            website="https://sunrisedental.com"
        ),
        hours={"mon-sat": "9:00-18:00", "sun": "closed"},
        services=[
            ServiceItem(name="Teeth cleaning", price="$80", details="Professional cleaning"),
            ServiceItem(name="Root canal", price="$500", details="")
        ],
        policies=PoliciesConfig(
            refund="Full refund 24h prior.",
            booking="Book online or phone."
        )
    )

    faqs = generate_layer1_faqs(cfg)
    assert len(faqs) >= 6

    # Verify Hours FAQ
    hours_faq = next((f for f in faqs if "hours" in f.q.lower()), None)
    assert hours_faq is not None
    assert "9:00-18:00" in hours_faq.a
    assert hours_faq.show_as_button is True

    # Verify Location FAQ
    loc_faq = next((f for f in faqs if "located" in f.q.lower()), None)
    assert loc_faq is not None
    assert "123 Main St" in loc_faq.a

    # Verify Services overview FAQ
    services_faq = next((f for f in faqs if "services do you offer" in f.q.lower()), None)
    assert services_faq is not None
    assert "Teeth cleaning" in services_faq.a
    assert "$80" in services_faq.a

    # Verify Individual Service FAQ
    teeth_faq = next((f for f in faqs if "Teeth cleaning" in f.q), None)
    assert teeth_faq is not None
    assert "$80" in teeth_faq.a

    # Verify Refund policy FAQ
    refund_faq = next((f for f in faqs if "refund" in f.q.lower()), None)
    assert refund_faq is not None
    assert "Full refund" in refund_faq.a
