"""
Pastor Niyi Adetiloye - Sermon Study Assistant
Light Modern UI matching user preferred aesthetic
"""
import os
import json
import html
import base64
from datetime import datetime
import streamlit as st
import chromadb
from chromadb.utils import embedding_functions
from google import genai
from google.genai import types

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(APP_DIR, "sermon_vector_db")
EXCLUDE_FILE = os.path.join(APP_DIR, "exclude_titles.json")
COLLECTION = "pastor_niyi_sermons"
MODELS = [m for m in [st.secrets.get("GEMINI_MODEL", ""), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"] if m]
TOP_K = 6
MAX_DISTANCE = 0.65

# Load Pastor Niyi avatar in base64
AVATAR_PATH = os.path.join(APP_DIR, "assets", "pastor_niyi.webp")
if os.path.exists(AVATAR_PATH):
    with open(AVATAR_PATH, "rb") as f:
        PASTOR_IMG_B64 = f"data:image/webp;base64,{base64.b64encode(f.read()).decode('utf-8')}"
else:
    PASTOR_IMG_B64 = "https://images.unsplash.com/photo-1544717305-2782549b5136?w=150"

st.set_page_config(
    page_title="Pastor Niyi AI",
    page_icon="✝",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS for the Light Ice-Blue & Navy Theme ──────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1e293b;
    background-color: #f8fafd;
}}

#MainMenu, footer, header {{ visibility: hidden !important; }}
.block-container {{
    max-width: 680px;
    padding-top: 1.5rem;
    padding-bottom: 5rem;
}}

/* Header */
.app-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 1.2rem;
    border-bottom: 1px solid #e5edf5;
    margin-bottom: 1.8rem;
}}

.header-left {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.avatar-wrapper {{
    position: relative;
    width: 46px;
    height: 46px;
}}

.header-avatar {{
    width: 46px;
    height: 46px;
    border-radius: 50%;
    object-fit: cover;
    box-shadow: 0 2px 8px rgba(0, 30, 60, 0.12);
}}

.status-badge {{
    position: absolute;
    bottom: -1px;
    right: -1px;
    width: 12px;
    height: 12px;
    background-color: #10b981;
    border: 2px solid #ffffff;
    border-radius: 50%;
}}

.header-text h1 {{
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f2238;
    margin: 0;
    line-height: 1.25;
}}

.status-text {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.78rem;
    color: #10b981;
    font-weight: 500;
    margin-top: 2px;
}}

.status-dot {{
    width: 7px;
    height: 7px;
    background-color: #10b981;
    border-radius: 50%;
    display: inline-block;
}}

.header-tagline {{
    font-size: 0.84rem;
    color: #6482a4;
    font-style: italic;
    font-weight: 500;
}}

/* Messages */
.chat-stream {{
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
    margin-bottom: 1.5rem;
}}

/* User Row */
.user-row {{
    display: flex;
    justify-content: flex-end;
    align-items: flex-end;
    gap: 10px;
    margin-left: auto;
    max-width: 82%;
}}

.user-bubble {{
    background-color: #ebf3fb;
    color: #0f2238;
    padding: 12px 18px;
    border-radius: 18px 18px 4px 18px;
    font-size: 0.94rem;
    line-height: 1.5;
    box-shadow: 0 1px 3px rgba(0, 30, 60, 0.04);
}}

.user-meta {{
    font-size: 0.72rem;
    color: #6482a4;
    margin-top: 4px;
    text-align: right;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
}}

.check-mark {{
    color: #0284c7;
    font-weight: 700;
}}

.user-avatar-circle {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background-color: #0f2238;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}

/* Assistant Row */
.assistant-row {{
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
    gap: 12px;
    max-width: 88%;
}}

.assistant-avatar {{
    width: 36px;
    height: 36px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    margin-top: 4px;
    box-shadow: 0 1px 4px rgba(0, 20, 40, 0.15);
}}

.assistant-card {{
    background-color: #ffffff;
    border: 1px solid #e2ecf5;
    border-radius: 18px 18px 18px 4px;
    padding: 16px 20px;
    box-shadow: 0 2px 10px rgba(0, 30, 60, 0.03);
}}

.assistant-text {{
    color: #1e293b;
    font-size: 0.94rem;
    line-height: 1.62;
}}

.assistant-text p {{
    margin-bottom: 0.8rem;
}}
.assistant-text p:last-child {{
    margin-bottom: 0;
}}

.assistant-divider {{
    height: 1px;
    background-color: #eaf1f8;
    margin: 14px 0 10px 0;
}}

.assistant-followup {{
    font-size: 0.88rem;
    font-weight: 600;
    color: #1e293b;
    margin-bottom: 6px;
}}

.assistant-time {{
    font-size: 0.72rem;
    color: #94a3b8;
}}

/* Quick Action Pills */
.action-pills-row {{
    display: flex;
    gap: 8px;
    margin-top: 10px;
    margin-left: 48px;
    margin-bottom: 18px;
    flex-wrap: wrap;
}}

/* Streamlit Button Tweaks */
div[data-testid="column"] button {{
    border-radius: 20px !important;
    font-size: 0.83rem !important;
    padding: 6px 14px !important;
    font-weight: 500 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    transition: all 0.15s ease !important;
}}

/* Suggested Questions Section */
.suggestions-box {{
    background: #ffffff;
    border: 1px solid #e5edf5;
    border-radius: 16px;
    padding: 16px;
    margin-top: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 8px rgba(0, 30, 60, 0.03);
}}

.suggestions-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}}

.suggestions-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.92rem;
    font-weight: 700;
    color: #0f2238;
}}

.view-all-link {{
    font-size: 0.82rem;
    color: #0284c7;
    font-weight: 600;
}}

/* Sources Accordion */
.stExpander {{
    border: 1px solid #e2ecf5 !important;
    border-radius: 12px !important;
    background-color: #f8fafd !important;
    margin-top: 8px !important;
    margin-left: 48px !important;
}}
.source-item {{
    border-left: 3px solid #0284c7;
    padding: 6px 10px;
    margin-bottom: 8px;
    background-color: #ffffff;
    border-radius: 4px;
    font-size: 0.82rem;
}}
.source-title {{
    font-weight: 600;
    color: #0f2238;
}}
.source-time {{
    color: #64748b;
    font-size: 0.76rem;
}}

/* Chat Input Styling */
div[data-testid="stChatInput"] {{
    border-radius: 28px !important;
    border: 1px solid #d9e6f2 !important;
    box-shadow: 0 4px 18px rgba(0, 30, 60, 0.08) !important;
    background-color: #ffffff !important;
}}
div[data-testid="stChatInput"] textarea {{
    font-size: 0.92rem !important;
}}

/* Pastor Niyi AI interface refresh */
:root {{
    --pn-ink: #202925;
    --pn-muted: #56635d;
    --pn-green: #17362f;
    --pn-green-soft: #e9efeb;
    --pn-gold: #c29b5d;
    --pn-paper: #faf9f6;
    --pn-line: #e8e8e1;
}}
html, body, [data-testid="stAppViewContainer"] {{
    color: var(--pn-ink) !important;
    background: var(--pn-paper) !important;
}}
.block-container {{ max-width: 760px; padding-top: 1.35rem; padding-bottom: 5.4rem; }}
.app-header {{ padding-bottom: 1rem; border-bottom-color: var(--pn-line); margin-bottom: 2.1rem; }}
.header-avatar {{ border: 1px solid #d8d6ca; box-shadow: 0 2px 9px rgba(23, 54, 47, .10); }}
.status-badge {{ background-color: var(--pn-gold); }}
.header-text h1 {{ color: var(--pn-green); font-family: 'Libre Baskerville', Georgia, serif; font-size: 1.12rem; font-weight: 400; letter-spacing: -.025em; }}
.status-text {{ color: #586a60; font-size: .74rem; }}
.status-dot {{ background-color: var(--pn-gold); }}
.header-tagline {{ color: #66766d; font-size: .78rem; font-style: normal; }}
.user-bubble {{ background: var(--pn-green); color: #fff; border-radius: 16px 16px 4px 16px; box-shadow: none; }}
.user-meta, .assistant-time {{ color: #737e78; }}
.check-mark {{ color: var(--pn-gold); }}
.user-avatar-circle {{ background: var(--pn-green); }}
.assistant-card {{ background: #fff; border-color: var(--pn-line); border-radius: 15px 15px 15px 4px; box-shadow: 0 4px 16px rgba(23, 54, 47, .035); }}
.assistant-text {{ color: #29342e; }}
.assistant-followup {{ color: var(--pn-green); }}
.assistant-divider {{ background: var(--pn-line); }}
.suggestions-box {{ padding: 0; margin: 0 0 1.45rem; border: 0; border-radius: 0; background: transparent; box-shadow: none; }}
.suggestions-header {{ justify-content: flex-start; margin: 1.5rem 0 .55rem; }}
.suggestions-title {{ color: #64736a; font-size: .69rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }}
.suggestions-title span, .view-all-link {{ display: none; }}
div[data-testid="column"] button {{ min-height: 42px; border: 1px solid #e4e5dd !important; border-radius: 9px !important; background: rgba(255,255,255,.82) !important; color: #34413b !important; font-size: .78rem !important; font-weight: 500 !important; text-align: left; box-shadow: none !important; transition: border-color .16s ease, background .16s ease, transform .16s ease !important; }}
div[data-testid="column"] button:hover {{ border-color: #b7c6bb !important; background: #fff !important; color: var(--pn-green) !important; transform: translateY(-1px); }}
.stExpander {{ border-color: var(--pn-line) !important; border-radius: 10px !important; background: #f7f7f2 !important; }}
.source-item {{ border-left-width: 1px; border-left-color: #d8d6ca; border-radius: 5px; }}
.source-title {{ color: var(--pn-green); }}
div[data-testid="stChatInput"] {{ border: 1px solid #dfe1d8 !important; border-radius: 12px !important; background: #fff !important; box-shadow: 0 5px 19px rgba(23, 54, 47, .07) !important; }}
div[data-testid="stChatInput"]:focus-within {{ border-color: #789185 !important; }}
div[data-testid="stChatInput"] textarea {{ color: var(--pn-ink) !important; font-size: .84rem !important; }}
div[data-testid="stSpinner"] {{ color: var(--pn-green) !important; }}
@media (max-width: 640px) {{
    .block-container {{ padding: 1rem 1rem 5.2rem; }}
    .app-header {{ align-items: flex-start; gap: 10px; margin-bottom: 1.7rem; }}
    .header-tagline {{ max-width: 115px; padding-top: 4px; text-align: right; line-height: 1.45; }}
    .header-text h1 {{ font-size: .98rem; }}
    .assistant-row {{ max-width: 100%; gap: 9px; }}
    .assistant-card {{ padding: 14px 15px; }}
    .user-row {{ max-width: 92%; }}
    .suggestions-box [data-testid="column"] {{ min-width: 100% !important; }}
}}
</style>
""", unsafe_allow_html=True)


def ensure_db():
    """Extracts sermon database on startup from local or Google Drive if on cloud."""
    sqlite_file = os.path.join(DB_DIR, "chroma.sqlite3")
    if os.path.exists(sqlite_file):
        return

    # 1. Check local download zip
    local_zips = [
        os.path.join(APP_DIR, "sermon_vector_db.zip"),
        os.path.expanduser(r"~\Downloads\sermon_vector_db-20261005T034509Z-1-001.zip"),
    ]
    for pz in local_zips:
        if os.path.exists(pz):
            import zipfile
            with zipfile.ZipFile(pz, "r") as z:
                z.extractall(APP_DIR)
            if os.path.exists(sqlite_file):
                return

    # 2. Check Google Drive URL/ID from Streamlit Secrets
    gdrive_target = st.secrets.get("GDRIVE_FILE_ID", "") or st.secrets.get("GDRIVE_DB_URL", "")
    if gdrive_target:
        import gdown, zipfile
        temp_zip = os.path.join(APP_DIR, "_sermon_db.zip")
        with st.spinner("Downloading sermon library archive (~15-20s on cloud)..."):
            if "drive.google.com" in gdrive_target or "http" in gdrive_target:
                gdown.download(url=gdrive_target, output=temp_zip, quiet=False, fuzzy=True)
            else:
                gdown.download(id=gdrive_target, output=temp_zip, quiet=False)
            if os.path.exists(temp_zip):
                with zipfile.ZipFile(temp_zip, "r") as z:
                    z.extractall(APP_DIR)
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass


@st.cache_resource(show_spinner="Loading Pastor Niyi sermon archive…")
def load():
    ensure_db()
    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    except Exception:
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
            class CompatibleONNX(ONNXMiniLM_L6_V2):
                def name(self) -> str:
                    return "sentence_transformer"
            emb = CompatibleONNX()
        except Exception:
            emb = None

    if emb is not None:
        try:
            col = client.get_collection(COLLECTION, embedding_function=emb)
        except ValueError:
            col = client.get_collection(COLLECTION)
    else:
        col = client.get_collection(COLLECTION)

    exclude = json.load(open(EXCLUDE_FILE, encoding="utf-8")) if os.path.exists(EXCLUDE_FILE) else []
    return col, exclude


def retrieve(col, exclude, question):
    kwargs = {"query_texts": [question], "n_results": TOP_K}
    if exclude:
        kwargs["where"] = {"title": {"$nin": exclude}}
    r = col.query(**kwargs)
    hits = []
    for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
        if dist <= MAX_DISTANCE:
            hits.append({"title": meta.get("title", ""), "time": meta.get("time_range", ""), "text": doc, "dist": dist})
    return hits


SYSTEM_INSTRUCTION = """You are an AI assistant built on the teachings, sermons, writings, and ministry philosophy of Pastor Niyi Adetiloye of The Designate Church.

Your primary responsibility is to communicate in a manner that reflects his biblical convictions, teaching style, pastoral wisdom, and heart for people.

Response Guidelines:

1. Start with concise answers.
   - For straightforward questions, provide a direct answer in 1-3 paragraphs.
   - Avoid unnecessary length unless the user requests more detail.

2. Progressive Depth.
   - After giving a short answer, offer deeper insight where appropriate.
   - Use phrases such as "For further understanding...", "A deeper perspective is...", "Let's examine what Scripture teaches about this."

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

Default Response Style:
- Begin with a direct answer.
- Expand only as needed.
- Prioritize clarity over length.
- Sound like a wise pastor speaking to a member, not an academic writing a textbook.

The goal is not merely to provide information but to help people understand God's Word, grow spiritually, and apply biblical truth to daily life."""


def answer(api_key, question, hits, history):
    if hits:
        context = "\n\n".join(f"[{i+1}] Sermon: \"{h['title']}\" ({h['time']})\n{h['text']}" for i, h in enumerate(hits))
    else:
        context = "(No relevant passages were found in Pastor Niyi's messages for this question.)"

    recent = history[-4:]
    convo = "\n".join(f"{t['role'].upper()}: {t['content'][:600]}" for t in recent) or "(none)"

    prompt = f"""Recent conversation:
{convo}

Sermon passages from Pastor Niyi Adetiloye:
{context}

Question: {question}"""

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.4)
    last_err = None
    for model in MODELS:
        try:
            return client.models.generate_content(model=model, contents=prompt, config=config).text
        except Exception as e:
            last_err = e
    raise RuntimeError(f"All models failed: {last_err}")


# ── HEADER ────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-header">
  <div class="header-left">
    <div class="avatar-wrapper">
      <img src="{PASTOR_IMG_B64}" class="header-avatar" alt="Pastor Niyi" />
      <span class="status-badge"></span>
    </div>
    <div class="header-text">
       <h1>Pastor Niyi AI</h1>
      <div class="status-text">
         <span class="status-dot"></span> Sermon study assistant
      </div>
    </div>
  </div>
  <div class="header-tagline">
     Explore teachings from Pastor Niyi Adetiloye.
  </div>
</div>
""", unsafe_allow_html=True)

# ── API KEY & SETUP ──────────────────────────────────────────────
def load_api_key():
    k = st.secrets.get("GEMINI_API_KEY", "")
    if k and "PASTE" not in k and len(k.strip()) > 10:
        return k.strip()
    k = os.environ.get("GEMINI_API_KEY", "")
    if k and "PASTE" not in k and len(k.strip()) > 10:
        return k.strip()
    key_file = os.path.join(APP_DIR, "api_key.txt")
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "PASTE" not in line and len(line) > 10:
                        return line
        except Exception:
            pass
    return st.session_state.get("gemini_api_key", "").strip()

api_key = load_api_key()

if not api_key:
    st.markdown("""
    <div style="background:#ffffff; border:1.5px solid #38bdf8; border-radius:14px; padding:14px 18px; margin-bottom:1.2rem; box-shadow:0 2px 10px rgba(56,189,248,0.1);">
      <div style="display:flex; align-items:center; gap:8px; font-weight:700; color:#0f2238; font-size:0.95rem;">
        <span>🔑</span> Enter Gemini API Key
      </div>
      <div style="font-size:0.82rem; color:#64748b; margin-top:3px;">
        Paste your key below and press <b>Enter</b> to start chatting (or save it in <code>api_key.txt</code> in the app folder).
      </div>
    </div>
    """, unsafe_allow_html=True)
    input_val = st.text_input("Gemini API Key", type="password", placeholder="Paste AIzaSy... here and press Enter", label_visibility="collapsed")
    if input_val and len(input_val.strip()) > 10:
        st.session_state["gemini_api_key"] = input_val.strip()
        try:
            with open(os.path.join(APP_DIR, "api_key.txt"), "w", encoding="utf-8") as f:
                f.write(f"{input_val.strip()}\\n")
        except Exception:
            pass
        st.rerun()

ensure_db()
if not os.path.exists(os.path.join(DB_DIR, "chroma.sqlite3")):
    st.error(f"Sermon database not found at {DB_DIR}")
    st.stop()

col, exclude = load()

# ── SESSION STATE ────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# ── RENDER CHAT HISTORY ──────────────────────────────────────────
for idx, turn in enumerate(st.session_state.history):
    time_str = turn.get("time", "Just now")
    if turn["role"] == "user":
        st.markdown(f"""
        <div class="user-row">
          <div>
            <div class="user-bubble">{html.escape(turn['content'])}</div>
            <div class="user-meta">{time_str} <span class="check-mark">✓✓</span></div>
          </div>
          <div class="user-avatar-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Convert markdown paragraphs to clean HTML
        content_paragraphs = turn["content"].split("\n\n")
        html_paragraphs = "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in content_paragraphs if p.strip())
        
        st.markdown(f"""
        <div class="assistant-row">
          <img src="{PASTOR_IMG_B64}" class="assistant-avatar" alt="Pastor Niyi" />
          <div class="assistant-card">
            <div class="assistant-text">{html_paragraphs}</div>
            <div class="assistant-divider"></div>
            <div class="assistant-followup">Would you like a deeper study on this topic?</div>
            <div class="assistant-time">{time_str}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Sources accordion
        if turn.get("hits"):
            with st.expander(f"📚 Sources ({len(turn['hits'])} sermon passages)"):
                for s_i, h in enumerate(turn["hits"], 1):
                    snippet = html.escape(h["text"][:240]) + "…"
                    st.markdown(f"""
                    <div class="source-item">
                      <div class="source-title">[{s_i}] {html.escape(h['title'])}</div>
                      <div class="source-time">Timestamp: {h['time']}</div>
                      <div style="color:#475569; margin-top:3px;">{snippet}</div>
                    </div>
                    """, unsafe_allow_html=True)

# ── FOLLOW-UP ACTION PILLS (Under latest message) ────────────────
if st.session_state.history and st.session_state.history[-1]["role"] == "assistant":
    c1, c2, c3, c4 = st.columns([1.6, 1.4, 1.4, 1.0])
    with c1:
        if st.button("Yes, show me more", key="pill_more"):
            st.session_state.pending_query = "Yes, please provide a deeper study and biblical breakdown on this topic."
            st.rerun()
    with c2:
        if st.button("Related Scriptures", key="pill_scriptures"):
            st.session_state.pending_query = "What key Scriptures and Bible passages support this teaching?"
            st.rerun()
    with c3:
        if st.button("Practical Steps", key="pill_steps"):
            st.session_state.pending_query = "What practical steps and everyday applications can I take from this?"
            st.rerun()
    with c4:
        if st.button("Not now", key="pill_not_now"):
            st.session_state.pending_query = None
            st.rerun()


# ── SUGGESTED QUESTIONS (Shown on empty/fresh chat) ──────────────
if not st.session_state.history:
    st.markdown("""
    <div class="suggestions-box">
      <div class="suggestions-header">
        <div class="suggestions-title">
          <span>💡</span> Suggested Questions
        </div>
        <div class="view-all-link">View all →</div>
      </div>
    """, unsafe_allow_html=True)
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("What has Pastor Niyi taught about thanksgiving?", key="sq_thanksgiving", use_container_width=True):
            st.session_state.pending_query = "What has Pastor Niyi taught about thanksgiving?"
            st.rerun()
        if st.button("Where should I begin with building my faith?", key="sq_faith", use_container_width=True):
            st.session_state.pending_query = "Where should I begin with building my faith?"
            st.rerun()
            
    with col_b:
        if st.button("Show me teachings about prayer.", key="sq_prayer", use_container_width=True):
            st.session_state.pending_query = "Show me teachings about prayer."
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)


# ── HANDLE PROMPT INPUT ──────────────────────────────────────────
pending = st.session_state.pop("pending_query", None)
user_input = st.chat_input("Ask a question about a message…")

query_to_run = pending or user_input

if query_to_run:
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API key in the box above to generate answers.")
    else:
        now_time = datetime.now().strftime("%I:%M %p")
        prior = st.session_state.history[:]
        
        st.session_state.history.append({
            "role": "user",
            "content": query_to_run,
            "time": now_time
        })
        
        # Context reformulation for short follow-ups
        search_q = query_to_run
        prev_user = [t["content"] for t in prior if t["role"] == "user"]
        if prev_user and len(query_to_run.split()) < 6:
            search_q = prev_user[-1] + " " + query_to_run

        with st.spinner("Searching Pastor Niyi's sermons…"):
            hits = retrieve(col, exclude, search_q)
            
        try:
            with st.spinner("Reflecting on Scripture and teachings…"):
                reply = answer(api_key, query_to_run, hits, prior)
        except Exception as e:
            reply = f"I am unable to generate a response at this moment. Please check your API key or network.\n\n`{e}`"
            
        reply_time = datetime.now().strftime("%I:%M %p")
        st.session_state.history.append({
            "role": "assistant",
            "content": reply,
            "hits": hits,
            "time": reply_time
        })
        st.rerun()
