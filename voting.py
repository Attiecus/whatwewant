import streamlit as st
import requests
import spacy
from opencage.geocoder import OpenCageGeocode
from bs4 import BeautifulSoup
import feedparser
import aiohttp
import asyncio
import hashlib
import time
from streamlit_cookies_manager import EncryptedCookieManager
import json
import firebase_admin
from firebase_admin import credentials, auth
from firebase_admin._auth_utils import UserNotFoundError, EmailAlreadyExistsError
from datetime import datetime, timedelta
from PIL import Image
from urllib.parse import urlencode, parse_qs, urlparse
import random

# Initialize cookie manager
st.set_page_config(layout='wide', page_title='Echo', initial_sidebar_state='collapsed')

# Check if Firebase app is already initialized
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("echo-73aeb-firebase-adminsdk-5cxbo-01aa7691b8.json")
        firebase_admin.initialize_app(cred)
    except ValueError as e:
        st.error(f"Firebase initialization error: {e}")
        st.stop()

# Initialize cookie manager with password
cookies = EncryptedCookieManager(prefix="echo_app_", password="this_is_a_secret_key")
if not cookies.ready():
    st.stop()

# Function to hash passwords (if needed for comparison)
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Check if user is logged in
def check_login():
    if "user" in st.session_state:
        if "voted_articles" not in st.session_state:
            voted_articles_cookie = cookies.get("voted_articles", "[]")  # Default to an empty JSON list
            try:
                st.session_state["voted_articles"] = json.loads(voted_articles_cookie)
                if not isinstance(st.session_state["voted_articles"], list):
                    st.session_state["voted_articles"] = []
            except json.JSONDecodeError:
                st.session_state["voted_articles"] = []  # Fallback to an empty list if decoding fails
        return True
    else:
        user_id = cookies.get("user")
        if user_id:
            st.session_state["user"] = user_id
            st.session_state["username"] = cookies.get("anonymous_name")
            st.session_state["voted_articles"] = json.loads(cookies.get("voted_articles", "[]"))
            return True
        return False

# Register function using Firebase Authentication
def register_anonymous():
    st.markdown("<h2 style='text-align: center;'>Register as Anonymous</h2>", unsafe_allow_html=True)
    
    try:
        if st.button("Register as Anonymous", key="anonymous_register_button"):
            anonymous_id = cookies.get("anonymous_id")
            if not anonymous_id:
                anonymous_id = hashlib.sha256(str(time.time()).encode()).hexdigest()
                random_name = f"User{random.randint(1000, 9999)}"
                cookies["anonymous_id"] = anonymous_id
                cookies["anonymous_name"] = random_name
                cookies.save()
            try:
                # Check if the user already exists
                try:
                    user = auth.get_user(anonymous_id)
                    st.warning("Anonymous user ID already exists. Logging in with existing ID.")
                    st.session_state["user"] = anonymous_id
                    st.session_state["username"] = cookies.get("anonymous_name")
                    st.session_state["voted_articles"] = json.loads(cookies.get("voted_articles", "[]"))
                    cookies["user"] = anonymous_id
                    cookies.save()
                    st.session_state['page'] = "Main"  # Set the page to Main after successful login
                    st.experimental_rerun()
                except UserNotFoundError:
                    user = auth.create_user(uid=anonymous_id)
                    st.session_state["user"] = anonymous_id
                    st.session_state["username"] = cookies.get("anonymous_name")
                    st.session_state["voted_articles"] = []
                    st.success("Registered anonymously!")
                    cookies["user"] = anonymous_id
                    cookies.save()
                    st.session_state['page'] = "Main"  # Set the page to Main after successful anonymous registration
                    st.experimental_rerun()
            except EmailAlreadyExistsError as e:
                st.error(f"Error: {e}")

    except st.errors.DuplicateWidgetID:
        st.warning("Please click the register button again to confirm.")

# Logout function
def logout():
    if st.sidebar.button("Logout", key="logout_button"):
        st.session_state.pop("user")
        st.session_state.pop("voted_articles")
        st.session_state.pop("username")
        cookies["user"] = ""
        cookies.save()
        st.experimental_rerun()

def track_vote(article_id):
    if "voted_articles" not in st.session_state or not isinstance(st.session_state["voted_articles"], list):
        st.session_state["voted_articles"] = []

    if article_id not in st.session_state["voted_articles"]:
        st.session_state["voted_articles"].append(article_id)
        cookies["voted_articles"] = json.dumps(st.session_state["voted_articles"])
        cookies.save()
        return True
    else:
        st.warning("You have already voted on this article.")
        return False

# Tutorial function
def tutorial():
    st.markdown("<h2 style='text-align: center;'>Welcome to ECHO!</h2>", unsafe_allow_html=True)
    st.write("""
    **ECHO** is a platform designed to give you a voice on trending news topics, especially in a world where voices are often unheard or suppressed by those in power. Here's how it works:
    
    1. **Browse News Articles**: Find news articles from various sources.
    2. **UPROAR on News**: Vote on news articles by sharing your opinion through polls.
    3. **See Results**: View how others have voted and the geographical distribution of votes.

    **Why ECHO?**

    In an era where the mainstream media is often controlled by powerful entities, it can be difficult for ordinary people to make their voices heard. ECHO empowers you to speak out on news channels about what you stand for, without the fear of being exposed or censored. Your voice matters, and ECHO ensures it is heard.

    **Getting Started**:
    - **Register**: Sign up with your email, or register anonymously to protect your identity.
    - **Login**: Log in to start voting and saving articles.
    
    **Features**:
    - **Search Articles**: Use the search bar to find articles by keywords.
    - **Save Articles**: Save articles to read later.
    - **Share Opinions**: Share your opinions on social media directly from the platform.

    **Our Commitment**:
    - **Anonymity**: Register anonymously if you wish, ensuring your identity is protected.
    - **Freedom of Speech**: Share your opinions without fear of censorship.
    - **Community Engagement**: See how others feel about the same topics and participate in a global conversation.

    Enjoy using **ECHO** and make your voice heard!
    """)

    if st.button("Read less"):
        st.session_state['page'] = "Main"
        st.experimental_rerun()

def filter_articles_by_date(feed, days=2):
    filtered_entries = []
    current_time = datetime.now()
    for entry in feed.entries:
        published_time = datetime(*entry.published_parsed[:6])
        if current_time - timedelta(days=days) <= published_time <= current_time:
            filtered_entries.append(entry)
    return filtered_entries

def create_social_media_share_button(article_title, post_id):
    website_url = f"https://voices.streamlit.app?post_id={post_id}"
    twitter_url = f"https://twitter.com/intent/tweet?url={website_url}&text={article_title}"
    facebook_url = f"https://www.facebook.com/sharer/sharer.php?u={website_url}"
    linkedin_url = f"https://www.linkedin.com/shareArticle?mini=true&url={website_url}&title={article_title}"
    instagram_url = f"https://www.instagram.com/?url={website_url}"

    buttons_html = f"""
    <div class="dropdown" style="display: inline-block; margin-left: 10px;">
        <button class="dropbtn">
            <img src="https://img.icons8.com/material-outlined/24/000000/share.png" alt="Share Icon" style="vertical-align: middle; margin-right: 5px;"/>
            -
        </button>
        <div class="dropdown-content">
            <a href="{twitter_url}" target="_blank">Twitter</a>
            <a href="{facebook_url}" target="_blank">Facebook</a>
            <a href="{linkedin_url}" target="_blank">LinkedIn</a>
            <a href="{instagram_url}" target="_blank">Instagram</a>
        </div>
    </div>

    <style>
        .dropdown {{
            position: relative;
            display: inline-block;
        }}

        .dropbtn {{
            background-color: white;
            color: black;
            padding: 10px 16px;
            font-size: 14px;
            border: none;
            cursor: pointer;
            border-radius: 9px;
            display: flex;
            align-items: center;
        }}

        .dropdown-content {{
            display: none;
            position: absolute;
            background-color: #f9f9f9;
            min-width: 160px;
            box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
            z-index: 1;
            border-radius: 10px;
        }}

        .dropdown-content a {{
            color: black;
            padding: 12px 16px;
            text-decoration: none;
            display: block;
        }}

        .dropdown-content a:hover {{
            background-color: #f1f1f1;
        }}

        .dropdown:hover .dropdown-content {{
            display: block;
        }}

        .dropdown:hover .dropbtn {{
            background-color: #e6e6e6;
        }}

        .card-container {{
            position: relative;
        }}

        .button-container {{
            display: flex;
            justify-content: flex-end;
            align-items: center;
            margin-top: 10px;
        }}
    </style>
    """
    st.markdown(buttons_html, unsafe_allow_html=True)

st.markdown("""
    <style>
    .stButton > button {
        display: block;
        margin-left: auto;
        margin-right: auto;
        width: 50%;
    }
    </style>
    """, unsafe_allow_html=True)

def create_poll_with_options(article_id, options):
    vote_key = f"votes_{article_id}"

    if vote_key not in st.session_state:
        st.session_state[vote_key] = {option: 0 for option in options}

    votes = st.session_state[vote_key]

    st.write("Choose your stance on this news:")
    custom_option = st.text_input(f"Enter a custom option for this article:", key=f"custom_option_{article_id}_input")
    if custom_option:
        if st.button(f"Add custom option", key=f"add_custom_option_{article_id}_button"):
            if custom_option not in options:
                options.append(custom_option)
                votes[custom_option] = 0
            if track_vote(article_id):
                votes[custom_option] += 1
                st.session_state[vote_key] = votes
                st.write(f"Your stance: {custom_option}")

    for option in options:
        if st.button(option, key=f"vote_button_{article_id}_{option}"):
            if track_vote(article_id):
                votes[option] += 1
                st.session_state[vote_key] = votes
                st.write(f"Your stance: {option}")

    st.write("---")

    if any(count > 0 for count in votes.values()):
        st.write("Current Poll Results:")
        total_votes = sum(votes.values())
        for option, count in votes.items():
            percentage = count / total_votes * 100 if total_votes != 0 else 0
            st.write(f"{option}: {count} votes ({percentage:.2f}% of total)")
            st.progress(percentage / 100)
        st.write("---")

def main():
    # Display loading screen with logo
    st.markdown(
        """
        <style>
        .loading-container {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            flex-direction: column;
        }
        .loading-logo {
            width: 50%;
        }
        </style>
        """, unsafe_allow_html=True
    )

    st.markdown('<div class="loading-container"><img src="logo.png" class="loading-logo" alt="Logo"></div>', unsafe_allow_html=True)
    time.sleep(2)  # Display loading screen for 2 seconds

    # Set default mode
    if 'dark_mode' not in st.session_state:
        st.session_state['dark_mode'] = False

    # Check login state using cookies
    if check_login():
        st.sidebar.write(f"Welcome, {st.session_state['username']}!")
        logout()
    else:
        if 'page' not in st.session_state:
            st.session_state['page'] = "Main"

    if st.session_state['page'] == "Register":
        register_anonymous()
        return

    @st.cache_resource
    def load_spacy_model():
        return spacy.load("en_core_web_lg")

    async def fetch_article_content_async(session, url):
        async with session.get(url) as response:
            content = await response.read()
            soup = BeautifulSoup(content, 'lxml')  # Use lxml for faster parsing

            paragraphs = soup.find_all('p')
            content = ' '.join([para.get_text() for para in paragraphs]) if paragraphs else 'Content not available'

            image = None
            img_tag = soup.find('meta', property='og:image')
            if img_tag and img_tag['content']:
                image = img_tag['content']
            else:
                img_tag = soup.find('img')
                if img_tag and img_tag['src']:
                    image = img_tag['src']

            return content, image

    async def fetch_articles(urls):
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_article_content_async(session, url) for url in urls]
            return await asyncio.gather(*tasks)

    OPENCAGE_API_KEY = 'dcbeeba6d26b4628bef1806606c11c21'  # Replace with your OpenCage API key
    geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

    @st.cache_data
    def extract_relevant_entities(text):
        nlp = load_spacy_model()
        doc = nlp(text)
        entities = [ent.text for ent in doc.ents if ent.label_ in ['PERSON', 'ORG', 'GPE']]
        return list(set(entities))

    def determine_poll_type(article):
        if "policy" in article['title'].lower() or "election" in article['title'].lower():
            return "yes_no"
        else:
            return "entity_based"

    @st.cache_data
    def get_user_location(api_key):
        response = requests.get(f'https://ipinfo.io/json?token={api_key}')
        return response.json()

    @st.cache_data
    def get_country_coordinates(country_name):
        result = geocoder.geocode(country_name)
        if result and len(result):
            return result[0]['geometry']['lat'], result[0]['geometry']['lng']
        return None, None

    def plot_world_map(location_votes):
        data = []
        for country, votes in location_votes.items():
            lat, lon = get_country_coordinates(country)
            if lat and lon:
                for _ in range(votes):
                    data.append({'lat': lat, 'lon': lon})
        return data

    def toggle_dark_light_mode():
        st.session_state['dark_mode'] = st.sidebar.checkbox("Dark Mode", value=st.session_state['dark_mode'])
        return st.session_state['dark_mode']

    def set_custom_css(dark_mode):
        css = """
        <style>
            h1 {
                font-family: 'Garamond';
                font-weight: bold;
                font-size: 7em;
                text-align: center;
            }
            h2 {
                font-family: 'Boston';
                font-weight: bold;
                text-align: center;
                font-size:2em
            }
            @media (max-width: 768px) {
                h1 {
                    font-size: 2em;
                }
                h2 {
                    font-size: 1.5em;
                }
            }
        </style>
        """
        dark_css = """
        <style>
            body {
                background-color: #000000;
                color: #ffffff;
            }
            a {
                color: #1E90FF;
            }
            .stButton button {
                background-color: #444444;
                color: #ffffff;
            }
            .stTextInput input {
                background-color: #444444;
                color: #ffffff;
            }
        </style>
        """
        light_css = """
        <style>
            body {
                background-color: #ffffff;
                color: #000000;
            }
            a {
                color: #1E90FF;
            }
            .stButton button {
                background-color: #f0f0f0;
                color: #000000;
            }
            .stTextInput input {
                background-color: #ffffff;
                color: #000000;
            }
        </style>
        """
        if dark_mode:
            st.markdown(dark_css, unsafe_allow_html=True)
        else:
            st.markdown(light_css, unsafe_allow_html=True)
        st.markdown(css, unsafe_allow_html=True)

    def search_articles(entries, query):
        if not query:
            return entries
        filtered_entries = []
        for entry in entries:
            if query.lower() in entry.title.lower() or query.lower() in entry.summary.lower():
                filtered_entries.append(entry)
        return filtered_entries

    dark_mode = toggle_dark_light_mode()
    set_custom_css(dark_mode)

    # Display the logo image centered and large
    st.markdown(
        """
        <style>
        .centered-logo {
            display: block;
            margin-left: auto;
            margin-right: auto;
            width: 60%;  /* Adjust the width to make the image bigger */
            margin-top: 20px;  /* Adjust the margin to lower the image */
            margin-bottom: -20px;  /* Adjust the margin to reduce the gap */
        }
        </style>
        """, 
        unsafe_allow_html=True
    )
    st.image("logo.png", use_column_width=True, width=500, output_format="PNG", caption="")
    st.header("HAVE YOUR SAY")

    user_query = st.text_input("Search for articles containing:", key="article_search")
    news_sources = {
        "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
        "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
        "RTE": "https://www.rte.ie/rss/news.xml",
        "Al Jazeera": "http://www.aljazeera.com/xml/rss/all.xml",
        "Sky Sports": "https://www.skysports.com/rss/12040",  # Sky Sports RSS feed
        "Business Insider": "https://www.businessinsider.com/rss"  # Business Insider RSS feed
    }

    news_source = st.selectbox("Select news source:", list(news_sources.keys()))
    feed_url = news_sources[news_source]

    if st.button("Reload Feed"):
        feed = feedparser.parse(feed_url)
    else:
        feed = feedparser.parse(feed_url)

    with st.sidebar:
        st.header("Saved Articles")
        st.write("*Warning: Your saved articles are only for this session and will be deleted once the session is over! To ensure you have your articles saved, please sign up or log in.")
        st.sidebar.header("About us:")
        tut_button = st.sidebar.button("Read here")
        if tut_button:
            tutorial()

        if 'saved_posts' not in st.session_state:
            st.session_state.saved_posts = []
        saved_posts = st.session_state.saved_posts
        if saved_posts:
            for idx, post in enumerate(saved_posts):
                if st.button(f"Unsave", key=f"remove_{idx}"):
                    st.session_state.saved_posts = [p for p in saved_posts if p['link'] != post['link']]
                    st.experimental_rerun()
                st.markdown(f"### [{post['title']}]({post['link']})")
                st.markdown(f"{post['summary']}")
        else:
            st.write("No articles saved.")

    # Filter articles by date (past 2 days)
    filtered_entries = filter_articles_by_date(feed, days=2)
    # Further filter articles based on user query
    filtered_entries = search_articles(filtered_entries, user_query)
    if filtered_entries:
        num_cols = min(len(filtered_entries), 3)
        cols = st.columns(num_cols)

        urls = [entry.link for entry in filtered_entries]
        articles = asyncio.run(fetch_articles(urls))

        for idx, (entry, (content, image)) in enumerate(zip(filtered_entries, articles)):
            col = cols[idx % num_cols]
            with col:
                with st.container():
                    article_url = entry.link
                    post_id = hashlib.md5(article_url.encode()).hexdigest()  # Generate unique post ID

                    card_color = "#444444" if dark_mode else "#f9f9f9"
                    text_color = "#ffffff" if dark_mode else "#000000"

                    card_html = f"""
                    <div class="card" style="background-color: {card_color}; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                        <h3><a href="{entry.link}" style="color: {text_color}; text-decoration: none;">{entry.title}</a></h3>
                        <p style="color: {text_color};">{entry.summary}</p>
                    """
                    if image:
                        card_html += f'<img src="{image}" alt="Article Image" style="width:100%; border-radius: 10px; margin-bottom: 10px;"/>'

                    card_html += "</div>"
                    st.markdown(card_html, unsafe_allow_html=True)

                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col3:
                        if st.button(":arrow_down:", key=f"save_{idx}"):
                            st.session_state.saved_posts.append({
                                'title': entry.title,
                                'summary': entry.summary,
                                'link': article_url
                            })
                            st.success(f"Saved {entry.title}")
                            st.experimental_rerun()
                    
                    with col1:
                        create_social_media_share_button(entry.title, post_id)

                    if content:
                        poll_type = determine_poll_type({'title': entry.title, 'description': entry.summary})
                        if poll_type == "yes_no":
                            options = ["Yes", "No"]
                        else:
                            relevant_entities = extract_relevant_entities(content)
                            entity_counts = {entity: relevant_entities.count(entity) for entity in set(relevant_entities)}
                            sorted_entities = sorted(entity_counts.items(), key=lambda x: 1, reverse=True)
                            options = [entity[0] for entity in sorted_entities[:5]]

                        hashtag_options = [f"#{option.replace(' ', '')}" for option in options]

                        if options:
                            if check_login():
                                create_poll_with_options(entry.link, hashtag_options)
                            else:
                                st.warning("Please register anonymously to have your say")
                                if st.button("Register as Anonymous", key=f"register_anonymous_{idx}"):
                                    st.write("*Dont worry all users will remain anonymous,your data is yours")
                                    st.session_state['page'] = "Register"
                                    st.experimental_rerun()
                        else:
                            st.write("No relevant entities found for voting.")

                    else:
                        st.write("No content available for deeper analysis.")
    else:
        st.error("Failed to fetch trending news.")

st.markdown("""
<style>
    .card {
        border: 1px solid #ccc;
        border-radius: 10px;
        padding: 20px;
        margin: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        transition: transform 0.3s ease-in-out;
    }
    .card:hover {
        transform: scale(1.05);
    }
</style>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
