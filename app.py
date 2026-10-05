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

import chromadb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
DB_DIR = Path(os.getenv("SERMON_DB_DIR", str(APP_DIR / "sermon_vector_db"))).resolve()
EXCLUDE_FILE = APP_DIR / "exclude_titles.json"
COLLECTION = "pastor_niyi_sermons"
MODELS = list(dict.fromkeys(filter(None, ["gemini-3.5-flash-lite", "gemini-3.8-flash", os.getenv("GEMINI_MODEL")])))
TOP_K = 6
MAX_DISTANCE = 0.65
CATALOG_FILE = APP_DIR / "sermon_catalog_with_urls.json"

def normalize_title(title):
    plain = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()

def title_aliases(title):
    normalized = normalize_title(title)
    aliases = {normalized} if normalized else set()
    for prefix in ("pastor niyi adetiloye", "niyi adetiloye"):
        if normalized.startswith(prefix + " "):
            aliases.add(normalized[len(prefix):].strip())
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

def telegram_links_for(title, message_id=None):
    matches = get_telegram_catalog().get(normalize_title(title), [])
    if message_id is not None:
        exact = [item for item in matches if str(item.get("message_id")) == str(message_id)]
        if exact:
            matches = exact
    pastor_matches = [item for item in matches if "niyi" in item["minister"].lower() or "adetiloye" in item["minister"].lower()]
    if pastor_matches:
        matches = pastor_matches
    links = []
    for item in matches:
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

6. Faithful Representation.
   - Reflect Pastor Niyi's known teachings using the sermon passages provided with each question.
   - When you use a passage, cite it inline by number and sermon title, e.g. [2] "A Time To Build".
   - Never attribute a view to Pastor Niyi that is not in the passages.
   - When the passages do not cover the question, say plainly that you could not find it in his messages, then share general biblical principles, clearly labelled as such, rather than inventing his position.
   - The passages are automatic transcripts and may contain transcription errors (names, scripture references). Do not quote obviously garbled text as his words.

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

_rate_lock = threading.Lock()
_rate_counts = {}

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

@app.on_event("startup")
def prepare_sermon_library():
    """Download missing Drive data and warm Chroma before accepting chat requests."""
    started = time.perf_counter()
    try:
        ensure_database()
        collection, _ = get_collection()
        # Trigger Chroma's ONNX model initialization outside the first user request.
        collection.query(query_texts=["sermon library warmup"], n_results=1)
        print(f"[startup] sermon_library_ready_ms={int((time.perf_counter() - started) * 1000)}")
    except Exception as exc:
        print(f"[startup] sermon_library_error={type(exc).__name__}: {exc}")

def retrieve(collection, exclude, question):
    query = {"query_texts": [question], "n_results": TOP_K}
    if exclude:
        query["where"] = {"title": {"$nin": exclude}}
    results = collection.query(**query)
    hits = []
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    for document, metadata, distance in zip(documents, metadatas, distances):
        if distance <= MAX_DISTANCE:
            hits.append({"title": metadata.get("title", "Sermon"), "time": metadata.get("time_range", ""), "text": document, "distance": distance, "message_id": metadata.get("message_id")})
    return hits

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

def answer(question, hits, history):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Gemini is not configured yet.")
    context = "\n\n".join(f"[{i + 1}] Sermon: \"{h['title']}\" ({h['time']})\n{h['text']}" for i, h in enumerate(hits))
    if not context:
        context = "(No relevant passages were found in Pastor Niyi's messages for this question.)"
    recent = history[-4:]
    convo = "\n".join(f"{turn.role.upper()}: {turn.content[:600]}" for turn in recent) or "(none)"
    prompt = f"Recent conversation:\n{convo}\n\nSermon passages from Pastor Niyi Adetiloye:\n{context}\n\nQuestion: {question}"
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

@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "database_ready": (DB_DIR / "chroma.sqlite3").is_file()}

@app.post("/api/chat")
def chat(payload: ChatRequest, request: Request):
    request_started = time.perf_counter()
    enforce_rate_limit(request.client.host if request.client else "unknown")
    history = [turn for turn in payload.history if turn.role in {"user", "assistant"}]
    try:
        stage_started = time.perf_counter()
        collection, exclude = get_collection()
        print(f"[chat-timing] collection_setup_ms={int((time.perf_counter() - stage_started) * 1000)}")
        stage_started = time.perf_counter()
        hits = retrieve(collection, exclude, payload.message.strip())
        print(f"[chat-timing] retrieval_ms={int((time.perf_counter() - stage_started) * 1000)} hits={len(hits)}")
        stage_started = time.perf_counter()
        response = answer(payload.message.strip(), hits, history)
        print(f"[chat-timing] answer_ms={int((time.perf_counter() - stage_started) * 1000)} total_ms={int((time.perf_counter() - request_started) * 1000)}")
        sources = [{"title": hit["title"], "time": hit["time"], "excerpt": hit["text"][:320], "telegram_links": telegram_links_for(hit["title"], hit.get("message_id"))} for hit in hits]
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


