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

# Initialize cookie manager
st.set_page_config(layout='wide')

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
        return False

# Login function using Firebase Authentication
def login():
    st.markdown("<h1 style='font-family: Garamond; font-weight: bold; font-size: 5em; text-align: center;'>-ECHO-</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>Login</h2>", unsafe_allow_html=True)
    username = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login", key="login_button"):
        try:
            user = auth.get_user_by_email(username)
            user_token = auth.create_custom_token(user.uid)
            st.session_state["user"] = username
            st.session_state["voted_articles"] = cookies.get("voted_articles", [])
            st.success("Logged in successfully!")
            cookies["user"] = username
            cookies.save()
            st.session_state['page'] = "Main"  # Set the page to Main after successful login
            st.experimental_rerun()
        except UserNotFoundError:
            st.error("Invalid email or password")

# Register function using Firebase Authentication
def register():
    st.markdown("<h2 style='text-align: center;'>Sign-up</h2>", unsafe_allow_html=True)
    
    if st.button("Register as Anonymous", key="anonymous_register_button"):
        anonymous_id = cookies.get("anonymous_id")
        if not anonymous_id:
            anonymous_id = hashlib.sha256(str(time.time()).encode()).hexdigest()
            cookies["anonymous_id"] = anonymous_id
            cookies.save()
        try:
            # Check if the user already exists
            try:
                user = auth.get_user(anonymous_id)
                st.warning("Anonymous user ID already exists. Logging in with existing ID.")
                st.session_state["user"] = anonymous_id
                st.session_state["voted_articles"] = json.loads(cookies.get("voted_articles", "[]"))
                cookies["user"] = anonymous_id
                cookies.save()
                st.session_state['page'] = "Main"  # Set the page to Main after successful login
                st.experimental_rerun()
            except UserNotFoundError:
                user = auth.create_user(uid=anonymous_id)
                st.session_state["user"] = anonymous_id
                st.session_state["voted_articles"] = []
                st.success("Registered anonymously!")
                cookies["user"] = anonymous_id
                cookies.save()
                st.session_state['page'] = "Main"  # Set the page to Main after successful anonymous registration
                st.experimental_rerun()
        except EmailAlreadyExistsError as e:
            st.error(f"Error: {e}")

    else:
        username = st.text_input("Email", key="register_email")
        password = st.text_input("Password", type="password", key="register_password")
        if st.button("Register", key="register_button"):
            try:
                user = auth.create_user(email=username, password=password)
                st.success("Registered successfully! You can now log in.")
            except EmailAlreadyExistsError as e:
                st.error(f"Error: {e}")

# Logout function
def logout():
    if st.sidebar.button("Logout", key="logout_button"):
        st.session_state.pop("user")
        st.session_state.pop("voted_articles")
        cookies["user"] = ""
        cookies.save()
        st.experimental_rerun()

# Ensure unique keys for each article's widgets
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

    # Display poll options as buttons
    for option in options:
        if st.button(option, key=f"vote_button_{article_id}_{option}"):
            if track_vote(article_id):
                votes[option] += 1
                st.session_state[vote_key] = votes
                st.write(f"Your stance: {option}")

    st.write("---")

    # Display poll results
    if any(count > 0 for count in votes.values()):
        st.write("Current Poll Results:")
        total_votes = sum(votes.values())
        for option, count in votes.items():
            percentage = count / total_votes * 100 if total_votes != 0 else 0
            st.write(f"{option}: {count} votes ({percentage:.2f}% of total)")
            st.progress(percentage / 100)
        st.write("---")

# Define filter_articles_by_date function
def filter_articles_by_date(feed, days=2):
    filtered_entries = []
    current_time = datetime.now()
    for entry in feed.entries:
        published_time = datetime(*entry.published_parsed[:6])
        if current_time - timedelta(days=days) <= published_time <= current_time:
            filtered_entries.append(entry)
    return filtered_entries

# Main function
def main():
    # Set default mode
    if 'dark_mode' not in st.session_state:
        st.session_state['dark_mode'] = False

    # Set initial page to news feed
    if 'page' not in st.session_state:
        st.session_state['page'] = "Main"

    # Check login state using cookies
    if check_login():
        st.sidebar.write(f"Welcome, {st.session_state['user']}!")
        logout()
    else:
        if st.session_state['page'] == "Login":
            login()
            register()
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

    def toggle_voting_section():
        if 'show_voting_section' not in st.session_state:
            st.session_state['show_voting_section'] = True
        show_voting_section = st.session_state['show_voting_section']
        return st.checkbox("Show/Hide Voting Section", value=show_voting_section, key='toggle_voting')

    def toggle_dark_light_mode():
        st.session_state['dark_mode'] = st.sidebar.checkbox("Dark Mode", value=st.session_state['dark_mode'])
        return st.session_state['dark_mode']

    def set_custom_css(dark_mode):
        css = """
        <style>
            h1 {
                font-family: 'Garamond';
                font-weight: bold;
                font-size: 5em;
                text-align: center;
            }
            h2 {
                font-family: 'Times New Roman';
                font-weight: bold;
                text-align: center;
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
                background-color: #2e2e2e;
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

    st.title("-ECHO-")
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

    show_voting_section = toggle_voting_section()

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
                if st.button(f"Remove {post['title']}", key=f"remove_{idx}"):
                    st.session_state.saved_posts = [p for p in saved_posts if p['link'] != post['link']]
                    st.experimental_rerun()
                st.markdown(f"### [{post['title']}]({post['link']})")
                st.markdown(f"{post['summary']}")

        else:
            st.write("No articles saved.")

    if show_voting_section:
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

                        with col1:
                            if st.button("Save", key=f"save_{idx}"):
                                st.session_state.saved_posts.append({
                                    'title': entry.title,
                                    'summary': entry.summary,
                                    'link': article_url
                                })
                                st.success(f"Saved {entry.title}")
                                st.experimental_rerun()

                        with col2:
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
                                    st.warning("Please log in or register to vote.")
                                    if st.button("Login/Register", key=f"login_register_{idx}"):
                                        st.session_state['page'] = "Login"
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
    .stButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

