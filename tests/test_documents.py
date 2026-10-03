import pytest
from app.documents import validate_pdf_bytes, chunk_text_into_passages


def test_validate_pdf_bytes():
    valid_bytes = b"%PDF-1.7 header content"
    invalid_bytes = b"Hello world non pdf"

    validate_pdf_bytes(valid_bytes)

    with pytest.raises(ValueError) as exc_info:
        validate_pdf_bytes(invalid_bytes)
    assert "Invalid file format" in str(exc_info.value)


def test_chunk_text_into_passages():
    sample_text = """Heading 1: Dental Services Overview
We offer comprehensive dental care including teeth cleaning, whitening, root canals, and cosmetic surgery.
All procedures are performed by certified specialists using state-of-the-art medical equipment.

Heading 2: Payment and Insurance Policies
We accept all major credit cards, cash, and health insurance plans from Aetna, Cigna, and Blue Cross.
Flexible payment plans are available for major dental procedures upon request."""

    passages = chunk_text_into_passages(sample_text, target_size=200, overlap=50)
    assert len(passages) >= 2
    assert "Dental Services Overview" in passages[0] or "Dental Services Overview" in passages[1]
