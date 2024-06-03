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
from firebase_admin import credentials, firestore, auth
from firebase_admin._auth_utils import UserNotFoundError, EmailAlreadyExistsError
from datetime import datetime, timedelta
from PIL import Image

# Initialize Firebase app
if not firebase_admin._apps:
    cred = credentials.Certificate("path_to_your_firebase_admin_sdk_json")
    firebase_admin.initialize_app(cred)

# Initialize Firestore
db = firestore.client()

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
        return True
    elif cookies.get("user"):
        st.session_state["user"] = cookies["user"]
        return True
    return False

# Function to create a unique post URL
def generate_post_url(post_id):
    base_url = "https://voices.streamlit.app/"
    return f"{base_url}?post_id={post_id}"

# Function to create a Twitter share button
def create_twitter_share_button(post_id, tweet_content, hashtags):
    post_url = generate_post_url(post_id)
    hashtag_str = " ".join([f"#{tag}" for tag in hashtags])
    twitter_url = f"https://twitter.com/intent/tweet?text={tweet_content} {hashtag_str} {post_url}"
    st.markdown(f"[Tweet this](https://twitter.com/intent/tweet?text={tweet_content} {hashtag_str} {post_url})")

# Function to create or update a poll in Firestore
def create_or_update_poll(post_id, option):
    doc_ref = db.collection("polls").document(post_id)
    doc = doc_ref.get()
    if doc.exists:
        poll_data = doc.to_dict()
        if option in poll_data["options"]:
            poll_data["options"][option] += 1
        else:
            poll_data["options"][option] = 1
    else:
        poll_data = {
            "options": {option: 1}
        }
    doc_ref.set(poll_data)

# Function to display poll results
def display_poll_results(post_id):
    doc_ref = db.collection("polls").document(post_id)
    doc = doc_ref.get()
    if doc.exists:
        poll_data = doc.to_dict()
        options = poll_data["options"]
        total_votes = sum(options.values())
        st.write("Current Poll Results:")
        for option, count in options.items():
            percentage = count / total_votes * 100 if total_votes != 0 else 0
            st.write(f"{option}: {count} votes ({percentage:.2f}% of total)")
            st.progress(percentage / 100)
    else:
        st.write("No votes yet.")
# Login function using Firebase Authentication
def login():
    st.markdown("<h1 style='font-family: Garamond; font-weight: bold; font-size: 5em; text-align: center;'>-ECHO-</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>Login</h2>", unsafe_allow_html=True)
    username = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        try:
            user = auth.get_user_by_email(username)
            user_token = auth.create_custom_token(user.uid)
            st.session_state["user"] = username
            st.session_state["voted_articles"] = cookies.get("voted_articles", [])
            st.success("Logged in successfully!")
            cookies["user"] = username
            cookies.save()
        except UserNotFoundError:
            st.error("Invalid email or password")

# Register function using Firebase Authentication
def register():
    st.markdown("<h2 style='text-align: center;'>Sign-up</h2>", unsafe_allow_html=True)
    anonymous = st.checkbox("Register as Anonymous", key="anonymous_checkbox")
    
    if anonymous:
        if st.button("Register Anonymously"):
            anonymous_id = hashlib.sha256(str(time.time()).encode()).hexdigest()
            try:
                user = auth.create_user(uid=anonymous_id)
                st.session_state["user"] = anonymous_id
                st.session_state["voted_articles"] = []
                st.success("Registered anonymously!")
                cookies["user"] = anonymous_id
                cookies.save()
            except EmailAlreadyExistsError as e:
                st.error(f"Error: {e}")
    else:
        username = st.text_input("Email", key="register_email")
        password = st.text_input("Password", type="password", key="register_password")
        if st.button("Register"):
            try:
                user = auth.create_user(email=username, password=password)
                st.success("Registered successfully! You can now log in.")
            except EmailAlreadyExistsError as e:
                st.error(f"Error: {e}")

# Logout function
def logout():
    if st.button("Logout"):
        st.session_state.pop("user")
        st.session_state.pop("voted_articles")
        cookies["user"] = ""
        cookies.save()
        st.experimental_rerun()
def tutorial():
    st.markdown("<h1 style='font-family: Garamond; font-weight: bold; font-size: 5em; text-align: center;'>-ECHO-</h1>", unsafe_allow_html=True)
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

    if st.button("Go to Login Page"):
        st.session_state['page'] = "Login"
        st.experimental_rerun()
def main():
    # Set default mode
    if 'dark_mode' not in st.session_state:
        st.session_state['dark_mode'] = False
    
    if 'page' not in st.session_state:
        st.session_state['page'] = "Tutorial"

    if st.session_state['page'] == "Login":
        login()
        register()
    elif st.session_state['page'] == "Tutorial":
        tutorial()
        return
    else:
        # User authentication
        if not check_login():
            login()
            register()
            return
        else:
            st.sidebar.write(f"Welcome, {st.session_state['user']}!")
            logout()

    IPINFO_API_KEY = 'f2439f60dfe99d'

    @st.cache_resource
    def load_spacy_model():
        return spacy.load("en_core_web_sm")

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

    def generate_question(article):
        title = article['title']
        description = article['description'] or ''
        nlp = load_spacy_model()
        doc = nlp(title + " " + description)
        questions = []
        for sent in doc.sents:
            if len(sent.ents) > 0:
                questions.append(f"What are your thoughts on this topic: '{sent}'?")
        return questions[0] if questions else "What do you think about this news?"

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

    def create_social_media_share_buttons(article_title, votes, options):
        website_url = "https://whatwewant.streamlit.app/"
        options_str = "%20".join(options)
        twitter_url = f"https://twitter.com/intent/tweet?url={article_title}&text={website_url}&options={options_str}"
        facebook_url = f"https://www.facebook.com/sharer/sharer.php?u={website_url}"
        linkedin_url = f"https://www.linkedin.com/shareArticle?mini=true&url={website_url}&title={article_title}"
        instagram_url = f"https://www.instagram.com/?url={website_url}"

        buttons_html = f"""
        <div style="display: flex; gap: 10px;">
            <a href="{twitter_url}" target="_blank">
                <img src="https://th.bing.com/th/id/OIP.OiRP0Wt_nlImTXz5w45aRQHaHa?rs=1&pid=ImgDetMain" alt="X logo" style="width: 48px; height: 48px;"/>
            </a>
            <a href="{facebook_url}" target="_blank">
                <img src="https://img.icons8.com/fluent/48/000000/facebook-new.png" alt="Facebook logo" style="width: 48px; height: 48px;"/>
            </a>
            <a href="{linkedin_url}" target="_blank">
                <img src="https://img.icons8.com/fluent/48/000000/linkedin.png" alt="LinkedIn logo" style="width: 48px; height: 48px;"/>
            </a>
            <a href="{instagram_url}" target="_blank">
                <img src="https://img.icons8.com/fluent/48/000000/instagram-new.png" alt="Instagram logo" style="width: 48px; height: 48px;"/>
            </a>
        </div>
        """
        st.markdown(buttons_html, unsafe_allow_html=True)

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

    def search_articles(feed, query):
        if not query:
            return feed.entries
        filtered_entries = []
        for entry in feed.entries:
            if query.lower() in entry.title.lower() or query.lower() in entry.summary.lower():
                filtered_entries.append(entry)
        return filtered_entries

    def filter_articles_by_date(feed, days=1):
        filtered_entries = []
        current_time = datetime.now()
        for entry in feed.entries:
            published_time = datetime(*entry.published_parsed[:6])
            if current_time - timedelta(days=days) <= published_time <= current_time:
                filtered_entries.append(entry)
        return filtered_entries

    dark_mode = toggle_dark_light_mode()
    set_custom_css(dark_mode)

    st.title("-ECHO-")
    st.header("HAVE YOUR SAY")

    categories = ["All", "Politics", "Technology", "Sports", "Entertainment", "Health"]
    selected_category = st.selectbox("Select Category", categories)

    user_query = st.text_input("Search for articles containing:", key="article_search")

    news_sources = {
        "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
        "RTE": "https://www.rte.ie/rss/news.xml",
        "Al Jazeera": "http://www.aljazeera.com/xml/rss/all.xml",
        "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
    }

    news_source = st.sidebar.selectbox("Select news source:", list(news_sources.keys()))
    feed_url = news_sources[news_source]

    if st.button("Reload Feed"):
        feed = feedparser.parse(feed_url)
    else:
        feed = feedparser.parse(feed_url)

    show_voting_section = toggle_voting_section()

    with st.sidebar:
        st.header("Saved Articles")
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
        filtered_entries = filter_articles_by_date(feed, days=1)
        filtered_entries = search_articles(feed, user_query)
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

                        if st.button("Save", key=f"save_{idx}"):
                            st.session_state.saved_posts.append({
                                'title': entry.title,
                                'summary': entry.summary,
                                'link': article_url
                            })
                            st.success(f"Saved {entry.title}")
                            st.experimental_rerun()

                        if content:
                            poll_type = determine_poll_type({'title': entry.title, 'description': entry.summary})
                            if poll_type == "yes_no":
                                options = ["Yes", "No"]
                            else:
                                relevant_entities = extract_relevant_entities(content)
                                entity_counts = {entity: relevant_entities.count(entity) for entity in set(relevant_entities)}
                                sorted_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)
                                options = [entity[0] for entity in sorted_entities[:5]]

                            custom_option = st.text_input(f"Enter a custom option for article {idx}:", key=f"custom_option_{idx}")
                            if custom_option:
                                options.append(custom_option)

                            hashtag_options = [f"#{option.replace(' ', '')}" for option in options]
                            create_social_media_share_buttons(article_url, entry.title, hashtag_options)

                            if options:
                                vote_key = f"votes_{idx}"
                                location_key = f"location_votes_{idx}"

                                if vote_key not in st.session_state:
                                    st.session_state[vote_key] = {option: 0 for option in options}
                                if location_key not in st.session_state:
                                    st.session_state[location_key] = {}

                                votes = st.session_state[vote_key]
                                location_votes = st.session_state[location_key]

                                question = generate_question({'title': entry.title, 'description': entry.summary})
                                st.write(question)

                                voted_option = st.radio("UPROAR on this news:", hashtag_options, key=f"radio_{idx}")

                                if st.button("UPROAR", key=f"vote_{idx}"):
                                    article_id = entry.link
                                    if track_vote(article_id):
                                        if voted_option in votes:
                                            votes[voted_option] += 1
                                        else:
                                            votes[voted_option] = 1
                                        st.session_state[vote_key] = votes

                                        user_location = get_user_location(IPINFO_API_KEY)
                                        country = user_location.get('country', 'Unknown')

                                        if country not in location_votes:
                                            location_votes[country] = 1
                                        else:
                                            location_votes[country] += 1
                                        st.session_state[location_key] = location_votes

                                        st.write("🔥UPROARED!✅ POWER-TO-YOU 🔥! ")

                                with st.expander("Show/Hide Poll Results"):
                                    if any(count > 0 for count in votes.values()):

                                        st.write("Current Poll Results:")
                                        total_votes = sum(votes.values())
                                        for option, count in votes.items():
                                            percentage = count / total_votes * 100 if total_votes != 0 else 0
                                            st.write(f"{option}: {count} votes ({percentage:.2f}% of total)")
                                            st.progress(percentage / 100)
                                        st.write("---")

                                        st.write("Votes by Country:")
                                        for country, count in location_votes.items():
                                            st.write(f"{country}: {count} votes")

                                    st.write("---")

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
