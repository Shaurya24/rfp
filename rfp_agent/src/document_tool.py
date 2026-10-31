"""Document Tool: extract clean text from an uploaded PDF (deterministic, no LLM)."""
from __future__ import annotations

import io
import re

from pypdf import PdfReader

MAX_CHARS = 60_000          # keeps prompts bounded
MIN_USEFUL_CHARS = 200      # below this we assume a scanned / empty PDF


class DocumentError(Exception):
    """Raised when a PDF cannot be read or has no extractable text."""


def _clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(data: bytes, max_chars: int = MAX_CHARS) -> dict:
    """Return {text, pages, chars, truncated}. Raises DocumentError on failure."""
    if not data:
        raise DocumentError("File is empty.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise DocumentError("PDF is password-protected.")
        parts = []
        for i, page in enumerate(reader.pages, start=1):
            parts.append(f"[Page {i}]\n{page.extract_text() or ''}")
    except DocumentError:
        raise
    except Exception as exc:  # pypdf raises many exception types for corrupt files
        raise DocumentError(f"Could not read PDF: {exc}") from exc

    text = _clean("\n\n".join(parts))
    body_chars = len(re.sub(r"\[Page \d+\]", "", text).strip())
    if body_chars < MIN_USEFUL_CHARS:
        raise DocumentError(
            f"Only {body_chars} characters of text found (scanned/image-only PDF?). OCR is not supported."
        )
    truncated = len(text) > max_chars
    return {"text": text[:max_chars], "pages": len(reader.pages),
            "chars": min(len(text), max_chars), "truncated": truncated}
