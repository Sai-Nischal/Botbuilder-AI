import pytest
from app.models import FAQItem
from app.matcher import build_business_index, query_business_index


def test_matcher_vector_index(tmp_path):
    biz_id = "test-clinic-x1y2"
    faqs = [
        FAQItem(
            id=1,
            q="What are your opening hours?",
            alt_questions=["when do you open", "what time do you close", "when do u start the day"],
            a="We are open Mon-Sat, 9:00-18:00.",
            button_label="Opening hours",
            show_as_button=True
        ),
        FAQItem(
            id=2,
            q="Where are you located?",
            alt_questions=["what is your address", "how to get there"],
            a="123 Main St, New York.",
            button_label="Location",
            show_as_button=True
        )
    ]

    passages = [
        {"id": 101, "content": "Our clinic parking lot is located behind the building on 2nd Avenue."}
    ]

    # Build index
    build_business_index(biz_id, faqs, passages)

    # Query with exact rephrasing: "when do u start the day?"
    res1 = query_business_index(biz_id, "when do u start the day?")
    assert res1["best_faq"] is not None
    assert res1["best_faq"]["faq_id"] == 1
    assert res1["best_faq"]["score"] > 0.50

    # Query for passage fallback: "where can I park my car?"
    res2 = query_business_index(biz_id, "where can I park my car?")
    assert res2["best_passage"] is not None
    assert res2["best_passage"]["passage_id"] == 101
