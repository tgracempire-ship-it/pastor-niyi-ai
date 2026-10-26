import threading
"""User Authentication (Google 1-Tap & Local) and Admin Feedback Management."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(APP_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_AUTH_FILE = DATA_DIR / "admin_auth.json"
FEEDBACKS_FILE = DATA_DIR / "feedbacks.json"
USERS_FILE = DATA_DIR / "users.json"
ANALYTICS_FILE = DATA_DIR / "analytics.json"

# ── Password Hashing Helpers ──────────────────────────────────────────────────

def _hash_password(password: str, salt: bytes = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return base64.b64encode(key).decode("ascii"), base64.b64encode(salt).decode("ascii")

def _verify_password(password: str, hashed_str: str, salt_str: str) -> bool:
    try:
        salt = base64.b64decode(salt_str.encode("ascii"))
        expected_hash, _ = _hash_password(password, salt)
        return hmac.compare_digest(expected_hash, hashed_str)
    except Exception:
        return False

# ── Admin Auth Management ────────────────────────────────────────────────────

def _load_admin_auth() -> Dict[str, Any]:
    if not ADMIN_AUTH_FILE.is_file():
        # Default password is "0000"
        h, s = _hash_password("0000")
        secret = secrets.token_hex(32)
        data = {
            "password_hash": h,
            "salt": s,
            "secret": secret,
            "is_default": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        ADMIN_AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data
    try:
        return json.loads(ADMIN_AUTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        h, s = _hash_password("0000")
        secret = secrets.token_hex(32)
        return {"password_hash": h, "salt": s, "secret": secret, "is_default": True}

def verify_admin_password(password: str) -> bool:
    auth = _load_admin_auth()
    return _verify_password(password, auth["password_hash"], auth["salt"])

def change_admin_password(old_password: str, new_password: str) -> Tuple[bool, str]:
    if not verify_admin_password(old_password):
        return False, "Incorrect current password."
    if len(new_password) < 4:
        return False, "New password must be at least 4 characters."
    
    h, s = _hash_password(new_password)
    auth = _load_admin_auth()
    auth["password_hash"] = h
    auth["salt"] = s
    auth["is_default"] = False
    auth["updated_at"] = datetime.now(timezone.utc).isoformat()
    ADMIN_AUTH_FILE.write_text(json.dumps(auth, indent=2), encoding="utf-8")
    return True, "Password updated successfully."

def is_admin_default_password() -> bool:
    auth = _load_admin_auth()
    return auth.get("is_default", False)

def create_admin_session() -> str:
    auth = _load_admin_auth()
    secret = auth["secret"].encode("utf-8")
    expiry = int(time.time()) + 7 * 86400  # 7 days
    payload = f"admin:{expiry}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode("utf-8")).decode("ascii")
    return token

def validate_admin_session(token: str) -> bool:
    if not token or not isinstance(token, str):
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 3:
            return False
        role, expiry_str, sig = parts
        if role != "admin":
            return False
        expiry = int(expiry_str)
        if time.time() > expiry:
            return False
        auth = _load_admin_auth()
        secret = auth["secret"].encode("utf-8")
        payload = f"{role}:{expiry}"
        expected_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False

# ── Feedback / Suggestion Store ──────────────────────────────────────────────

def _load_feedbacks() -> List[Dict[str, Any]]:
    if not FEEDBACKS_FILE.is_file():
        return []
    try:
        return json.loads(FEEDBACKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

_io_lock = threading.Lock()

def _atomic_write_json(filepath: Path, data: Any):
    with _io_lock:
        temp_file = filepath.with_name(f"{filepath.name}.tmp.{secrets.token_hex(4)}")
        temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_file.replace(filepath)

def _save_feedbacks(feedbacks: List[Dict[str, Any]]):
    _atomic_write_json(FEEDBACKS_FILE, feedbacks)

def add_feedback(
    category: str,
    content: str,
    contact: str = "",
    context_question: str = "",
    user_id: str = None
) -> Dict[str, Any]:
    content = str(content or "").strip()
    if not content:
        raise ValueError("Feedback content cannot be empty.")
    
    clean_category = str(category or "suggestion").lower().strip()
    valid_categories = {"suggestion", "sermon", "bug", "testimony", "rating", "other"}
    if clean_category not in valid_categories:
        clean_category = "suggestion"

    feedbacks = _load_feedbacks()
    fb_id = f"fb_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    new_item = {
        "id": fb_id,
        "category": clean_category,
        "content": content[:3000],
        "contact": str(contact or "").strip()[:150],
        "context_question": str(context_question or "").strip()[:500],
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "new",  # "new", "reviewed", "starred", "archived"
    }
    feedbacks.insert(0, new_item)  # Newest first
    _save_feedbacks(feedbacks)
    return new_item

def get_feedbacks(
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    feedbacks = _load_feedbacks()
    results = []
    search_lower = search.lower().strip() if search else None
    
    for fb in feedbacks:
        if status_filter and status_filter != "all" and fb.get("status") != status_filter:
            continue
        if category_filter and category_filter != "all" and fb.get("category") != category_filter:
            continue
        if search_lower:
            text = f"{fb.get('content', '')} {fb.get('contact', '')} {fb.get('category', '')}".lower()
            if search_lower not in text:
                continue
        results.append(fb)
    return results

def update_feedback_status(feedback_id: str, new_status: str) -> bool:
    if new_status not in {"new", "reviewed", "starred", "archived"}:
        return False
    feedbacks = _load_feedbacks()
    updated = False
    for fb in feedbacks:
        if fb.get("id") == feedback_id:
            fb["status"] = new_status
            fb["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            break
    if updated:
        _save_feedbacks(feedbacks)
    return updated

def delete_feedback(feedback_id: str) -> bool:
    feedbacks = _load_feedbacks()
    initial_len = len(feedbacks)
    feedbacks = [fb for fb in feedbacks if fb.get("id") != feedback_id]
    if len(feedbacks) < initial_len:
        _save_feedbacks(feedbacks)
        return True
    return False

def get_feedback_stats() -> Dict[str, Any]:
    feedbacks = _load_feedbacks()
    stats = {
        "total": len(feedbacks),
        "new": sum(1 for fb in feedbacks if fb.get("status") == "new"),
        "reviewed": sum(1 for fb in feedbacks if fb.get("status") == "reviewed"),
        "starred": sum(1 for fb in feedbacks if fb.get("status") == "starred"),
        "by_category": {
            "suggestion": sum(1 for fb in feedbacks if fb.get("category") == "suggestion"),
            "sermon": sum(1 for fb in feedbacks if fb.get("category") == "sermon"),
            "bug": sum(1 for fb in feedbacks if fb.get("category") == "bug"),
            "testimony": sum(1 for fb in feedbacks if fb.get("category") == "testimony"),
            "rating": sum(1 for fb in feedbacks if fb.get("category") == "rating"),
        }
    }
    return stats

# ── User Accounts & Google Auth (Option B) ───────────────────────────────────

def _load_users() -> Dict[str, Any]:
    if not USERS_FILE.is_file():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_users(users: Dict[str, Any]):
    _atomic_write_json(USERS_FILE, users)

def _create_user_token(user_id: str, email: str) -> str:
    auth = _load_admin_auth()
    secret = auth["secret"].encode("utf-8")
    expiry = int(time.time()) + 30 * 86400  # 30 days
    payload = f"user:{user_id}:{expiry}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode("utf-8")).decode("ascii")

def validate_user_session(token: str) -> Optional[str]:
    if not token or not isinstance(token, str):
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 4:
            return None
        role, user_id, expiry_str, sig = parts
        if role != "user":
            return None
        if time.time() > int(expiry_str):
            return None
        auth = _load_admin_auth()
        secret = auth["secret"].encode("utf-8")
        payload = f"{role}:{user_id}:{expiry_str}"
        expected_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return user_id
    except Exception:
        return None
    return None

def authenticate_google_credential(credential_jwt: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Decode Google Sign-In credential payload (standard JWT format)."""
    if not credential_jwt:
        return None, None
    try:
        # JWT format: header.payload.signature
        parts = credential_jwt.split(".")
        if len(parts) < 2:
            return None, None
        payload_b64 = parts[1]
        # Pad base64 string
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
        google_data = json.loads(payload_bytes.decode("utf-8"))
        
        email = google_data.get("email")
        if not email:
            return None, None
            
        sub = google_data.get("sub", email)
        name = google_data.get("name", email.split("@")[0])
        picture = google_data.get("picture", "")
        
        users = _load_users()
        user_id = f"usr_{hashlib.md5(email.lower().encode()).hexdigest()[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        
        if user_id in users:
            user = users[user_id]
            user["last_login"] = now
            user["name"] = name or user.get("name")
            user["picture"] = picture or user.get("picture")
        else:
            user = {
                "id": user_id,
                "email": email.lower(),
                "name": name,
                "picture": picture,
                "provider": "google",
                "created_at": now,
                "last_login": now,
                "bookmarks": [],
                "threads": []
            }
            users[user_id] = user
            
        _save_users(users)
        token = _create_user_token(user_id, email)
        return user, token
    except Exception as exc:
        print(f"[google-auth-error] {exc}")
        return None, None

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    users = _load_users()
    return users.get(user_id)

def add_user_bookmark(user_id: str, title: str, excerpt: str, url: str) -> List[Dict[str, Any]]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return []
    bookmarks = user.setdefault("bookmarks", [])
    # Avoid duplicate URLs
    if not any(b.get("url") == url and b.get("title") == title for b in bookmarks):
        bookmarks.insert(0, {
            "id": f"bm_{secrets.token_hex(4)}",
            "title": title,
            "excerpt": excerpt[:300],
            "url": url,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        _save_users(users)
    return bookmarks

def remove_user_bookmark(user_id: str, bookmark_id: str) -> List[Dict[str, Any]]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return []
    user["bookmarks"] = [b for b in user.get("bookmarks", []) if b.get("id") != bookmark_id]
    _save_users(users)
    return user["bookmarks"]



def get_user_threads(user_id: str) -> List[Dict[str, Any]]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return []
    threads = user.get("threads", [])
    # Return sorted by updated_at descending, omitting large transcript details in list view
    summary = []
    for t in threads:
        summary.append({
            "id": t.get("id"),
            "title": t.get("title", "Study Session"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
            "message_count": len(t.get("messages", [])),
            "preview": t.get("messages", [{}])[0].get("content", "")[:120] if t.get("messages") else ""
        })
    summary.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return summary

def get_user_thread(user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return None
    for t in user.get("threads", []):
        if t.get("id") == thread_id:
            return t
    return None

def save_user_thread(user_id: str, title: str, messages: List[Dict[str, Any]], thread_id: Optional[str] = None) -> Dict[str, Any]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return {}
    threads = user.setdefault("threads", [])
    now = datetime.now(timezone.utc).isoformat()
    
    clean_messages = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") in {"user", "assistant"}:
            clean_messages.append({
                "role": m.get("role"),
                "content": str(m.get("content", ""))[:12000],
                "sources": m.get("sources", []) if isinstance(m.get("sources"), list) else []
            })
            
    # Derive title if not provided or generic
    clean_title = str(title or "").strip()
    if not clean_title or clean_title == "New Conversation":
        for m in clean_messages:
            if m.get("role") == "user" and m.get("content"):
                first_text = m.get("content").strip()
                clean_title = first_text[:60] + ("…" if len(first_text) > 60 else "")
                break
    if not clean_title:
        clean_title = f"Study Session · {datetime.now(timezone.utc).strftime('%b %d, %H:%M')}"
        
    target_thread = None
    if thread_id:
        for t in threads:
            if t.get("id") == thread_id:
                target_thread = t
                break
                
    if target_thread:
        target_thread["title"] = clean_title
        target_thread["messages"] = clean_messages
        target_thread["updated_at"] = now
    else:
        new_id = f"th_{secrets.token_hex(6)}"
        target_thread = {
            "id": new_id,
            "title": clean_title,
            "messages": clean_messages,
            "created_at": now,
            "updated_at": now
        }
        threads.insert(0, target_thread)
        
    # Cap total stored threads per user to 50
    user["threads"] = threads[:50]
    _save_users(users)
    return target_thread

def remove_user_thread(user_id: str, thread_id: str) -> List[Dict[str, Any]]:
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return []
    user["threads"] = [t for t in user.get("threads", []) if t.get("id") != thread_id]
    _save_users(users)
    return get_user_threads(user_id)

def authenticate_member_email(email: str, name: str = "") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Instant passwordless member profile using email."""
    email = str(email or "").strip().lower()
    if not email or "@" not in email:
        return None, None
    users = _load_users()
    user_id = f"usr_{hashlib.md5(email.encode()).hexdigest()[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    if user_id in users:
        user = users[user_id]
        user["last_login"] = now
        if name and not user.get("name"):
            user["name"] = name.strip()
    else:
        user = {
            "id": user_id,
            "email": email,
            "name": name.strip() or email.split("@")[0].title(),
            "picture": "",
            "provider": "email",
            "created_at": now,
            "last_login": now,
            "bookmarks": [],
                "threads": []
        }
        users[user_id] = user
    _save_users(users)
    token = _create_user_token(user_id, email)
    return user, token

def get_google_client_id() -> str:
    env_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if env_id:
        return env_id
    auth = _load_admin_auth()
    return auth.get("google_client_id", "").strip()

def set_google_client_id(client_id: str) -> bool:
    auth = _load_admin_auth()
    auth["google_client_id"] = str(client_id or "").strip()
    ADMIN_AUTH_FILE.write_text(json.dumps(auth, indent=2), encoding="utf-8")
    return True


# ── Live Analytics & Traffic Inflow/Outflow Engine ──────────────────────────

_analytics_lock = threading.Lock()

def _load_analytics_raw() -> Dict[str, Any]:
    if not ANALYTICS_FILE.is_file():
        return {
            "daily": {},
            "recent_events": [],
            "top_topics": {},
            "link_clicks": {"telegram": 0, "youtube": 0},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    try:
        return json.loads(ANALYTICS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "daily": {},
            "recent_events": [],
            "top_topics": {},
            "link_clicks": {"telegram": 0, "youtube": 0},
            "created_at": datetime.now(timezone.utc).isoformat()
        }

def _save_analytics_raw(data: Dict[str, Any]):
    _atomic_write_json(ANALYTICS_FILE, data)

THEME_KEYWORDS = [
    ("Faith & Trust", ["faith", "trust", "believ", "doubt", "fear"]),
    ("Prayer & Fellowship", ["prayer", "pray", "fasting", "fellowship", "intercession"]),
    ("The Devotional Life", ["devotion", "quiet time", "study the word", "scripture", "bible"]),
    ("Mind Renewal & Thought Life", ["mind", "thought", "renew", "mental", "focus", "discipline"]),
    ("Christian Profession & Words", ["profession", "confession", "homologia", "words", "tongue", "speak"]),
    ("Wisdom & Guidance", ["wisdom", "guidance", "decision", "direction", "discernment", "lead"]),
    ("Spiritual Growth & Fruit", ["growth", "mature", "fruit", "consecrat", "holiness", "flesh"]),
    ("Work, Career & Calling", ["work", "career", "calling", "gift", "purpose", "business", "job"]),
    ("Prosperity & Giving", ["money", "giving", "tithe", "wealth", "prosper", "financial"]),
    ("Relationships & Marriage", ["marriage", "relationship", "spouse", "dating", "family", "parent"]),
    ("Church & Headship", ["church", "headship", "pastor", "ministry", "serving", "landscape"]),
]

def classify_topics(text: str) -> List[str]:
    lower = text.lower()
    matched = []
    for category, kw_list in THEME_KEYWORDS:
        if any(kw in lower for kw in kw_list):
            matched.append(category)
    if not matched:
        matched.append("General Spiritual Guidance")
    return matched

def record_analytics_event(event_type: str, data: Dict[str, Any], client_ip: str = ""):
    """Safely log visitor sessions, chat questions, and media outbound clicks."""
    with _analytics_lock:
        analytics = _load_analytics_raw()
        now_dt = datetime.now(timezone.utc)
        today = now_dt.strftime("%Y-%m-%d")
        now_iso = now_dt.isoformat()
        
        # Salted IP hash for unique daily visitor tracking without storing personal IP
        salt = today.encode()
        ip_hash = hashlib.sha256(salt + (client_ip or "anonymous").encode()).hexdigest()[:10]
        
        daily = analytics.setdefault("daily", {}).setdefault(today, {
            "visitors": [],
            "pageviews": 0,
            "chats": 0,
            "stream_tokens": 0,
            "telegram_clicks": 0,
            "youtube_clicks": 0,
            "saves": 0,
            "categories": {}
        })
        
        if ip_hash not in daily["visitors"]:
            daily["visitors"].append(ip_hash)
            
        if event_type == "pageview":
            daily["pageviews"] = daily.get("pageviews", 0) + 1
        elif event_type == "chat":
            daily["chats"] = daily.get("chats", 0) + 1
            query = data.get("query", "").strip()
            if query:
                topics = classify_topics(query)
                for cat in topics:
                    daily.setdefault("categories", {})[cat] = daily["categories"].get(cat, 0) + 1
                    analytics.setdefault("top_topics", {})[cat] = analytics["top_topics"].get(cat, 0) + 1
        elif event_type == "click":
            link_type = data.get("link_type", "").lower()
            if "youtube" in link_type:
                daily["youtube_clicks"] = daily.get("youtube_clicks", 0) + 1
                analytics.setdefault("link_clicks", {})["youtube"] = analytics["link_clicks"].get("youtube", 0) + 1
            elif "telegram" in link_type:
                daily["telegram_clicks"] = daily.get("telegram_clicks", 0) + 1
                analytics.setdefault("link_clicks", {})["telegram"] = analytics["link_clicks"].get("telegram", 0) + 1
        elif event_type == "save_thread":
            daily["saves"] = daily.get("saves", 0) + 1
            
        # Recent activity stream (keep last 50 events)
        recent = analytics.setdefault("recent_events", [])
        recent.insert(0, {
            "type": event_type,
            "time": now_iso,
            "summary": data.get("summary", ""),
            "detail": data.get("detail", "")
        })
        analytics["recent_events"] = recent[:50]
        
        # Keep last 90 days in daily
        if len(analytics["daily"]) > 90:
            sorted_days = sorted(analytics["daily"].keys())
            for d in sorted_days[:-90]:
                del analytics["daily"][d]
                
        _save_analytics_raw(analytics)

def get_analytics_dashboard_data() -> Dict[str, Any]:
    with _analytics_lock:
        analytics = _load_analytics_raw()
        users = _load_users()
        feedbacks = _load_feedbacks()
        
    now_dt = datetime.now(timezone.utc)
    today = now_dt.strftime("%Y-%m-%d")
    daily = analytics.get("daily", {})
    
    # Calculate daily chart data for past 14 days
    last_14_days = []
    for i in range(13, -1, -1):
        d_str = (now_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        d_data = daily.get(d_str, {})
        last_14_days.append({
            "date": d_str,
            "label": (now_dt - timedelta(days=i)).strftime("%b %d"),
            "visitors": len(d_data.get("visitors", [])),
            "pageviews": d_data.get("pageviews", 0),
            "chats": d_data.get("chats", 0),
            "telegram_clicks": d_data.get("telegram_clicks", 0),
            "youtube_clicks": d_data.get("youtube_clicks", 0)
        })
        
    today_data = daily.get(today, {})
    total_lifetime_chats = sum(d.get("chats", 0) for d in daily.values())
    total_lifetime_pageviews = sum(d.get("pageviews", 0) for d in daily.values())
    total_lifetime_tg = sum(d.get("telegram_clicks", 0) for d in daily.values()) + analytics.get("link_clicks", {}).get("telegram", 0)
    total_lifetime_yt = sum(d.get("youtube_clicks", 0) for d in daily.values()) + analytics.get("link_clicks", {}).get("youtube", 0)
    
    # Calculate members count & active saved threads
    total_members = len(users)
    google_members = sum(1 for u in users.values() if u.get("provider") == "google")
    email_members = total_members - google_members
    total_threads = sum(len(u.get("threads", [])) for u in users.values())
    total_bookmarks = sum(len(u.get("bookmarks", [])) for u in users.values())
    
    # Sort top spiritual topics
    topic_counts = analytics.get("top_topics", {})
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "ok": True,
        "summary": {
            "today_visitors": len(today_data.get("visitors", [])),
            "today_chats": today_data.get("chats", 0),
            "today_pageviews": today_data.get("pageviews", 0),
            "total_lifetime_chats": total_lifetime_chats,
            "total_lifetime_pageviews": total_lifetime_pageviews,
            "total_members": total_members,
            "google_members": google_members,
            "email_members": email_members,
            "total_saved_threads": total_threads,
            "total_bookmarks": total_bookmarks,
            "telegram_clicks": total_lifetime_tg,
            "youtube_clicks": total_lifetime_yt,
            "total_feedbacks": len(feedbacks)
        },
        "chart_days": last_14_days,
        "top_topics": [{"topic": k, "count": v} for k, v in sorted_topics],
        "recent_activity": analytics.get("recent_events", [])[:20]
    }
