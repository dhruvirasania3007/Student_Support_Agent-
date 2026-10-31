"""
UniPilot document retrieval
Reads the academic plan and student handbook PDFs from the project's data/ folder.

Expected project layout:
Student_Support_Agent/
    retrieval/policy.py
    data/academic_plan.pdf
    data/AIDTM_Student_Handbook.pdf

Install dependency if needed:
    pip install pypdf
"""

from pathlib import Path
import re
from typing import Dict, List, Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# These names are intentional: only these two documents are part of this
# retrieval collection. Add another filename here only when it is approved.
DOCUMENTS = [
    {
        "filename": "academic_plan.pdf",
        "title": "Academic Plan",
        "source_type": "source_document",
        "default_status": "SOURCE DOCUMENT — verify current version with AIDTM",
    },
    {
        "filename": "AIDTM_Student_Handbook.pdf",
        "title": "AIDTM Student Handbook (Draft for Demonstration)",
        "source_type": "handbook_draft",
        "default_status": "DRAFT HANDBOOK — some sections are illustrative, not official",
    },
]


def _clean_text(text: str) -> str:
    """Normalize PDF-extracted text without changing its meaning."""
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_illustrative(text: str, document_title: str) -> bool:
    """Mark handbook sample guidance so it is never mistaken for official policy."""
    if "handbook" not in document_title.lower():
        return False

    markers = (
        "illustrative sample",
        "not an official aidtm rule",
        "illustrative sample policy",
        "not an official",
    )
    return any(marker in (text or "").lower() for marker in markers)


def _split_page_into_chunks(page_text: str, max_chars: int = 1400) -> List[str]:
    """Split page text into readable paragraph chunks."""
    page_text = _clean_text(page_text)
    if not page_text:
        return []

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", page_text)
        if p.strip()
    ]

    chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:
        # PDF extraction sometimes returns one very long paragraph.
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), max_chars):
                piece = paragraph[start:start + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _load_documents() -> List[Dict[str, Any]]:
    """Read the configured PDFs and return page-level chunks with provenance."""
    if PdfReader is None:
        raise RuntimeError(
            "The pypdf package is not installed. Run: pip install pypdf"
        )

    documents: List[Dict[str, Any]] = []

    for config in DOCUMENTS:
        path = DATA_DIR / config["filename"]
        if not path.exists():
            continue

        try:
            reader = PdfReader(str(path))
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = _clean_text(page.extract_text() or "")
                for chunk_text in _split_page_into_chunks(page_text):
                    illustrative = _is_illustrative(
                        chunk_text, config["title"]
                    )
                    status = (
                        "ILLUSTRATIVE SAMPLE — NOT AN OFFICIAL AIDTM RULE"
                        if illustrative
                        else config["default_status"]
                    )
                    documents.append({
                        "text": chunk_text,
                        "page": page_number,
                        "source": config["title"],
                        "filename": config["filename"],
                        "status": status,
                        "illustrative": illustrative,
                    })
        except Exception as exc:
            # Keep other documents searchable if one PDF is damaged.
            documents.append({
                "text": f"Could not read {config['filename']}: {exc}",
                "page": 0,
                "source": config["title"],
                "filename": config["filename"],
                "status": "DOCUMENT READ ERROR",
                "illustrative": False,
                "error": True,
            })

    return documents


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _score(query_tokens: List[str], text: str) -> float:
    """Simple transparent keyword relevance score; no external model required."""
    words = _tokens(text)
    if not query_tokens or not words:
        return 0.0

    word_set = set(words)
    unique_query = set(query_tokens)
    overlap = len(unique_query & word_set)

    # Give a small boost when the exact phrase occurs in the chunk.
    query_phrase = " ".join(query_tokens)
    phrase_boost = 2.0 if query_phrase and query_phrase in text.lower() else 0.0

    # Normalize for chunk length so long pages do not always win.
    return (overlap / (len(unique_query) ** 0.5)) + phrase_boost


def retrieve_policy(query: str, top_k: int = 4) -> Dict[str, Any]:
    """
    Retrieve relevant chunks from both PDFs.

    Return structure remains compatible with app.py:
        {"success": bool, "chunks": [...], "message": str}
    Each chunk includes text, page, source, filename, status and illustrative.
    """
    query = (query or "").strip()
    if not query:
        return {
            "success": False,
            "chunks": [],
            "message": "Please enter a question so I can search the documents.",
        }

    try:
        all_chunks = _load_documents()
    except Exception as exc:
        return {
            "success": False,
            "chunks": [],
            "message": f"Document retrieval is unavailable: {exc}",
        }

    searchable = [c for c in all_chunks if not c.get("error")]
    if not searchable:
        missing = [
            item["filename"]
            for item in DOCUMENTS
            if not (DATA_DIR / item["filename"]).exists()
        ]
        if missing:
            message = (
                "I could not find these PDF files in the data folder: "
                + ", ".join(missing)
                + ". Please check their filenames and location."
            )
        else:
            message = (
                "The PDFs were found, but no readable text could be extracted."
            )
        return {"success": False, "chunks": [], "message": message}

    query_tokens = _tokens(query)
    ranked = []
    for chunk in searchable:
        score = _score(query_tokens, chunk["text"])
        if score > 0:
            result = dict(chunk)
            result["score"] = round(score, 4)
            ranked.append(result)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    selected = ranked[:max(1, int(top_k))]

    if not selected:
        return {
            "success": True,
            "chunks": [],
            "message": (
                "I could not find a relevant passage in the available "
                "academic plan or handbook. I should not guess an official rule."
            ),
        }

    return {
        "success": True,
        "chunks": selected,
        "message": f"Found {len(selected)} relevant passage(s).",
    }


# Compatibility alias for agent modules that use the more descriptive name.
def retrieve_academic_info(query: str, top_k: int = 4) -> Dict[str, Any]:
    return retrieve_policy(query, top_k=top_k)


def list_available_documents() -> List[str]:
    """Return the configured PDFs that currently exist in data/."""
    return [
        item["filename"]
        for item in DOCUMENTS
        if (DATA_DIR / item["filename"]).exists()
    ]
