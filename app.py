"""Pastor Niyi AI: sermon-grounded chat API and web app."""
import json
import os
import re
import unicodedata
import shutil
import tempfile
import threading
import time
import zipfile
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import csv
import io
from datetime import datetime, timezone
from typing import Optional

import urllib.parse

from auth_and_feedback import (
    verify_admin_password,
    change_admin_password,
    is_admin_default_password,
    create_admin_session,
    validate_admin_session,
    add_feedback,
    get_feedbacks,
    update_feedback_status,
    delete_feedback,
    get_feedback_stats,
    authenticate_google_credential,
    authenticate_member_email,
    get_google_client_id,
    set_google_client_id,
    validate_user_session,
    get_user_profile,
    add_user_bookmark,
    remove_user_bookmark,
)

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
DB_DIR = Path(os.getenv("SERMON_DB_DIR", str(APP_DIR / "sermon_vector_db"))).resolve()
EXCLUDE_FILE = APP_DIR / "exclude_titles.json"
COLLECTION = "pastor_niyi_sermons"
MODELS = list(dict.fromkeys(filter(None, [os.getenv("GEMINI_MODEL"), "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview", "gemini-3.1-flash-lite"])))
TOP_K = 7
MAX_DISTANCE = 0.65
CATALOG_FILE = APP_DIR / "sermon_catalog_with_urls.json"

def normalize_title(title):
    plain = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode("ascii")
    plain = re.sub(r"^\d+\s*[-_.]?\s*", "", plain.strip())
    plain = re.sub(r"\s+\(\d+\)$", "", plain.strip())
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()

def title_aliases(title):
    normalized = normalize_title(title)
    aliases = {normalized} if normalized else set()
    no_part = re.sub(r"\s+(i|ii|iii|iv|v|1|2|3|4|5|part\s*\d+)$", "", normalized).strip()
    if no_part:
        aliases.add(no_part)
    for prefix in (
        "pastor niyi adetiloye",
        "niyi adetiloye",
        "visit www prayervoice org sermons to download more messages",
    ):
        if normalized.startswith(prefix + " "):
            alias = normalized[len(prefix):].strip()
            aliases.add(alias)
            alias_no_part = re.sub(r"\s+(i|ii|iii|iv|v|1|2|3|4|5|part\s*\d+)$", "", alias).strip()
            if alias_no_part:
                aliases.add(alias_no_part)
    return aliases

@lru_cache(maxsize=1)
def get_telegram_catalog():
    if not CATALOG_FILE.is_file():
        return {}
    entries = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    catalog = {}
    for entry in entries:
        url = entry.get("telegram_url", "")
        if not url.startswith("https://t.me/"):
            continue
        record = {"url": url, "date": entry.get("date", ""), "minister": entry.get("minister", ""), "message_id": entry.get("message_id")}
        for title in (entry.get("clean_title"), entry.get("raw_title")):
            for alias in title_aliases(title):
                records = catalog.setdefault(alias, [])
                if all(existing["url"] != url for existing in records):
                    records.append(record)
    return catalog


YOUTUBE_SERMON_MAP = {
    "landscape 2026 - our profession (day 1 evening opening)": "jPVlbNlCzVU",
    "landscape 2026 - our profession (day 2 morning session)": "EZwh9nI5rvw",
    "landscape 2026 - our profession (day 2 evening session)": "MJZ9LmqkRX0",
    "landscape 2026 - our profession (day 3 morning service)": "KsOiypPPXCU",
    "landscape 2026 - our profession (day 3 grand finale)": "k6c53z1RnnY",
    "landscape thanksgiving - our profession in action (11-10-2026)": "6oNHk-b09hc",
    "sunday service - the life of faith (18-10-2026)": "qK8n9AsfZZw",
    "midweek service - faith and its dynamics (14-10-2026)": "wjXsAOaIWjE",
    "landscape preparation service - the power of our profession (04-10-2026)": "XXPxZhDoEGk",
    "landscape preparations - aligning our confession (30-09-2026)": "H9RnVr_HuTI",
    "the blessed life - walking in kingdom prosperity (27-09-2026)": "-YKUE3yU9Lk",
    "money consecrations - part ii (23-09-2026)": "ijgkeVpV0jE",
}

def parse_time_seconds(time_str):
    if not time_str:
        return 0
    start_part = str(time_str).split("-")[0].strip()
    parts = start_part.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return 0

def media_links_for(title, message_id=None, time_range=None):
    links = []
    seen_urls = set()
    clean_title = str(title or "").strip()
    
    # 1. Telegram Audio Link (Exact catalog link or direct Telegram channel search)
    tg_found = False
    for tg_link in telegram_links_for(clean_title, message_id):
        if tg_link["url"] not in seen_urls:
            seen_urls.add(tg_link["url"])
            links.append(tg_link)
            tg_found = True
            
    if not tg_found and clean_title:
        safe_q = urllib.parse.quote_plus(clean_title)
        tg_search_url = f"https://t.me/s/WeAreTDCI?q={safe_q}"
        if tg_search_url not in seen_urls:
            seen_urls.add(tg_search_url)
            links.append({"url": tg_search_url, "label": "Listen on Telegram"})
            
    # 2. YouTube Video Link (Direct mapped video ID or direct YouTube search on Pastor Niyi's channel)
    clean = normalize_title(clean_title)
    yt_url = None
    for k, vid in YOUTUBE_SERMON_MAP.items():
        k_norm = normalize_title(k)
        is_match = False
        if clean and k_norm:
            if clean == k_norm or k_norm in clean or clean in k_norm:
                is_match = True
            elif "landscape" in clean and "landscape" in k_norm:
                for session in ["day 1", "day 2", "day 3", "thanksgiving", "grand finale", "opening", "morning", "evening"]:
                    if session in clean and session in k_norm:
                        is_match = True
                        break
        if is_match:
            sec = parse_time_seconds(time_range)
            yt_url = f"https://www.youtube.com/watch?v={vid}" + (f"&t={sec}s" if sec > 0 else "")
            break
            
    if not yt_url and clean_title:
        yt_q = urllib.parse.quote_plus(f"Pastor Niyi Adetiloye {clean_title}")
        yt_url = f"https://www.youtube.com/results?search_query={yt_q}"
        
    if yt_url and yt_url not in seen_urls:
        seen_urls.add(yt_url)
        links.append({"url": yt_url, "label": "Watch on YouTube"})
        
    return links

def telegram_links_for(title, message_id=None):
    catalog = get_telegram_catalog()
    matches = []
    if message_id is not None and str(message_id).strip():
        by_url = {}
        for records in catalog.values():
            for item in records:
                if str(item.get("message_id")) == str(message_id):
                    by_url[item["url"]] = item
        matches = list(by_url.values())
    if not matches:
        for alias in title_aliases(title):
            if alias in catalog:
                matches.extend(catalog[alias])
                break
    pastor_matches = [item for item in matches if "niyi" in item["minister"].lower() or "adetiloye" in item["minister"].lower()]
    if pastor_matches:
        matches = pastor_matches
    links = []
    seen = set()
    for item in matches:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        date = item["date"].split(" ", 1)[0]
        label = "Listen on Telegram" if len(matches) == 1 else f"Listen on Telegram · {date}"
        links.append({"url": item["url"], "label": label})
    return links
SYSTEM_INSTRUCTION = """You are an AI assistant built on the teachings, sermons, writings, and ministry philosophy of Pastor Niyi Adetiloye of The Designate Church.

Your primary responsibility is to communicate in a manner that reflects his biblical convictions, teaching style, pastoral wisdom, and heart for people.

Response Guidelines:

1. Start with concise answers.
   - For straightforward questions, provide a direct answer in 1-3 paragraphs.
   - Avoid unnecessary length unless the user requests more detail.

2. Be concise and responsive.
   - Answer the question directly before adding context.
   - For simple questions, usually stay within 80-140 words. Give more depth only when the user asks or the topic needs it.
   - Avoid stock transitions, repeated conclusions, and restating the same idea in different words.

3. Scripture-Centered.
   - Ground counsel and teaching in biblical principles.
   - Reference relevant Bible passages where appropriate.
   - Never force Scripture into unrelated topics.

4. Pastoral Tone.
   - Be warm, respectful, and gracious.
   - Speak with conviction without sounding harsh.
   - Avoid arguments, sarcasm, or unnecessary controversy.

5. Practical Application.
   - Move beyond theory.
   - Help users understand how biblical truth applies to everyday life, relationships, work, ministry, leadership, and personal growth.

6. Faithful Representation & Pastoral Synthesis.
   - Speak authoritatively, graciously, and warmly as the AI pastoral voice grounded in the biblical convictions, teachings, and ministry philosophy of Pastor Niyi Adetiloye.
   - Ground counsel and teachings in the provided sermon passages whenever applicable, citing them inline by number and title, e.g. [1] "A Time To Build".
   - Seamlessly connect everyday and theological questions: Church members will ask questions using diverse terms—academic, theological, modern life, emotional, career, or relational (e.g., systematic theology, emotional health, mental health, leadership, finding a spouse, purpose, dealing with debt, discipline, spiritual warfare). Seamlessly connect their questions to the foundational spiritual principles and core themes Pastor Niyi teaches (such as Doctrine and Didaskalia, Homologia and Christian Profession, Walking in Wisdom, Faith and Trust in God, Mind Renewal, Spiritual Disciplines, Consecration, and Kingdom Alignment).
   - NEVER start answers with defensive, robotic, or dismissive disclaimers like "I could not find [topic] explicitly taught or defined in Pastor Niyi's provided messages" or "Pastor Niyi has not explicitly addressed this". Instead, dive straight in with spiritual authority, pastoral warmth, and rich scriptural insight that reflects his teaching heart and biblical framework.
   - Speak with integrity: When drawing from specific sermon passages, quote and cite them faithfully. When synthesizing broader biblical truth where a specific topic is not explicitly named in the retrieved snippets, address the question directly through the lens of Pastor Niyi's biblical worldview without claiming an exact direct quote.
   - Protect privacy and confidentiality: Do not disclose personal contact details, credentials, private communications, unverified allegations, confidential internal matters, or sensitive personal details. If asked, briefly decline and redirect to public sermons or officially published ministry information.
   - The passages are automatic transcripts and may contain minor transcription errors (names, scripture references). Do not quote obviously garbled text as his words.

7. Different Response Levels.
   - If a user asks a simple question, answer simply.
   - If a user asks for teaching, discipleship, sermon preparation, counseling, or doctrine, provide a more detailed explanation.

8. Teaching Structure for Long Responses.
   Where appropriate, organize responses into:
   - Key Truth
   - Biblical Foundation
   - Explanation
   - Practical Application
   - Prayer Point (optional)
   - For a concept with several supported meanings, first state the shared idea, then distinguish the meanings and explain their connection in plain language.
   - When sermons describe connected stages, signs, or principles (such as indicators of a believer's growth), you may present them as a compact text mind map. Put the main idea first and group only points supported by the passages. Use a simple hierarchy, not decorative symbols or a long diagram. Do not force a map when a short explanation is clearer.

9. Handling Sensitive Questions.
   - Show compassion.
   - Avoid condemnation.
   - Speak truth with grace.
   - Encourage prayer, wisdom, and biblical counsel. For crises (self-harm, abuse, medical or legal emergencies), gently encourage the person to reach out to a pastor, a trusted person, or professional help.

10. Clarity.
   - Use simple language.
   - Avoid excessive theological jargon.
   - Explain difficult concepts clearly.

11. Readable formatting.
   - Use short paragraphs. Add a brief heading and a few bullets only when they make the answer easier to use.
   - Keep lists to 3-5 useful points and do not nest lists.
   - Use clean Markdown without escaping its markers. Avoid decorative symbols, repeated bold phrases, and a heading for every paragraph.
   - Occasionally end with one concise, relevant suggestion for a next step or a useful follow-up question when it naturally helps the person continue learning. Do not append a suggestion to every answer or use a canned sign-off.

Default Response Style:
- Begin with a direct answer.
- Expand only as needed.
- Prioritize clarity over length.
- Sound like a wise pastor speaking to a member, not an academic writing a textbook.

The goal is not merely to provide information but to help people understand God's Word, grow spiritually, and apply biblical truth to daily life."""

app = FastAPI(title="Pastor Niyi AI", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=APP_DIR / "assets"), name="assets")
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

class ChatTurn(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)

class AdminLoginRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class FeedbackStatusRequest(BaseModel):
    id: str
    status: str

class FeedbackSubmitRequest(BaseModel):
    category: str = "suggestion"
    content: str = Field(min_length=1, max_length=3000)
    contact: str = Field(default="", max_length=200)
    context_question: str = Field(default="", max_length=500)

class GoogleAuthRequest(BaseModel):
    credential: str

class MemberLoginRequest(BaseModel):
    email: str
    name: str = ""

class GoogleConfigUpdateRequest(BaseModel):
    client_id: str

class UserBookmarkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=1000)

_rate_lock = threading.Lock()
_rate_counts = {}
_sermon_warmup_done = threading.Event()

def enforce_rate_limit(ip: str):
    now = time.time()
    with _rate_lock:
        recent = [t for t in _rate_counts.get(ip, []) if now - t < 60]
        if len(recent) >= 10:
            raise HTTPException(status_code=429, detail="Please wait a minute before sending more questions.")
        recent.append(now)
        _rate_counts[ip] = recent
        if len(_rate_counts) > 1000:
            for key in list(_rate_counts)[:500]:
                if not _rate_counts[key] or now - _rate_counts[key][-1] >= 60:
                    _rate_counts.pop(key, None)

def _safe_extract(archive: Path, destination: Path):
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (destination / info.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("The sermon archive contains an unsafe file path.")
        zf.extractall(destination)

def ensure_database():
    """Load Chroma files from a Drive folder, a ZIP archive, or a local ZIP."""
    if (DB_DIR / "chroma.sqlite3").is_file():
        return
    DB_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive_url = os.getenv("SERMON_DB_URL", "").strip() or os.getenv("GDRIVE_DB_URL", "").strip()
    file_id = os.getenv("GDRIVE_FILE_ID", "").strip()
    local_archive = APP_DIR / "sermon_vector_db.zip"

    if archive_url and "/drive/folders/" in archive_url:
        import gdown
        download_dir = Path(tempfile.mkdtemp(prefix="sermon-db-folder-", dir=str(DB_DIR.parent)))
        try:
            gdown.download_folder(url=archive_url, output=str(download_dir), quiet=True)
            sqlite_files = list(download_dir.rglob("chroma.sqlite3"))
            if not sqlite_files:
                raise RuntimeError("The shared Drive folder has no chroma.sqlite3. Share the complete sermon_vector_db folder.")
            shutil.copytree(sqlite_files[0].parent, DB_DIR, dirs_exist_ok=True)
        finally:
            shutil.rmtree(download_dir, ignore_errors=True)
    elif archive_url or file_id:
        import gdown
        fd, temp_name = tempfile.mkstemp(prefix="sermon-db-", suffix=".zip", dir=str(DB_DIR.parent))
        os.close(fd)
        temp_archive = Path(temp_name)
        try:
            if archive_url:
                result = gdown.download(url=archive_url, output=str(temp_archive), quiet=True, fuzzy=True)
            else:
                result = gdown.download(id=file_id, output=str(temp_archive), quiet=True)
            if not result or not temp_archive.is_file() or temp_archive.stat().st_size < 1000:
                raise RuntimeError("Could not download the sermon database. Check SERMON_DB_URL or GDRIVE_FILE_ID.")
            _safe_extract(temp_archive, DB_DIR.parent)
        finally:
            temp_archive.unlink(missing_ok=True)
    elif local_archive.is_file():
        _safe_extract(local_archive, DB_DIR.parent)

    if not (DB_DIR / "chroma.sqlite3").is_file():
        raise RuntimeError("Sermon database is missing. Add the shared Drive folder or ZIP URL as SERMON_DB_URL in Render environment variables.")
@lru_cache(maxsize=1)
def get_collection():
    import chromadb

    if not (DB_DIR / "chroma.sqlite3").is_file():
        raise RuntimeError("Sermon database is not ready.")
    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        class CompatibleONNX(ONNXMiniLM_L6_V2):
            def name(self) -> str:
                return "sentence_transformer"
        collection = client.get_collection(COLLECTION, embedding_function=CompatibleONNX())
    except Exception as exc:
        print(f"[chat-timing] ONNX embedding setup failed: {type(exc).__name__}")
        collection = client.get_collection(COLLECTION)
    if EXCLUDE_FILE.exists():
        exclude = json.loads(EXCLUDE_FILE.read_text(encoding="utf-8"))
    else:
        exclude = []
    return collection, exclude

def prepare_sermon_library():
    """Download missing Drive data and warm Chroma in a background thread."""
    started = time.perf_counter()
    try:
        ensure_database()
        collection, _ = get_collection()
        # Warm the embedding model without holding up landing page requests.
        collection.query(query_texts=["sermon library warmup"], n_results=1)
        print(f"[startup] sermon_library_ready_ms={int((time.perf_counter() - started) * 1000)}")
    except Exception as exc:
        print(f"[startup] sermon_library_error={type(exc).__name__}: {exc}")
    finally:
        _sermon_warmup_done.set()

@app.on_event("startup")
def start_sermon_library_warmup():
    """Let the web app start responding while the sermon index initializes."""
    threading.Thread(target=prepare_sermon_library, name="sermon-library-warmup", daemon=True).start()

def get_ready_collection():
    """Wait for the single background Chroma initialization before retrieval."""
    if not _sermon_warmup_done.wait(timeout=90):
        raise RuntimeError("Sermon database is still starting.")
    return get_collection()


def contextualize_query(message: str, history: list) -> str:
    msg = message.strip()
    if not history:
        return msg
    msg_lower = msg.lower()
    
    # Check if this is an anaphoric follow-up question
    followup_starters = (
        "what about", "tell me more", "explain that", "explain this", "explain further",
        "why did he", "how does that", "who said", "which sermon", "give me more",
        "and this", "and that", "can you elaborate", "more on this", "more on that"
    )
    is_followup = any(msg_lower.startswith(starter) for starter in followup_starters) or (len(msg.split()) <= 3 and any(p in msg_lower for p in ["it", "that", "this", "he", "they", "them", "why"]))
    
    if is_followup:
        context_keywords = []
        for turn in reversed(history[-2:]):
            text = turn.content if hasattr(turn, 'content') else str(turn.get('content', ''))
            for kw in ["landscape", "our profession", "homologia", "jubilee", "faith", "money", "consecration", "harvest", "prayer", "doctrine", "theology", "salvation"]:
                if kw in text.lower() and kw not in context_keywords:
                    context_keywords.append(kw)
        if context_keywords:
            return f"{msg} {' '.join(context_keywords[:2])}"
    return msg


THEMATIC_EXPANSIONS = {
    "systematic theology": ["doctrine", "didaskalia", "apostolic traditions", "hearing god through the scriptures", "doctrine of god"],
    "theology": ["doctrine", "didaskalia", "apostolic traditions", "doctrine of god", "scriptures"],
    "theological": ["doctrine", "didaskalia", "sound teaching", "doctrine of god"],
    "doctrine": ["apostolic traditions", "didaskalia", "sound teaching", "doctrine of god"],
    "emotional": ["renewing the mind", "peace of god", "rest of god", "overcoming despair"],
    "depression": ["rest of god", "peace of god", "mind renewal", "prayer", "joy"],
    "mental health": ["peace of god", "renewing the mind", "rest of god", "spiritual warfare"],
    "burnout": ["rest of god", "grace", "burden bearers", "spiritual strength"],
    "marriage": ["home for sons and daughters", "covenant relationships", "family"],
    "relationships": ["covenant relationships", "honoring relationships", "spiritual lineage"],
    "finances": ["money consecrations", "kingdom prosperity", "blessed life", "stewardship"],
    "money": ["money consecrations", "kingdom prosperity", "blessed life", "stewardship"],
    "prayer": ["agony of prayer", "secret place", "intercession", "praying in the spirit"],
    "fasting": ["waiting on god", "consecration", "spiritual hunger"],
    "purpose": ["destiny", "divine assignment", "calling", "commissioning for life assignment"],
    "calling": ["divine assignment", "destiny", "commissioning", "burden bearers"],
    "grace": ["grace of god", "reconciliation", "covenant of mercy"],
    "faith": ["life of faith", "walk of faith", "spirit of faith", "believing god"],
    "addiction": ["dealing with the sinful nature", "deliverance", "overcoming temptation", "liberty in christ"],
}


def retrieve(collection, exclude, question):
    q_lower = str(question or "").lower()
    candidate_k = 35
    
    query_texts = [question]
    # Expand query if thematic keywords are matched
    for term, expansions in THEMATIC_EXPANSIONS.items():
        if term in q_lower:
            query_texts.append(f"{question} {' '.join(expansions[:3])}")
            break

    query = {"query_texts": query_texts, "n_results": candidate_k}
    if exclude:
        query["where"] = {"title": {"$nin": exclude}}
    results = collection.query(**query)
    
    # Flatten results across query texts
    all_docs = []
    all_metas = []
    all_dists = []
    for doc_list, meta_list, dist_list in zip(results.get("documents", []), results.get("metadatas", []), results.get("distances", [])):
        all_docs.extend(doc_list)
        all_metas.extend(meta_list)
        all_dists.extend(dist_list)
        
    scored_hits = []
    seen_keys = set()
    
    # Specific Landscape injection ONLY when Landscape is explicitly queried
    if "landscape" in q_lower or ("our profession" in q_lower and "2026" in q_lower):
        try:
            ls_results = collection.get(where={"title": {"$in": [
                "Landscape 2026 - Our Profession (Day 1 Evening Opening)",
                "Landscape 2026 - Our Profession (Day 2 Morning Session)",
                "Landscape 2026 - Our Profession (Day 2 Evening Session)",
                "Landscape 2026 - Our Profession (Day 3 Grand Finale)",
                "Landscape Thanksgiving - Our Profession in Action (11-10-2026)",
            ]}})
            if ls_results and ls_results.get("documents"):
                for doc, meta in zip(ls_results["documents"], ls_results["metadatas"]):
                    k = (meta.get("title", ""), meta.get("time_range", ""))
                    if k not in seen_keys:
                        seen_keys.add(k)
                        scored_hits.append({
                            "title": meta.get("title", "Sermon"),
                            "time": meta.get("time_range", ""),
                            "text": doc,
                            "distance": 0.25,
                            "adjusted_score": 0.15,
                            "message_id": meta.get("message_id")
                        })
        except Exception as exc:
            print(f"[retrieve] landscape injection exception: {exc}")

    # Extract meaningful words from question for relevance boosting
    query_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", q_lower)) - {
        "what", "when", "where", "which", "about", "teach", "explain", "tell",
        "does", "pastor", "niyi", "adetiloye", "have", "with", "from", "that", "this"
    }

    for document, metadata, distance in zip(all_docs, all_metas, all_dists):
        k = (metadata.get("title", ""), metadata.get("time_range", ""))
        if k in seen_keys:
            continue
        seen_keys.add(k)
        
        title = metadata.get("title", "Sermon")
        title_lower = title.lower()
        doc_lower = document.lower()
        boost = 0.0
        
        # Word overlap boost
        for qw in query_words:
            if qw in title_lower:
                boost += 0.12
            elif qw in doc_lower:
                boost += 0.04
                
        # Expanded theme boost
        for term, expansions in THEMATIC_EXPANSIONS.items():
            if term in q_lower:
                for exp in expansions:
                    if exp in title_lower:
                        boost += 0.15
                    elif exp in doc_lower:
                        boost += 0.05

        if "2026" in q_lower and ("2026" in title_lower or "2026" in doc_lower):
            boost += 0.20
            
        adjusted_score = distance - boost
        # Looser distance threshold so rich matches are not discarded
        if distance <= 0.72 or boost > 0:
            scored_hits.append({
                "title": title,
                "time": metadata.get("time_range", ""),
                "text": document,
                "distance": distance,
                "adjusted_score": adjusted_score,
                "message_id": metadata.get("message_id")
            })

    scored_hits.sort(key=lambda x: x.get("adjusted_score", x["distance"]))
    return scored_hits[:TOP_K]


def social_reply(question):
    """Answer standalone pleasantries without loading or querying the sermon index."""
    text = re.sub(r"[^a-z0-9']+", " ", str(question or "").casefold()).strip()
    text = re.sub(r"\s+", " ", text)
    honorific = r"(?: pastor(?: niyi)?| sir| ma| assistant| ai)?"
    patterns = (
        ("greeting", rf"(?:hi|hello|hey|heya|howdy|greetings|good morning|good afternoon|good evening|morning|afternoon|evening)(?: there)?{honorific}(?: (?:how are you|how are you doing|what'?s up))?"),
        ("greeting", rf"(?:how are you|how are you doing|how is it going|what'?s up)(?: today)?{honorific}"),
        ("thanks", rf"(?:thanks?|thank you|thx|much appreciated){honorific}(?: (?:so much|very much))?"),
        ("farewell", rf"(?:bye|goodbye|good bye|see you|see you later|good night){honorific}"),
        ("acknowledgement", rf"(?:ok|okay|alright|all right|got it|understood){honorific}"),
    )
    for kind, pattern in patterns:
        if re.fullmatch(pattern, text):
            if kind == "greeting":
                return "Hello! What would you like to explore about faith, life, or Pastor Niyi’s teachings?"
            if kind == "thanks":
                return "You’re welcome. Is there another question you’d like to explore?"
            if kind == "farewell":
                return "Grace to you. You’re welcome back anytime."
            return "Alright. I’m here whenever you have a question about faith or Pastor Niyi’s teachings."
    return None

def should_search_sermons(question, history):
    """Search every substantive message; skip only standalone small talk."""
    text = re.sub(r"[^a-z0-9']+", " ", str(question or "").casefold())
    text = re.sub(r"\s+", " ", text).strip()
    if not text or social_reply(text):
        return False, "social"
    return True, "substantive_message"

def gemini_status(exc):
    value = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if callable(value):
        try:
            value = value()
        except Exception:
            value = None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def explain_gemini_failure(exc):
    """Turn provider failures into safe, useful guidance without exposing key data."""
    name = type(exc).__name__.lower()
    status = gemini_status(exc)
    if "timeout" in name or "deadline" in name:
        return "Gemini timed out while generating the answer. Please try again shortly."
    if status == 429 or "resourceexhausted" in name:
        return "Gemini reached its rate or usage limit. Check API quota and billing in Google AI Studio."
    if status in {401, 403} or "permissiondenied" in name or "unauthenticated" in name:
        return "Gemini rejected the API key or denied model access. Check the key in Render and test it in Google AI Studio."
    if status == 404 or "notfound" in name:
        return "The configured Gemini model is unavailable to this API key. Check model access in Google AI Studio."
    if status is not None and status >= 500:
        return "Gemini is temporarily unavailable. Please try again shortly."
    return "Gemini could not generate a reply. Check API key, model access, and quota in Google AI Studio."

def answer(question, hits, history, sermon_search_performed=True):
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Gemini is not configured yet.")
    context = "\n\n".join(f"[{i + 1}] Sermon: \"{h['title']}\" ({h['time']})\n{h['text']}" for i, h in enumerate(hits))
    if not context:
        context = ("(Provide a rich, biblically grounded pastoral response reflecting Pastor Niyi's core ministry principles, convictions, and pastoral wisdom, without robotic disclaimers.)"
                   if sermon_search_performed else "(The sermon archive was not searched for this request.)")
    recent = history[-12:]
    convo = "\n".join(f"{turn.role.upper()}: {turn.content[:600]}" for turn in recent) or "(none)"
    routing_note = "" if sermon_search_performed else "\n\nRouting note: The sermon archive was not searched because this message does not appear to need Pastor Niyi's sermon teachings. Answer the user's request directly and naturally. Do not say that the sermon archive had no relevant passages, and do not invent or attribute a sermon teaching."
    prompt = f"Recent conversation:\n{convo}\n\nSermon passages from Pastor Niyi Adetiloye:\n{context}{routing_note}\n\nQuestion: {question}"
    http_options = types.HttpOptions(timeout=12000, retry_options=types.HttpRetryOptions(attempts=1))
    client = genai.Client(api_key=api_key, http_options=http_options)
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.4)
    last_error = None
    for model in MODELS:
        for attempt in range(2):
            model_started = time.perf_counter()
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                print(f"[chat-timing] gemini model={model} attempt={attempt + 1} ms={int((time.perf_counter() - model_started) * 1000)} ok={bool(response and response.text)}")
                if response and response.text:
                    return response.text
                break
            except Exception as exc:
                last_error = exc
                status = gemini_status(exc)
                print(f"[chat-timing] gemini model={model} attempt={attempt + 1} ms={int((time.perf_counter() - model_started) * 1000)} error={type(exc).__name__} status={status}")
                transient = status == 429 or (status is not None and status >= 500)
                if attempt == 0 and transient:
                    time.sleep(1)
                    continue
                break
    raise RuntimeError("Gemini could not generate a response.") from last_error

def answer_stream(question, hits, history, sermon_search_performed=True):
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Gemini is not configured yet.")
    context = "\n\n".join(f"[{i + 1}] Sermon: \"{h['title']}\" ({h['time']})\n{h['text']}" for i, h in enumerate(hits))
    if not context:
        context = ("(Provide a rich, biblically grounded pastoral response reflecting Pastor Niyi's core ministry principles, convictions, and pastoral wisdom, without robotic disclaimers.)"
                   if sermon_search_performed else "(The sermon archive was not searched for this request.)")
    recent = history[-12:]
    convo = "\n".join(f"{turn.role.upper()}: {turn.content[:600]}" for turn in recent) or "(none)"
    routing_note = "" if sermon_search_performed else "\n\nRouting note: The sermon archive was not searched because this message does not appear to need Pastor Niyi's sermon teachings. Answer the user's request directly and naturally. Do not say that the sermon archive had no relevant passages, and do not invent or attribute a sermon teaching."
    prompt = f"Recent conversation:\n{convo}\n\nSermon passages from Pastor Niyi Adetiloye:\n{context}{routing_note}\n\nQuestion: {question}"
    http_options = types.HttpOptions(timeout=12000, retry_options=types.HttpRetryOptions(attempts=1))
    client = genai.Client(api_key=api_key, http_options=http_options)
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.4)
    last_error = None
    try:
        for model in MODELS:
            for attempt in range(2):
                model_started = time.perf_counter()
                emitted = False
                try:
                    for chunk in client.models.generate_content_stream(model=model, contents=prompt, config=config):
                        piece = getattr(chunk, "text", None)
                        if piece:
                            emitted = True
                            yield piece
                    print(f"[chat-timing] gemini_stream model={model} attempt={attempt + 1} ms={int((time.perf_counter() - model_started) * 1000)} ok={emitted}")
                    if emitted:
                        return
                    break
                except Exception as exc:
                    last_error = exc
                    status = gemini_status(exc)
                    print(f"[chat-timing] gemini_stream model={model} attempt={attempt + 1} ms={int((time.perf_counter() - model_started) * 1000)} error={type(exc).__name__} status={status}")
                    if emitted:
                        raise RuntimeError("Gemini streaming was interrupted.") from exc
                    transient = status == 429 or (status is not None and status >= 500)
                    if attempt == 0 and transient:
                        time.sleep(1)
                        continue
                    break
        raise RuntimeError("Gemini could not generate a response.") from last_error
    finally:
        client.close()

@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/widget")
def widget():
    return FileResponse(WEB_DIR / "widget.html")

@app.get("/widget.js")
def widget_embed_script():
    return FileResponse(WEB_DIR / "widget-embed.js", media_type="application/javascript")

@app.get("/admin")
@app.head("/admin")
def admin_portal():
    return FileResponse(WEB_DIR / "admin.html")

def get_admin_token(request: Request, token: Optional[str] = None) -> str:
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""

def require_admin(request: Request, token: Optional[str] = None):
    tok = get_admin_token(request, token)
    if not tok or not validate_admin_session(tok):
        raise HTTPException(status_code=401, detail="Invalid or expired administrator session.")

def get_optional_user_id(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        tok = auth[7:].strip()
        return validate_user_session(tok)
    return None

def require_user_id(request: Request) -> str:
    uid = get_optional_user_id(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized user session.")
    return uid

@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password. Default is 0000.")
    token = create_admin_session()
    return {
        "ok": True,
        "token": token,
        "is_default": is_admin_default_password()
    }

@app.post("/api/admin/change-password")
def admin_change_pwd(payload: ChangePasswordRequest, request: Request):
    if not verify_admin_password(payload.old_password):
        raise HTTPException(status_code=401, detail="Incorrect current password.")
    success, msg = change_admin_password(payload.old_password, payload.new_password)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    new_token = create_admin_session()
    return {"ok": True, "message": msg, "token": new_token}

@app.get("/api/admin/feedbacks")
def admin_get_feedbacks(request: Request, status: str = "all", category: str = "all", search: str = ""):
    require_admin(request)
    feedbacks = get_feedbacks(status_filter=status, category_filter=category, search=search)
    stats = get_feedback_stats()
    return {
        "ok": True,
        "feedbacks": feedbacks,
        "stats": stats,
        "is_default_password": is_admin_default_password()
    }

@app.post("/api/admin/feedbacks/status")
def admin_update_feedback_status(payload: FeedbackStatusRequest, request: Request):
    require_admin(request)
    ok = update_feedback_status(payload.id, payload.status)
    if not ok:
        raise HTTPException(status_code=400, detail="Could not update feedback status.")
    return {"ok": True}

@app.delete("/api/admin/feedbacks/{feedback_id}")
def admin_delete_feedback(feedback_id: str, request: Request):
    require_admin(request)
    ok = delete_feedback(feedback_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Feedback item not found.")
    return {"ok": True}

@app.get("/api/admin/feedbacks/export")
def admin_export_feedbacks(request: Request, token: Optional[str] = None):
    require_admin(request, token=token)
    feedbacks = get_feedbacks()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Category", "Status", "Date (UTC)", "Feedback Text", "Contact Info", "Context Query", "User ID"])
    for fb in feedbacks:
        writer.writerow([
            fb.get("id", ""),
            fb.get("category", ""),
            fb.get("status", ""),
            fb.get("created_at", ""),
            fb.get("content", ""),
            fb.get("contact", ""),
            fb.get("context_question", ""),
            fb.get("user_id", "") or ""
        ])
    filename = f"pastor_niyi_feedbacks_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/feedback")
def submit_feedback(payload: FeedbackSubmitRequest, request: Request):
    user_id = get_optional_user_id(request)
    item = add_feedback(
        category=payload.category,
        content=payload.content,
        contact=payload.contact,
        context_question=payload.context_question,
        user_id=user_id
    )
    return {
        "ok": True,
        "id": item["id"],
        "message": "Thank you for sharing your thoughts with us. God bless you!"
    }

@app.get("/api/auth/config")
def get_auth_config():
    return {"google_client_id": get_google_client_id()}

@app.post("/api/auth/member")
def member_login(payload: MemberLoginRequest):
    user, token = authenticate_member_email(payload.email, payload.name)
    if not user or not token:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    return {
        "ok": True,
        "user": user,
        "token": token
    }

@app.post("/api/admin/google-client-id")
def admin_set_google_id(payload: GoogleConfigUpdateRequest, request: Request):
    require_admin(request)
    set_google_client_id(payload.client_id)
    return {"ok": True, "message": "Google Client ID updated successfully."}

@app.post("/api/auth/google")
def auth_google(payload: GoogleAuthRequest):
    user, token = authenticate_google_credential(payload.credential)
    if not user or not token:
        raise HTTPException(status_code=400, detail="Unable to authenticate Google account.")
    return {
        "ok": True,
        "user": user,
        "token": token
    }

@app.get("/api/auth/me")
def auth_me(request: Request):
    user_id = require_user_id(request)
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "user": user}

@app.post("/api/user/bookmarks")
def add_bookmark(payload: UserBookmarkRequest, request: Request):
    user_id = require_user_id(request)
    bookmarks = add_user_bookmark(user_id, payload.title, payload.excerpt, payload.url)
    return {"ok": True, "bookmarks": bookmarks}

@app.delete("/api/user/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: str, request: Request):
    user_id = require_user_id(request)
    bookmarks = remove_user_bookmark(user_id, bookmark_id)
    return {"ok": True, "bookmarks": bookmarks}

def sse_event(name, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"

def public_chat_error(exc):
    message = str(exc)
    if "Gemini" in message:
        if "Gemini is not configured" in message:
            return "Gemini is not configured. Check the GEMINI_API_KEY environment variable in Render."
        cause = exc.__cause__
        if cause:
            print(f"[chat-error] gemini_cause={type(cause).__name__} code={getattr(cause, 'code', None)} status={getattr(cause, 'status_code', None)}")
            return explain_gemini_failure(cause)
        return "Gemini could not generate a reply. Check the API key, model access, and quota in Google AI Studio."
    if "Sermon database is not ready" in message:
        return "The sermon library is still starting. Please try again shortly."
    return "The sermon library is not ready yet. Please try again in a moment."

@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, request: Request):
    request_started = time.perf_counter()
    enforce_rate_limit(request.client.host if request.client else "unknown")
    history = [turn for turn in payload.history if turn.role in {"user", "assistant"}]

    def events():
        hits = []
        quick_reply = social_reply(payload.message)
        if quick_reply:
            yield sse_event("status", {"message": "Responding…"})
            yield sse_event("token", {"text": quick_reply})
            yield sse_event("sources", {"sources": []})
            print(f"[chat-timing] search_skipped=social total_ms={int((time.perf_counter() - request_started) * 1000)}")
            yield sse_event("done", {})
            return
        search_sermons, route_reason = should_search_sermons(payload.message, history)
        hits = []
        try:
            if search_sermons:
                yield sse_event("status", {"message": "Searching Pastor Niyi’s messages…"})
                stage_started = time.perf_counter()
                collection, exclude = get_ready_collection()
                print(f"[chat-timing] collection_setup_ms={int((time.perf_counter() - stage_started) * 1000)}")
                stage_started = time.perf_counter()
                search_query = contextualize_query(payload.message.strip(), history)
                hits = retrieve(collection, exclude, search_query)
                print(f"[chat-timing] retrieval_ms={int((time.perf_counter() - stage_started) * 1000)} hits={len(hits)}")
                yield sse_event("status", {"message": "Preparing a sermon-grounded reply…"})
            else:
                yield sse_event("status", {"message": "Preparing a helpful reply…"})
                print(f"[chat-timing] search_skipped={route_reason}")
            stage_started = time.perf_counter()
            pieces = []
            for piece in answer_stream(payload.message.strip(), hits, history, search_sermons):
                pieces.append(piece)
                yield sse_event("token", {"text": piece})
            if not pieces:
                raise RuntimeError("Gemini returned an empty response.")
            sources = [{"title": hit["title"], "time": hit["time"], "excerpt": hit["text"][:320], "telegram_links": media_links_for(hit["title"], hit.get("message_id"), hit.get("time"))} for hit in hits]
            yield sse_event("sources", {"sources": sources})
            print(f"[chat-timing] stream_answer_ms={int((time.perf_counter() - stage_started) * 1000)} total_ms={int((time.perf_counter() - request_started) * 1000)}")
            yield sse_event("done", {})
        except HTTPException as exc:
            yield sse_event("error", {"detail": exc.detail})
        except RuntimeError as exc:
            print(f"[chat-error] runtime={exc} total_ms={int((time.perf_counter() - request_started) * 1000)}")
            if hits:
                sources = [{"title": hit["title"], "time": hit["time"], "excerpt": hit["text"][:320], "telegram_links": media_links_for(hit["title"], hit.get("message_id"), hit.get("time"))} for hit in hits]
                yield sse_event("sources", {"sources": sources})
            yield sse_event("error", {"detail": public_chat_error(exc)})
        except Exception as exc:
            print(f"[chat-error] type={type(exc).__name__} total_ms={int((time.perf_counter() - request_started) * 1000)}")
            yield sse_event("error", {"detail": "I couldn’t prepare a response just now. Please try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )

@app.head("/")
def home_head():
    return Response(status_code=200)

@app.get("/api/health")
def health():
    return {"status": "ok", "database_ready": (DB_DIR / "chroma.sqlite3").is_file()}

@app.post("/api/chat")
def chat(payload: ChatRequest, request: Request):
    request_started = time.perf_counter()
    enforce_rate_limit(request.client.host if request.client else "unknown")
    history = [turn for turn in payload.history if turn.role in {"user", "assistant"}]
    quick_reply = social_reply(payload.message)
    if quick_reply:
        return {"answer": quick_reply, "sources": []}
    try:
        search_sermons, route_reason = should_search_sermons(payload.message, history)
        hits = []
        if search_sermons:
            stage_started = time.perf_counter()
            collection, exclude = get_ready_collection()
            print(f"[chat-timing] collection_setup_ms={int((time.perf_counter() - stage_started) * 1000)}")
            stage_started = time.perf_counter()
            search_query = contextualize_query(payload.message.strip(), history)
            hits = retrieve(collection, exclude, search_query)
            print(f"[chat-timing] retrieval_ms={int((time.perf_counter() - stage_started) * 1000)} hits={len(hits)}")
        else:
            print(f"[chat-timing] search_skipped={route_reason}")
        stage_started = time.perf_counter()
        response = answer(payload.message.strip(), hits, history, search_sermons)
        print(f"[chat-timing] answer_ms={int((time.perf_counter() - stage_started) * 1000)} total_ms={int((time.perf_counter() - request_started) * 1000)}")
        sources = [{"title": hit["title"], "time": hit["time"], "excerpt": hit["text"][:320], "telegram_links": media_links_for(hit["title"], hit.get("message_id"), hit.get("time"))} for hit in hits]
        return {"answer": response, "sources": sources}
    except HTTPException:
        raise
    except RuntimeError as exc:
        message = str(exc)
        print(f"[chat-error] runtime={message} total_ms={int((time.perf_counter() - request_started) * 1000)}")
        if "Gemini" in message:
            if "Gemini is not configured" in message:
                raise HTTPException(status_code=503, detail="Gemini is not configured. Check the GEMINI_API_KEY environment variable in Render.") from exc
            cause = exc.__cause__
            if cause:
                print(f"[chat-error] gemini_cause={type(cause).__name__} code={getattr(cause, 'code', None)} status={getattr(cause, 'status_code', None)}")
                detail = explain_gemini_failure(cause)
            else:
                detail = "Gemini could not generate a reply. Check the API key, model access, and quota in Google AI Studio."
            raise HTTPException(status_code=503, detail=detail) from exc
        if "Sermon database is not ready" in message:
            raise HTTPException(status_code=503, detail="The sermon library is still starting. Please try again shortly.") from exc
        raise HTTPException(status_code=503, detail="The sermon library is not ready yet. Please try again in a moment.") from exc
    except Exception as exc:
        print(f"[chat-error] type={type(exc).__name__} total_ms={int((time.perf_counter() - request_started) * 1000)}")
        raise HTTPException(status_code=502, detail="I couldn't prepare a response just now. Please try again.") from exc


