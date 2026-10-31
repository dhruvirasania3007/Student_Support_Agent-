import base64
import hashlib
import html
import io
import re
import time
import uuid
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from tools.auth import register_student, login_student
from tools.student_tools import get_student_profile, create_support_request
from memory.store import get_memories, save_memory
from retrieval.policy import retrieve_policy
from database.db import init_db, get_connection

load_dotenv()
init_db()

# The agent uses OpenAI only when OPENAI_API_KEY is configured.
AGENT_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
if AGENT_AVAILABLE:
    from agent.agent import run_agent

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UniPilot — Your Campus Companion",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

MODEL = "claude-sonnet-5-5"

POLICIES = {
    "Attendance": "A minimum of 75% attendance per course is required to sit for end-semester exams. "
                  "Students with 65-74% may apply for condonation with a valid medical or official reason.",
    "Examinations": "Re-evaluation requests must be filed within 7 days of result declaration. "
                    "Supplementary exams are held once per semester, after the main exam cycle.",
    "Academic integrity": "Plagiarism or unfair means leads to a disciplinary review. "
                          "First offences may result in a zero for the component and a formal warning.",
    "Hostel & transport": "Hostel allotment is yearly and renewed through the student portal. "
                          "In-time is 10:00 PM for first-year students and 11:00 PM for others.",
    "Leave of absence": "Medical or personal leave must be applied for through the department office "
                        "before the absence, with supporting documents, wherever possible.",
}

IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif"
}

FILE_TYPES = ["pdf", "docx", "txt", "md", "csv"] + list(IMAGE_TYPES)

DOC_ICONS = {
    "pdf": "📕",
    "docx": "📘",
    "txt": "📄",
    "md": "📝",
    "csv": "📊"
}


# ─────────────────────────────────────────────────────────────
# AUTHENTICATION (SQLite database)
# ─────────────────────────────────────────────────────────────
for key, value in {
    "user": None,
    "chats": {},
    "current": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def new_chat():
    cid = uuid.uuid4().hex[:8]
    st.session_state.chats[cid] = {
        "title": "New chat",
        "messages": []
    }
    st.session_state.current = cid


# ─────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap');

:root {
    --ink: #1f1a3d; --muted: #7b7596; --violet: #6c4df6; --violet-deep: #4c2fd0;
    --pink: #ff5fa2; --bg: #f5f3ff; --line: #e7e2fb;
    --grad: linear-gradient(120deg, #6c4df6 0%, #9b5cf6 45%, #ff5fa2 100%);
}
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }

.stApp {
    background:
        radial-gradient(900px 400px at 100% -5%, rgba(255,95,162,.12), transparent 60%),
        radial-gradient(800px 400px at -5% 10%, rgba(108,77,246,.12), transparent 60%),
        var(--bg);
    color: var(--ink);
}
.block-container { max-width: 900px !important; margin: 0 auto; padding: 1.6rem 1.5rem 8rem !important; }

/* ═════ SIDEBAR ═════ */
[data-testid="stSidebar"] {
    background: linear-gradient(185deg, #2b1a73 0%, #1d1250 55%, #170e40 100%);
    border-right: none; min-width: 290px !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 1.6rem 1.1rem; }
[data-testid="stSidebar"] * { color: #e9e4ff; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }

.brand { font-family: 'Plus Jakarta Sans', sans-serif; font-size: 29px; font-weight: 800; letter-spacing: -1.4px; color: #fff !important; }
.brand span { background: linear-gradient(90deg, #ff9ccb, #b79bff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.brand-tag { font-size: 10px; letter-spacing: 2.2px; color: #a99be8 !important; margin-top: 4px; font-weight: 600; margin-bottom: 22px; }
.side-heading { font-size: 10px; color: #9486dc !important; font-weight: 700; letter-spacing: 1.9px; margin: 22px 0 8px 4px; }

[data-testid="stSidebar"] div.stButton > button {
    width: 100%; min-height: 40px; justify-content: flex-start;
    background: transparent; border: 1px solid transparent; border-radius: 12px;
    padding: 7px 13px; font-size: 13.5px; font-weight: 500; color: #d9d2ff; text-align: left;
    box-shadow: none; transform: none; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
[data-testid="stSidebar"] div.stButton > button:hover { background: rgba(255,255,255,.09); color: #fff; }
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
    background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.2); color: #fff; font-weight: 700;
}
[data-testid="stSidebar"] div.stButton > button.newchat, [data-testid="stSidebar"] .newchat-wrap div.stButton > button {
    background: var(--grad); color: #fff; border: none; font-weight: 700; min-height: 44px;
    box-shadow: 0 8px 20px rgba(255,95,162,.28); justify-content: center;
}

.profile-card {
    display: flex; gap: 12px; align-items: center;
    background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
    padding: 12px 14px; border-radius: 16px; margin-top: 18px;
}
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--grad); color: #fff !important; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.profile-name { font-weight: 700; font-size: 13.5px; color: #fff !important; line-height: 1.2; }
.profile-meta { font-size: 11px; color: #b7acee !important; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; }

/* ═════ LOGIN ═════ */
.login-hero { text-align: center; margin: 30px 0 22px; }
.login-hero .brand { font-size: 44px; color: var(--ink) !important; }
.login-hero .brand span { background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.login-hero p { color: var(--muted); font-size: 14.5px; margin-top: 8px; }
.demo-hint { text-align: center; font-size: 12px; color: var(--muted); margin-top: 14px; background: #ece7ff; border-radius: 12px; padding: 10px; }
[data-testid="stForm"] { background: #fff; border: 1px solid var(--line); border-radius: 22px; padding: 26px; box-shadow: 0 18px 44px rgba(108,77,246,.12); }
[data-testid="stForm"] div.stButton > button, [data-testid="stFormSubmitButton"] button {
    width: 100%; min-height: 46px; background: var(--grad); color: #fff; border: none; border-radius: 13px;
    font-weight: 700; box-shadow: 0 10px 22px rgba(255,95,162,.3);
}
[data-testid="stFormSubmitButton"] button:hover { color: #fff; filter: brightness(1.06); }
[data-testid="stTextInput"] input { border-radius: 12px; }

/* ═════ TOP BAR ═════ */
.topline { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.top-label { font-size: 12px; color: var(--muted); letter-spacing: 1.5px; font-weight: 700; }
.availability { background: #e3faf6; color: #0c8f80; border: 1px solid #bff0e8; padding: 6px 13px; border-radius: 30px; font-size: 11px; font-weight: 700; }

/* ═════ WELCOME ═════ */
.welcome { text-align: center; margin: 54px 0 30px; }
.welcome .spark {
    width: 64px; height: 64px; border-radius: 20px; background: var(--grad); color: #fff; font-size: 30px;
    display: inline-flex; align-items: center; justify-content: center; box-shadow: 0 18px 38px rgba(108,77,246,.35);
}
.welcome h1 { font-family: 'Plus Jakarta Sans', sans-serif; font-size: clamp(30px, 4vw, 44px); font-weight: 800; letter-spacing: -2px; color: var(--ink); margin: 20px 0 6px; line-height: 1.15; }
.welcome h1 span { background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.welcome p { color: var(--muted); font-size: 15px; }

[data-testid="stMain"] div.stButton > button {
    width: 100%; min-height: 84px; background: #fff; border: 1px solid var(--line); border-radius: 18px;
    color: var(--ink); text-align: left; justify-content: flex-start; align-items: flex-start;
    padding: 16px 18px; white-space: pre-wrap; font-size: 13.5px; line-height: 1.55;
    box-shadow: 0 8px 24px rgba(76,47,208,.06); transition: all .2s ease;
}
[data-testid="stMain"] div.stButton > button:hover {
    border-color: var(--violet); background: #faf8ff; color: var(--violet-deep);
    transform: translateY(-3px); box-shadow: 0 14px 30px rgba(108,77,246,.16);
}

/* ═════ CHAT BUBBLES ═════ */
.chat-wrap { display: flex; flex-direction: column; gap: 18px; margin: 10px 0 16px; }
.msg-row { display: flex; gap: 11px; align-items: flex-end; }
.msg-row.user { justify-content: flex-end; }
.av { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 13px; flex-shrink: 0; }
.av.bot { background: #fff; border: 1px solid var(--line); color: var(--violet); font-size: 17px; box-shadow: 0 4px 12px rgba(108,77,246,.12); }
.av.user { background: var(--grad); color: #fff; }
.bubble { max-width: 620px; padding: 14px 18px; font-size: 14.5px; line-height: 1.7; word-wrap: break-word; }
.bubble.user { background: var(--grad); color: #fff; border-radius: 20px 20px 4px 20px; box-shadow: 0 10px 24px rgba(108,77,246,.28); }
.bubble.bot { background: #fff; color: var(--ink); border: 1px solid var(--line); border-radius: 20px 20px 20px 4px; box-shadow: 0 8px 22px rgba(76,47,208,.07); }
.bubble b { font-weight: 700; }
.meta { font-size: 10.5px; color: #a8a2c0; margin: 5px 6px 0; letter-spacing: .3px; }
.meta.user { text-align: right; }
.chip { display: inline-block; font-size: 11px; font-weight: 700; padding: 4px 11px; border-radius: 20px; margin: 0 6px 8px 0; }
.chip-tool { background: #ece7ff; color: var(--violet-deep); }
.chip-doc { background: #dcf8f3; color: #0c8f80; }
.chip-file { background: rgba(255,255,255,.22); color: #fff; }
.snippet { background: #faf8ff; border-left: 3px solid var(--violet); padding: 9px 13px; border-radius: 0 10px 10px 0; margin-top: 9px; font-size: 13px; color: #5a5278; }
.att-img { display: block; max-width: 280px; max-height: 240px; border-radius: 14px; margin-bottom: 10px; border: 2px solid rgba(255,255,255,.35); }

div[data-testid="stChatInput"] { border: 1.5px solid #d4c9f7; border-radius: 22px; background: #fff; box-shadow: 0 12px 32px rgba(108,77,246,.14); }
.hint { text-align: center; color: #a8a2c0; font-size: 11.5px; margin-top: 8px; }

@media (max-width: 900px) { .block-container { padding: 1.2rem 1rem 7rem !important; } .bubble { max-width: 100%; } }
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────────────────────
def login_screen():
    st.markdown(
        '<div class="login-hero"><div class="brand">Uni<span>Pilot</span> ✦</div>'
        '<p>Your campus companion. Log in to continue.</p></div>',
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@college.edu")
                pw = st.text_input("Password", type="password", placeholder="••••••••")
                ok = st.form_submit_button("Log in")
            if ok:
                result = login_student(email, pw)
                if result["success"]:
                    st.session_state.user = result["student"]
                    new_chat()
                    st.rerun()
                else:
                    st.error(result["message"])
        with tab_signup:
            with st.form("signup_form"):
                name = st.text_input("Full name", placeholder="Your name")
                email2 = st.text_input("Email", placeholder="you@college.edu")
                programme = st.text_input(
                    "Programme",
                    placeholder="PGDM Big Data Analytics"
                )
                pw2 = st.text_input(
                    "Password",
                    type="password",
                    placeholder="At least 8 characters"
                )
                ok2 = st.form_submit_button("Create account")

            if ok2:
                result = register_student(
                    name,
                    email2,
                    programme,
                    pw2
                )

                if result["success"]:
                    st.success(result["message"])
                    st.info(
                        f"Your Student ID: {result['student_id']}. Please log in."
                    )
                else:
                    st.error(result["message"])


# ─────────────────────────────────────────────────────────────
# CHECK LOGIN
# ─────────────────────────────────────────────────────────────

if st.session_state.user is None:
    login_screen()
    st.stop()

USER = st.session_state.user

if st.session_state.current not in st.session_state.chats:
    new_chat()

CHAT = st.session_state.chats[st.session_state.current]


# ─────────────────────────────────────────────────────────────
# ATTACHMENT TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_text(ext: str, data: bytes) -> str:
    try:
        if ext in ("txt", "md", "csv"):
            return data.decode("utf-8", errors="ignore")

        if ext == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        if ext == "docx":
            from docx import Document

            document = Document(io.BytesIO(data))
            return "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
            )

    except Exception:
        return ""

    return ""


def make_attachment(uploaded_file) -> dict:
    data = uploaded_file.getvalue()
    ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if ext in IMAGE_TYPES:
        return {
            "name": uploaded_file.name,
            "ext": ext,
            "kind": "image",
            "mime": IMAGE_TYPES[ext],
            "b64": base64.b64encode(data).decode(),
            "text": ""
        }

    return {
        "name": uploaded_file.name,
        "ext": ext,
        "kind": "doc",
        "text": extract_text(ext, data)
    }


def chat_docs() -> list:
    return [
        attachment
        for message in CHAT["messages"]
        for attachment in message.get("attachments", [])
        if attachment["kind"] == "doc"
    ]


# ─────────────────────────────────────────────────────────────
# CACHED PDF SEARCH
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def cached_policy_search(query: str):
    return retrieve_policy(query, top_k=2)


# ─────────────────────────────────────────────────────────────
# LOCAL OLLAMA CONFIGURATION
# ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def ollama_chat(messages: list) -> str:
    """Call the locally running Ollama server without requiring an API key."""
    import json
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 350,
            "num_ctx": 4096,
        },
    }
    request = Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ConnectionError(
            "Cannot connect to Ollama at " + OLLAMA_BASE_URL +
            ". Make sure the Ollama app is running on this computer."
        ) from exc

    answer = ((result.get("message") or {}).get("content") or "").strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response.")
    return answer


# ─────────────────────────────────────────────────────────────
# PERSISTENT KNOWLEDGE BASE (PDFs stored beside this app)
# ─────────────────────────────────────────────────────────────

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent / "knowledge_base"


@st.cache_data(show_spinner=False, ttl=300)
def load_knowledge_base_docs() -> list:
    """Load bundled academic PDFs so they are available in every new chat."""
    documents = []
    if not KNOWLEDGE_BASE_DIR.exists():
        return documents

    for path in sorted(KNOWLEDGE_BASE_DIR.glob("*.pdf")):
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            page_texts = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    page_texts.append(f"[Page {page_number}]\\n{page_text}")
            text_content = "\\n\\n".join(page_texts)
            if text_content:
                documents.append({"name": path.name, "kind": "doc", "text": text_content})
        except Exception as exc:
            print(f"UniPilot: could not read knowledge-base file {path.name}: {exc}")
    return documents


# ─────────────────────────────────────────────────────────────
# DOCUMENT SEARCH
# ─────────────────────────────────────────────────────────────

STOP_WORDS = {
    "what", "when", "where", "which", "about",
    "does", "this", "that", "with", "from",
    "have", "tell", "please", "document",
    "documents", "file", "files", "uploaded",
    "there", "their", "give", "show"
}


def search_docs(query: str, docs: list, top_k: int = 4):
    """Find useful passages from files uploaded in the current chat."""
    words = {
        word for word in re.findall(r"[a-z0-9]+", query.lower())
        if len(word) > 2 and word not in STOP_WORDS
    }

    results = []
    for document in docs:
        full_text = (document.get("text") or "").strip()
        if not full_text:
            continue

        # Split long files into manageable overlapping passages.
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", full_text) if part.strip()]
        chunks = []
        for paragraph in paragraphs:
            if len(paragraph) <= 1100:
                chunks.append(paragraph)
            else:
                step = 900
                chunks.extend(paragraph[i:i + 1100] for i in range(0, len(paragraph), step))

        if not chunks:
            chunks = [full_text[:1100]]

        for chunk in chunks:
            lowered = chunk.lower()
            score = sum(2 if word in lowered else 0 for word in words)
            # A small relevance boost for exact phrase matches.
            if query and query.lower() in lowered:
                score += 5
            if score:
                results.append((score, document.get("name", "Uploaded file"), chunk[:1100]))

    results.sort(key=lambda item: item[0], reverse=True)
    return results[:top_k]


# ─────────────────────────────────────────────────────────────
# OLLAMA RESPONSE
# ─────────────────────────────────────────────────────────────

def ollama_reply(prompt: str, attachments: list) -> dict | None:
    """Generate a grounded local answer with Ollama; keep the existing UI contract."""
    question = (prompt or "").strip()
    lowered = question.lower()

    greetings = {
        "hi", "hii", "hello", "hey", "good morning",
        "good afternoon", "good evening", "how are you",
        "thank you", "thanks"
    }
    if lowered.strip(".!? ") in greetings and not attachments:
        if lowered.startswith("thank"):
            answer = "You're welcome! I'm here whenever you need help. 😊"
        elif lowered.startswith("how are"):
            answer = "I'm doing well! What can I help you with today? 😊"
        else:
            answer = "Hi! I'm UniPilot. How can I help you today? 😊"
        return {"tool": "", "content": answer, "sources": []}

    try:
        context_parts = []
        sources = []

        # Search chat uploads and the persistent academic knowledge base.
        attached_docs = chat_docs()
        knowledge_docs = load_knowledge_base_docs()
        # Permanent knowledge-base copies take priority. Ignore duplicate chat uploads
        # with the same filename so a PDF is not indexed/shown multiple times.
        knowledge_names = {doc.get("name", "").casefold() for doc in knowledge_docs}
        unique_attachments = []
        seen_names = set(knowledge_names)
        for doc in attached_docs:
            name = doc.get("name", "").casefold()
            if name and name not in seen_names:
                unique_attachments.append(doc)
                seen_names.add(name)
        all_docs = knowledge_docs + unique_attachments
        attachment_hits = search_docs(question, all_docs, top_k=4) if all_docs else []

        file_question = any(term in lowered for term in (
            "file", "document", "pdf", "attachment", "uploaded",
            "summarize", "summary", "explain this", "this document"
        ))
        if attached_docs and not attachment_hits and file_question:
            for doc in attached_docs[:2]:
                text_content = (doc.get("text") or "").strip()
                if text_content:
                    attachment_hits.append((1, doc.get("name", "Uploaded file"), text_content[:5000]))

        for _, filename, passage in attachment_hits:
            is_knowledge_base = any(doc.get("name") == filename for doc in knowledge_docs)
            source_type = "Academic knowledge-base document" if is_knowledge_base else "Chat attachment"
            context_parts.append(f"[{source_type}: {filename}]\\n{passage}")
            sources.append((filename, passage[:220]))

        # Use the legacy policy index only when the permanent PDFs returned no hits.
        # This avoids repeating the same handbook passages as duplicate sources.
        policy_terms = (
            "attendance", "exam", "examination", "re-evaluation", "reevaluation",
            "hostel", "fee", "scholarship", "course", "credit", "semester",
            "academic", "leave", "placement", "registration", "handbook",
            "university", "college", "aidtm", "timetable", "deadline", "sip"
        )
        if not attachment_hits and any(term in lowered for term in policy_terms):
            try:
                retrieval = cached_policy_search(question)
                if isinstance(retrieval, dict):
                    for chunk in retrieval.get("chunks", [])[:2]:
                        passage = (chunk.get("text") or "").strip()
                        if not passage:
                            continue
                        source = chunk.get("source", "Academic document")
                        page = chunk.get("page")
                        label = f"{source} — Page {page}" if page else source
                        context_parts.append(f"[Academic source: {label}]\n{passage}")
                        sources.append((label, passage[:220]))
            except Exception as retrieval_error:
                print(f"UniPilot: optional policy-index lookup failed: {retrieval_error}")

        context = "\n\n---\n\n".join(list(dict.fromkeys(context_parts))[:6])
        if not context:
            context = "No relevant uploaded or official document passage was found. Do not invent university-specific rules."

        history = []
        for message in CHAT["messages"][:-1][-10:]:
            role = "user" if message.get("role") == "user" else "assistant"
            content = (message.get("content") or "").strip()
            if content:
                history.append({"role": role, "content": content[:1200]})

        system_prompt = """You are UniPilot, a reliable and friendly university student support assistant.
Answer the student's actual question directly, naturally and in simple language.
Keep the default answer concise (about 3-6 sentences); expand only when the student asks for detail.
Use conversation history to understand follow-up questions and pronouns.
Use the academic knowledge-base passages and chat uploads as the primary evidence for
AIDTM/PGDM-specific questions. Answer from retrieved passages, not assumptions. Never invent
university policies, fees, deadlines, rules, subjects, credits, or dates. The UniPilot Student
Handbook is explicitly a DRAFT for demonstration: distinguish illustrative/sample guidance
from verified policy, and do not present sample rules as official. The Academic Plan is for
PGDM Big Data Analytics Batch 2025-27; do not apply it to another programme or batch unless
the source says so. If the documents do not confirm a detail, say it is not specified in the
available documents. For general questions, use general knowledge and make clear when it is
not document-derived. Avoid generic fallback answers."""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({
            "role": "user",
            "content": f"Relevant document context:\n{context}\n\nLatest student question:\n{question}"
        })

        # llama3.2:3b is a text model. Keep document uploads supported; explain image limitation.
        has_image = any(item.get("kind") == "image" for item in (attachments or []))
        answer = ollama_chat(messages)
        if has_image:
            answer += "\n\nNote: This local llama3.2:3b model supports text, not image understanding. Please describe the image or use a vision-capable model to analyse it."

        return {
            "tool": "",
            "content": answer,
            "sources": list(dict.fromkeys(sources))[:4]
        }

    except Exception as exc:
        error_text = str(exc)
        upper = error_text.upper()
        if "CANNOT CONNECT TO OLLAMA" in upper or "CONNECTION REFUSED" in upper:
            friendly = "Cannot connect to local Ollama. Please open the Ollama app and make sure its local service is running, then try again."
        elif "404" in upper or "MODEL" in upper and "NOT FOUND" in upper:
            friendly = f"The local model '{OLLAMA_MODEL}' was not found. In Command Prompt, run: ollama pull {OLLAMA_MODEL}"
        else:
            friendly = f"UniPilot could not get a response from Ollama. Technical detail: {error_text[:300]}"
        return {"tool": "", "content": friendly, "sources": []}


# ─────────────────────────────────────────────────────────────
# FALLBACK RESPONSE
# ─────────────────────────────────────────────────────────────

def rule_reply(prompt: str, attachments: list) -> dict:
    text = (prompt or "").strip()
    lowered = text.lower()
    docs = chat_docs()

    if docs:
        hits = search_docs(text, docs)

        if hits:
            return {
                "tool": "Chat attachment search",
                "sources": [
                    (name, passage[:220])
                    for _, name, passage in hits
                ],
                "content": (
                    "Here are the relevant passages I found "
                    "in your attached document:\n\n"
                    + "\n\n".join(
                        f"**{name}**\n{passage}"
                        for _, name, passage in hits
                    )
                )
            }

    if lowered in {"hi", "hello", "hey", "hii"}:
        return {
            "tool": "UniPilot",
            "sources": [],
            "content": f"Hello {USER['name'].split()[0]}! I'm UniPilot. How can I help you today?"
        }

    try:
        result = retrieve_policy(text, top_k=2)
        chunks = result.get("chunks", []) if isinstance(result, dict) else []

        answer_parts = []
        sources = []

        for item in chunks:
            passage = (item.get("text") or "").strip()

            if not passage:
                continue

            source = item.get("source", "Academic document")
            page = item.get("page")
            label = f"{source} — Page {page}" if page else source

            answer_parts.append(passage)
            sources.append((label, passage[:220]))

        if answer_parts:
            return {
                "tool": "Academic PDF Retrieval",
                "sources": sources[:3],
                "content": "\n\n".join(answer_parts)
            }

    except Exception:
        pass

    return {
        "tool": "UniPilot",
        "sources": [],
        "content": (
            "I couldn't find a relevant answer in the available documents. "
            "Please try another question or upload the relevant document."
        )
    }


# ─────────────────────────────────────────────────────────────
# MESSAGE DISPLAY
# ─────────────────────────────────────────────────────────────

def md_to_html(text: str) -> str:
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"`(.+?)`", r"<code>\1</code>", safe)

    lines = []

    for line in safe.split("\n"):
        line = re.sub(r"^#{1,6}\s*", "", line)

        if line.startswith(("- ", "* ")):
            line = "• " + line[2:]

        lines.append(line)

    return "<br>".join(lines)


def initials_of(name: str) -> str:
    return "".join(word[0] for word in name.split()[:2]).upper()


def attachments_html(attachments: list) -> str:
    output = ""

    for attachment in attachments:
        if attachment["kind"] == "image":
            output += (
                f'<img class="att-img" '
                f'src="data:{attachment["mime"]};base64,{attachment["b64"]}" '
                f'alt="{html.escape(attachment["name"])}">'
            )
        else:
            output += (
                f'<span class="chip chip-file">'
                f'{DOC_ICONS.get(attachment["ext"], "📄")} '
                f'{html.escape(attachment["name"])}'
                f'</span>'
            )

    return output


def bubble_html(message: dict) -> str:
    timestamp = message.get("ts", "")

    if message["role"] == "user":
        body = md_to_html(message["content"]) if message["content"] else ""

        return (
            f'<div class="msg-row user"><div>'
            f'<div class="bubble user">'
            f'{attachments_html(message.get("attachments", []))}'
            f'{body}</div>'
            f'<div class="meta user">You · {timestamp}</div>'
            f'</div>'
            f'<div class="av user">{initials_of(USER["name"])}</div>'
            f'</div>'
        )

    chips = ""

    for name, _ in message.get("sources", []):
        chips += (
            f'<span class="chip chip-doc">'
            f'📎 {html.escape(name)}</span>'
        )

    snippets = "".join(
        f'<div class="snippet">{html.escape(snippet)}…</div>'
        for _, snippet in message.get("sources", [])
    )

    return (
        f'<div class="msg-row bot">'
        f'<div class="av bot">✦</div>'
        f'<div><div class="bubble bot">'
        f'<div>{chips}</div>'
        f'{md_to_html(message["content"])}'
        f'{snippets}</div>'
        f'<div class="meta">UniPilot · {timestamp}</div>'
        f'</div></div>'
    )


# ─────────────────────────────────────────────────────────────
# SEND MESSAGE
# ─────────────────────────────────────────────────────────────

def send(text: str, files=None):
    attachments = [
        make_attachment(file)
        for file in (files or [])
    ]

    CHAT["messages"].append({
        "role": "user",
        "content": text,
        "attachments": attachments,
        "ts": datetime.now().strftime("%I:%M %p")
    })

    if CHAT["title"] == "New chat":
        base = text or (
            attachments[0]["name"] if attachments else "New chat"
        )
        CHAT["title"] = base[:32] + ("…" if len(base) > 32 else "")


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="brand">Uni<span>Pilot</span> ✦</div>'
        '<div class="brand-tag">YOUR CAMPUS COMPANION</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="newchat-wrap">', unsafe_allow_html=True)

    if st.button("＋  New chat", key="new_chat", use_container_width=True):
        new_chat()
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="side-heading">RECENT CHATS</div>',
        unsafe_allow_html=True
    )

    for cid, chat in reversed(list(st.session_state.chats.items())):
        if st.button(
            f"💬  {chat['title']}",
            key=f"chat_{cid}",
            use_container_width=True,
            type="primary" if cid == st.session_state.current else "secondary"
        ):
            st.session_state.current = cid
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown(
        f'<div class="profile-card">'
        f'<div class="avatar">{initials_of(USER["name"])}</div>'
        f'<div>'
        f'<div class="profile-name">{html.escape(USER["name"])}</div>'
        f'<div class="profile-meta">{html.escape(USER["email"])}</div>'
        f'</div></div>',
        unsafe_allow_html=True
    )

    if st.button("⎋  Log out", key="logout", use_container_width=True):
        st.session_state.user = None
        st.session_state.chats = {}
        st.session_state.current = None
        st.rerun()


# ─────────────────────────────────────────────────────────────
# MAIN CHAT
# ─────────────────────────────────────────────────────────────

st.markdown(
    '<div class="topline">'
    '<div class="top-label">UNIPILOT · CHAT</div>'
    '<div class="availability">● &nbsp; Ready</div>'
    '</div>',
    unsafe_allow_html=True
)

if not CHAT["messages"]:
    st.markdown(
        f'<div class="welcome">'
        f'<div class="spark">✦</div>'
        f'<h1>Hi {html.escape(USER["name"].split()[0])}, '
        f'<span>how can I help?</span></h1>'
        f'<p>Ask a question, or attach documents and photos '
        f'with the <b>+</b> button in the message box.</p>'
        f'</div>',
        unsafe_allow_html=True
    )

    suggestions = [
        ("📚  Attendance rules", "What is the attendance policy?"),
        ("📝  Exam re-evaluation", "How do I apply for exam re-evaluation?"),
        ("🏠  Hostel timings", "What are the hostel timings?"),
    ]

    columns = st.columns(3, gap="medium")

    for column, (label, prompt_text) in zip(columns, suggestions):
        with column:
            if st.button(
                f"{label}\n\n{prompt_text}",
                key=f"sg_{label}",
                use_container_width=True
            ):
                send(prompt_text)
                st.rerun()

else:
    st.markdown(
        '<div class="chat-wrap">'
        + "".join(
            bubble_html(message)
            for message in CHAT["messages"]
        )
        + "</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────
# GENERATE RESPONSE
# ─────────────────────────────────────────────────────────────

if CHAT["messages"] and CHAT["messages"][-1]["role"] == "user":
    last = CHAT["messages"][-1]

    with st.spinner("UniPilot is thinking…"):
        question = last["content"].strip() or (
            "Please review the attached file and summarize its content."
        )

        result = ollama_reply(
            question,
            last.get("attachments", [])
        )

        if result is None:
            result = rule_reply(
                last["content"],
                last.get("attachments", [])
            )

    CHAT["messages"].append({
        "role": "assistant",
        "content": result["content"],
        "tool": result.get("tool"),
        "sources": result.get("sources", []),
        "ts": datetime.now().strftime("%I:%M %p")
    })

    st.rerun()


# ─────────────────────────────────────────────────────────────
# CHAT INPUT
# ─────────────────────────────────────────────────────────────

entry = st.chat_input(
    "Message UniPilot…",
    accept_file="multiple",
    file_type=FILE_TYPES,
)

if entry:
    send(
        (entry.text or "").strip(),
        list(entry.files or [])
    )
    st.rerun()


st.markdown(
    '<div class="hint">'
    'UniPilot can make mistakes. Check important information.'
    '</div>',
    unsafe_allow_html=True
)      