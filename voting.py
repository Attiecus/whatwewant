import streamlit as st
import requests
import spacy
from bs4 import BeautifulSoup
import feedparser
import aiohttp
import asyncio
import hashlib
import time
from streamlit_cookies_controller import CookieController
import json
from datetime import datetime, timedelta
from PIL import Image
import random
from colorthief import ColorThief
from io import BytesIO
import sqlite3
import html
from urllib.parse import quote


# ─────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="EKO", page_icon="🗣️")


# ─────────────────────────────────────────────────────────────────
# Cookie controller
# ─────────────────────────────────────────────────────────────────
controller = CookieController()


# ─────────────────────────────────────────────────────────────────
# SQLite database
# ─────────────────────────────────────────────────────────────────
DB_PATH = "eko_votes.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS article_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            article_url TEXT NOT NULL,
            article_title TEXT,
            option_text TEXT NOT NULL,
            vote_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(article_id, option_text)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            user_fingerprint TEXT NOT NULL,
            option_text TEXT NOT NULL,
            voted_at TEXT NOT NULL,
            UNIQUE(article_id, user_fingerprint)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ─────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────
def extract_image_from_entry(entry):
    """
    Try every standard RSS/Atom image field before falling back to page scraping.
    """
    mt = getattr(entry, "media_thumbnail", None)
    if mt and isinstance(mt, list) and mt[0].get("url"):
        return mt[0]["url"]

    mc = getattr(entry, "media_content", None)
    if mc and isinstance(mc, list):
        for m in mc:
            t = m.get("type", "") or m.get("medium", "")
            url = m.get("url", "")
            if "image" in t or url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return url

    enc = getattr(entry, "enclosures", None)
    if enc:
        for e in enc:
            if "image" in e.get("type", ""):
                return e.get("href") or e.get("url")

    summary = entry.get("summary", "") or entry.get("description", "")
    if "<img" in summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    for c in entry.get("content", []):
        if "<img" in c.get("value", ""):
            soup = BeautifulSoup(c["value"], "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                return img["src"]

    return None


@st.cache_data(ttl=300, show_spinner=False)
def scrape_article_image(url: str) -> str | None:
    """Last resort: scrape the article page for og:image. Cached for 5 minutes."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.content, "lxml")

        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]

        img = soup.find("img", src=True)
        return img["src"] if img else None

    except Exception:
        return None


def get_dominant_colors(image_url, num_colors=3):
    try:
        r = requests.get(image_url, timeout=5)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.save("temp_image.jpg")
        ct = ColorThief("temp_image.jpg")
        return ct.get_palette(color_count=num_colors)
    except Exception:
        return [(30, 30, 60), (79, 70, 229), (129, 140, 248)]


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def create_css_gradient(colors):
    return f"linear-gradient(135deg, {', '.join(rgb_to_hex(c) for c in colors)})"


# ─────────────────────────────────────────────────────────────────
# Anonymous identity helpers: Firebase-free
# ─────────────────────────────────────────────────────────────────
def get_client_ip():
    """
    Best-effort client IP capture.

    Notes:
    - On local machine, this may return 'unknown_ip'.
    - On hosted apps, IP may come through reverse proxy headers.
    - IP alone is not a perfect identity, so this app combines it with a browser cookie.
    """
    try:
        headers = st.context.headers

        forwarded_for = headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        remote_addr = headers.get("Remote-Addr")
        if remote_addr:
            return remote_addr.strip()

    except Exception:
        pass

    return "unknown_ip"


def get_or_create_user_id():
    """
    Creates a stable anonymous browser ID using a cookie.
    The IP is stored only as a supporting signal.
    """
    uid = controller.get("user_id")

    if not uid:
        client_ip = get_client_ip()
        raw_id = f"{client_ip}_{time.time()}_{random.randint(1000, 9999)}"
        uid = hashlib.sha256(raw_id.encode()).hexdigest()

        controller.set("user_id", uid)
        controller.set("user_ip", client_ip)

    return uid


user_id = get_or_create_user_id()


def get_user_fingerprint():
    """
    Creates a hashed fingerprint to prevent duplicate voting.

    It uses:
    - anonymous cookie ID
    - best-effort IP address

    Raw IP is not stored directly in the voting table.
    """
    anon_id = controller.get("anonymous_id") or controller.get("user_id") or user_id
    client_ip = get_client_ip()
    raw = f"{anon_id}_{client_ip}"
    return hashlib.sha256(raw.encode()).hexdigest()


def check_login():
    if "user" not in st.session_state:
        return False

    if "voted_articles" not in st.session_state:
        raw = controller.get("voted_articles") or "[]"

        if not isinstance(raw, str):
            raw = json.dumps(raw)

        try:
            st.session_state["voted_articles"] = json.loads(raw)
        except json.JSONDecodeError:
            st.session_state["voted_articles"] = []

    return True


def register_anonymous():
    """
    Anonymous registration without Firebase.
    Uses browser cookies and best-effort IP capture.
    """
    st.markdown("<h2 style='text-align:center;'>Register anonymously</h2>", unsafe_allow_html=True)
    st.write("No email needed — your identity stays protected.")
    st.caption("Your IP address may be used only to maintain anonymous voting integrity.")

    if st.button("Continue anonymously", key="anon_reg_btn"):
        anon_id = controller.get("anonymous_id")

        if not anon_id:
            client_ip = get_client_ip()
            raw_id = f"{client_ip}_{time.time()}_{random.randint(1000, 9999)}"
            anon_id = hashlib.sha256(raw_id.encode()).hexdigest()

            controller.set("anonymous_id", anon_id)
            controller.set("user_ip", client_ip)

        random_name = controller.get("anonymous_name")

        if not random_name:
            random_name = f"User{random.randint(1000, 9999)}"
            controller.set("anonymous_name", random_name)

        controller.set("user", anon_id)

        st.session_state.update({
            "user": anon_id,
            "username": random_name,
            "voted_articles": [],
            "page": "Main",
        })

        st.success("Registered anonymously.")
        st.rerun()


def logout():
    if st.sidebar.button("Logout", key="logout_btn"):
        for k in ["user", "voted_articles", "username"]:
            st.session_state.pop(k, None)

        controller.remove("user")
        st.rerun()


# ─────────────────────────────────────────────────────────────────
# Voting database functions
# ─────────────────────────────────────────────────────────────────
def has_user_voted(article_id):
    user_fingerprint = get_user_fingerprint()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT option_text
        FROM user_votes
        WHERE article_id = ?
        AND user_fingerprint = ?
    """, (article_id, user_fingerprint))

    row = cur.fetchone()
    conn.close()

    return row["option_text"] if row else None


def record_vote(article_id, article_url, article_title, option_text):
    """
    Records one vote if the user has not already voted on the article.

    Returns True if vote was recorded.
    Returns False if user already voted.
    """
    user_fingerprint = get_user_fingerprint()
    now = datetime.now().isoformat()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # This insert enforces one vote per user per article.
        cur.execute("""
            INSERT INTO user_votes (
                article_id,
                user_fingerprint,
                option_text,
                voted_at
            )
            VALUES (?, ?, ?, ?)
        """, (article_id, user_fingerprint, option_text, now))

        # This upsert increments the public total count for the selected option.
        cur.execute("""
            INSERT INTO article_votes (
                article_id,
                article_url,
                article_title,
                option_text,
                vote_count
            )
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(article_id, option_text)
            DO UPDATE SET vote_count = vote_count + 1
        """, (article_id, article_url, article_title, option_text))

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


def get_vote_results(article_id, options=None):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT option_text, vote_count
        FROM article_votes
        WHERE article_id = ?
        ORDER BY vote_count DESC
    """, (article_id,))

    rows = cur.fetchall()
    conn.close()

    results = {row["option_text"]: row["vote_count"] for row in rows}

    if options:
        for opt in options:
            results.setdefault(opt, 0)

    return results


# ─────────────────────────────────────────────────────────────────
# Feed helpers
# ─────────────────────────────────────────────────────────────────
def filter_by_date(entries, days=3):
    now = datetime.now()
    out = []

    for e in entries:
        try:
            pub = datetime(*e.published_parsed[:6])
            if now - timedelta(days=days) <= pub <= now:
                out.append(e)
        except Exception:
            out.append(e)

    return out


@st.cache_data(ttl=300, show_spinner=False)
def fetch_feed(url: str):
    """Fetch a single RSS feed with a browser User-Agent to avoid 403s."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    try:
        r = requests.get(url, headers=headers, timeout=8)
        return feedparser.parse(r.text)
    except Exception:
        return feedparser.parse(url)


async def fetch_article_text_async(session, url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            html_content = await resp.read()
            soup = BeautifulSoup(html_content, "lxml")
            text = " ".join(p.get_text() for p in soup.find_all("p"))
            return text or ""

    except Exception:
        return ""


async def fetch_all_texts(urls):
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(*[fetch_article_text_async(session, u) for u in urls])


# ─────────────────────────────────────────────────────────────────
# NLP
# ─────────────────────────────────────────────────────────────────
@st.cache_resource
def load_nlp():
    try:
        return spacy.load("en_core_web_lg")
    except OSError:
        st.error(
            "spaCy model 'en_core_web_lg' is not installed. "
            "Run: python -m spacy download en_core_web_lg"
        )
        st.stop()


@st.cache_data(show_spinner=False)
def extract_entities(text):
    nlp = load_nlp()
    doc = nlp(text[:5000])

    return list({
        e.text
        for e in doc.ents
        if e.label_ in ["PERSON", "ORG", "GPE"]
    })


def determine_options(entry, content):
    title = entry.title.lower()

    if any(w in title for w in ["policy", "election", "vote", "bill", "law", "ban"]):
        return ["Yes", "No", "Not sure"]

    entities = extract_entities(content)

    if entities:
        counts = {e: entities.count(e) for e in set(entities)}
        top = sorted(counts, key=counts.get, reverse=True)[:5]
        return top

    return ["Support", "Oppose", "Neutral"]


# ─────────────────────────────────────────────────────────────────
# Poll UI
# ─────────────────────────────────────────────────────────────────
def create_poll(article_id, article_url, article_title, options):
    st.markdown("**Have your say:**")

    already_voted_option = has_user_voted(article_id)

    if already_voted_option:
        st.info(f"You have already voted on this article: `{already_voted_option}`")
    else:
        custom = st.text_input("Add your own stance:", key=f"custom_{article_id}")

        if custom and st.button("Add & vote", key=f"add_custom_{article_id}"):
            tag = f"#{custom.replace(' ', '')}"

            success = record_vote(
                article_id=article_id,
                article_url=article_url,
                article_title=article_title,
                option_text=tag,
            )

            if success:
                st.success("Vote recorded.")
                st.rerun()
            else:
                st.warning("You've already voted on this article.")

        cols = st.columns(min(len(options), 3))

        for i, opt in enumerate(options):
            tag = f"#{opt.replace(' ', '')}" if not opt.startswith("#") else opt

            with cols[i % 3]:
                if st.button(tag, key=f"vote_{article_id}_{opt}"):
                    success = record_vote(
                        article_id=article_id,
                        article_url=article_url,
                        article_title=article_title,
                        option_text=opt,
                    )

                    if success:
                        st.success("Vote recorded.")
                        st.rerun()
                    else:
                        st.warning("You've already voted on this article.")

    results = get_vote_results(article_id, options)
    total = sum(results.values())

    st.markdown("**Current results:**")

    if total == 0:
        st.caption("No votes yet. Be the first to vote.")
    else:
        for opt, count in sorted(results.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            st.write(f"`{opt}` — {count} vote{'s' if count != 1 else ''} ({pct:.0f}%)")
            st.progress(pct / 100)


# ─────────────────────────────────────────────────────────────────
# Tutorial page
# ─────────────────────────────────────────────────────────────────
def tutorial():
    st.markdown("## About EKO")

    st.write("""
EKO lets you vote on real news stories and see how others around the world feel about the same topics.

**How it works:**
1. Pick a news source and browse today's articles.
2. Hit UPROAR to cast your vote on any story.
3. See live results anonymously.

**Why it matters:**
Most news platforms are one-way. EKO gives the audience a way to push back, agree, or complicate the narrative. Every vote is anonymous by default.

**Getting started:** click *Continue anonymously* to register.
    """)

    if st.button("← Back"):
        st.session_state["page"] = "Main"
        st.rerun()


# ─────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────
def apply_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }

.stApp {
    background: linear-gradient(160deg, #0e0118 0%, #1a0a2e 40%, #0d0d1a 100%);
    color: #f0e8ff;
    min-height: 100vh;
}

.eko-header {
    text-align: center;
    padding: 10px 0 24px;
}

.eko-header h1 {
    font-size: 5em;
    font-weight: 700;
    background: linear-gradient(90deg, #c084fc, #818cf8, #e879f9);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -2px;
    margin: 0;
}

.eko-header p {
    color: rgba(255,255,255,0.5);
    font-size: 1.1em;
    margin-top: 4px;
}

.news-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 16px;
    transition: transform 0.2s, border-color 0.2s;
    position: relative;
    overflow: hidden;
}

.news-card:hover {
    transform: translateY(-3px);
    border-color: rgba(192,132,252,0.4);
}

.news-card img {
    width: 100%;
    border-radius: 10px;
    margin-bottom: 12px;
    object-fit: cover;
    max-height: 180px;
}

.news-card h3 {
    font-size: 1em;
    font-weight: 600;
    margin: 0 0 8px;
    line-height: 1.4;
}

.news-card h3 a {
    color: #e2d9f3;
    text-decoration: none;
}

.news-card h3 a:hover {
    color: #c084fc;
}

.news-card p {
    font-size: 0.85em;
    color: rgba(255,255,255,0.5);
    line-height: 1.5;
    margin: 0 0 12px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.news-card .meta {
    font-size: 0.75em;
    color: rgba(255,255,255,0.3);
    margin-bottom: 10px;
}

.share-btn {
    position: absolute;
    top: 12px;
    right: 12px;
}

.share-btn .dropbtn {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    color: #ccc;
    padding: 5px 10px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
}

.share-btn .dropdown-content {
    display: none;
    position: absolute;
    right: 0;
    top: 32px;
    background: #1e1535;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    min-width: 160px;
    z-index: 10;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}

.share-btn .dropdown-content a {
    color: #d4c8f0;
    padding: 10px 14px;
    display: block;
    font-size: 13px;
    text-decoration: none;
}

.share-btn .dropdown-content a:hover {
    background: rgba(255,255,255,0.06);
}

.share-btn:hover .dropdown-content {
    display: block;
}

[data-testid="stSidebar"] {
    background: #100920 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}

[data-testid="stSidebar"] * {
    color: rgba(255,255,255,0.75) !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #c084fc !important;
}

.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: opacity 0.2s, transform 0.1s !important;
}

.stButton > button:hover {
    opacity: 0.88 !important;
    transform: scale(1.02) !important;
}

.stTextInput input,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #f0e8ff !important;
    border-radius: 10px !important;
}

.stProgress > div > div {
    background: linear-gradient(90deg, #7c3aed, #c084fc) !important;
}

.source-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    background: rgba(124,58,237,0.2);
    border: 1px solid rgba(124,58,237,0.4);
    color: #c084fc;
    margin: 2px;
}
</style>

<script>
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => alert('Link copied!'));
}
</script>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Main app
# ─────────────────────────────────────────────────────────────────
def main():
    apply_css()

    st.session_state.setdefault("page", "Main")
    st.session_state.setdefault("dark_mode", True)
    st.session_state.setdefault("saved_posts", [])

    # Restore session from cookies
    if "user" not in st.session_state:
        stored_user = controller.get("user")

        if stored_user:
            st.session_state["user"] = stored_user
            st.session_state["username"] = controller.get("anonymous_name") or "Anonymous"

    if st.session_state["page"] == "Tutorial":
        tutorial()
        return

    if st.session_state["page"] == "Register":
        register_anonymous()
        return

    # Sidebar
    with st.sidebar:
        st.markdown("## 🗣️ EKO")

        if check_login():
            st.success(f"👤 {st.session_state['username']}")
            logout()
        else:
            st.warning("Not logged in")

            if st.button("Register anonymously"):
                st.session_state["page"] = "Register"
                st.rerun()

        st.markdown("---")
        st.markdown("### Saved articles")

        saved = st.session_state.saved_posts

        if saved:
            for i, post in enumerate(saved):
                st.markdown(f"[{post['title'][:50]}...]({post['link']})")

                if st.button("Remove", key=f"rm_{i}"):
                    st.session_state.saved_posts = [
                        p for p in saved
                        if p["link"] != post["link"]
                    ]
                    st.rerun()
        else:
            st.caption("No saved articles yet.")

        st.markdown("---")

        if st.button("About EKO"):
            st.session_state["page"] = "Tutorial"
            st.rerun()

    # Header
    st.markdown("""
<div class="eko-header">
    <h1>EKO</h1>
    <p>Your voice on today's news — anonymous, uncensored, global</p>
</div>
""", unsafe_allow_html=True)

    # News source picker
    NEWS_SOURCES = {
        "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
        "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
        "RTE": "https://www.rte.ie/rss/news.xml",
        "Al Jazeera": "http://www.aljazeera.com/xml/rss/all.xml",
        "ESPN": "https://www.espn.com/espn/rss/news",
        "Business Insider": "https://www.businessinsider.com/rss",
        "The Guardian": "https://www.theguardian.com/world/rss",
    }

    c1, c2 = st.columns([3, 1])

    with c1:
        selected = st.multiselect(
            "Select news sources:",
            list(NEWS_SOURCES.keys()),
            default=["Sky News", "BBC"],
        )

    with c2:
        days = st.slider("Days back", 1, 7, 3)

    show_votes = st.checkbox("Show voting section", value=True)
    search_q = st.text_input("🔍 Search articles", placeholder="e.g. climate, election…")

    if not selected:
        st.info("Select at least one news source above.")
        return

    # Fetch feeds
    with st.spinner("Fetching articles…"):
        all_entries = []

        for src in selected:
            feed = fetch_feed(NEWS_SOURCES[src])

            for e in feed.entries:
                e["_source"] = src
                all_entries.append(e)

    entries = filter_by_date(all_entries, days=days)

    # Search filter
    if search_q:
        q = search_q.lower()
        entries = [
            e for e in entries
            if q in e.get("title", "").lower()
            or q in e.get("summary", "").lower()
        ]

    if not entries:
        st.warning("No articles found for the selected sources and date range.")
        return

    st.caption(f"{len(entries)} articles · last {days} day{'s' if days != 1 else ''}")

    # Fetch article text for poll options
    with st.spinner("Loading article content…"):
        urls = [e.link for e in entries]

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            texts = loop.run_until_complete(fetch_all_texts(urls))
        except Exception:
            texts = [""] * len(entries)

    # Article grid
    cols = st.columns(3)

    for idx, (entry, content) in enumerate(zip(entries, texts)):
        col = cols[idx % 3]

        article_url = entry.link
        article_title = entry.title
        article_id = hashlib.md5(article_url.encode()).hexdigest()
        source = entry.get("_source", "")

        image_url = extract_image_from_entry(entry)

        if not image_url:
            image_url = scrape_article_image(article_url)

        safe_url = html.escape(article_url, quote=True)
        safe_title = html.escape(article_title, quote=True)
        safe_source = html.escape(source, quote=True)
        js_safe_url = quote(article_url, safe="")

        tw = f"https://twitter.com/intent/tweet?url={safe_url}&text={safe_title}"
        fb = f"https://www.facebook.com/sharer/sharer.php?u={safe_url}"
        li = f"https://www.linkedin.com/shareArticle?mini=true&url={safe_url}&title={safe_title}"

        img_html = ""

        if image_url:
            safe_img_url = html.escape(image_url, quote=True)
            img_html = (
                f'<img src="{safe_img_url}" alt="" '
                f'onerror="this.style.display=\'none\'" />'
            )

        summary = entry.get("summary", "")
        clean_summary = BeautifulSoup(summary, "html.parser").get_text()[:200]
        safe_summary = html.escape(clean_summary, quote=True)

        card_html = f"""
<div class="news-card">
    {img_html}
    <div class="meta">
        <span class="source-pill">{safe_source}</span>
    </div>
    <h3><a href="{safe_url}" target="_blank">{safe_title}</a></h3>
    <p>{safe_summary}…</p>
    <div class="share-btn">
        <button class="dropbtn">Share ▾</button>
        <div class="dropdown-content">
            <a href="#" onclick="copyToClipboard(decodeURIComponent('{js_safe_url}'))">📋 Copy link</a>
            <a href="{tw}" target="_blank">🐦 Twitter</a>
            <a href="{fb}" target="_blank">📘 Facebook</a>
            <a href="{li}" target="_blank">💼 LinkedIn</a>
        </div>
    </div>
</div>
"""

        with col:
            st.markdown(card_html, unsafe_allow_html=True)

            if st.button("💾 Save", key=f"save_{idx}"):
                if not any(p["link"] == article_url for p in st.session_state.saved_posts):
                    st.session_state.saved_posts.append({
                        "title": article_title,
                        "link": article_url,
                    })
                    st.success("Saved.")
                else:
                    st.info("Already saved.")

            if show_votes:
                if check_login():
                    options = determine_options(entry, content)

                    with st.expander("🗣️ UPROAR — have your say"):
                        create_poll(
                            article_id=article_id,
                            article_url=article_url,
                            article_title=article_title,
                            options=options,
                        )
                else:
                    st.caption("Register anonymously to vote.")

                    if st.button("Join the conversation", key=f"join_{idx}"):
                        st.session_state["page"] = "Register"
                        st.rerun()

            st.markdown("---")


if __name__ == "__main__":
    main()
