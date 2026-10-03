import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import pypdf

from app.config import DOCS_DIR, GEMINI_API_KEY
from app.models import FAQItem, ServiceItem, LLMDocumentExtractResult

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_FILES_PER_BUSINESS = 5


def validate_pdf_bytes(file_bytes: bytes) -> None:
    """Validates file signature (%PDF-) and size."""
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File exceeds maximum allowed size of 10 MB.")
    
    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("Invalid file format. Only valid PDF files with %PDF header are allowed.")


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extracts text content from a PDF file using pypdf.
    Raises ValueError if no readable text is found (e.g. scanned PDF).
    """
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        extracted_pages = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            # Strip non-printable / control characters
            cleaned_txt = "".join(ch for ch in txt if ch.isprintable() or ch in "\n\t")
            if cleaned_txt.strip():
                extracted_pages.append(cleaned_txt.strip())

        full_text = "\n\n".join(extracted_pages).strip()
        if not full_text:
            raise ValueError("No readable text could be extracted from this PDF. Scanned or image-only PDFs are not supported.")
        
        return full_text
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document: {str(e)}")


def chunk_text_into_passages(text: str, target_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Splits document text into logical passages of approximately 400-600 characters
    with overlap, attempting to preserve sentence and heading structures.
    """
    if not text:
        return []

    # Clean multi-space / multi-newline
    cleaned_text = re.sub(r'\n{3,}', '\n\n', text)
    paragraphs = [p.strip() for p in cleaned_text.split('\n\n') if p.strip()]

    passages: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        # If single paragraph is longer than target_size, split by sentences
        if para_len > target_size:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                s_len = len(sentence)
                if current_len + s_len > target_size and current_chunk:
                    chunk_str = " ".join(current_chunk).strip()
                    if chunk_str:
                        passages.append(chunk_str)
                    # Maintain overlap from trailing sentences
                    overlap_len = 0
                    new_chunk = []
                    for s in reversed(current_chunk):
                        if overlap_len + len(s) <= overlap:
                            new_chunk.insert(0, s)
                            overlap_len += len(s)
                        else:
                            break
                    current_chunk = new_chunk
                    current_len = sum(len(s) for s in current_chunk)
                
                current_chunk.append(sentence)
                current_len += s_len
        else:
            if current_len + para_len > target_size and current_chunk:
                chunk_str = " ".join(current_chunk).strip()
                if chunk_str:
                    passages.append(chunk_str)
                # Overlap logic
                current_chunk = [current_chunk[-1]] if current_chunk else []
                current_len = sum(len(s) for s in current_chunk)

            current_chunk.append(para)
            current_len += para_len

    if current_chunk:
        chunk_str = " ".join(current_chunk).strip()
        if chunk_str:
            passages.append(chunk_str)

    return passages


def extract_draft_faqs_from_pdf_llm(document_text: str) -> Dict[str, Any]:
    """
    Uses Gemini LLM (if key provided) to extract candidate FAQs and services from PDF text.
    Returns dict with 'faqs' and 'services'.
    """
    if not GEMINI_API_KEY or not document_text:
        return {"faqs": [], "services": []}

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""Extract customer FAQs and services/prices from the following PDF document text.
Rule: Extract ONLY facts present in the text. Do NOT invent prices, rules, or details.

Document Text:
{document_text[:8000]}

Return ONLY valid JSON matching this schema:
{{
  "faqs": [
    {{
      "q": "Question text?",
      "alt_questions": ["alt q 1", "alt q 2"],
      "a": "Answer text based purely on the document.",
      "button_label": "Short label"
    }}
  ],
  "services": [
    {{
      "name": "Service Name",
      "price": "Price info",
      "details": "Details"
    }}
  ]
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        data = json.loads(raw_text.strip())
        return {
            "faqs": data.get("faqs", []),
            "services": data.get("services", [])
        }
    except Exception as e:
        print(f"LLM PDF FAQ extraction failed: {e}")
        return {"faqs": [], "services": []}
