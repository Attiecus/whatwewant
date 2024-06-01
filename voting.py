import streamlit as st
import requests
import spacy
from opencage.geocoder import OpenCageGeocode
from bs4 import BeautifulSoup
import feedparser
import aiohttp
import asyncio

# Set Streamlit page configuration
st.set_page_config(layout='wide')
IPINFO_API_KEY = 'f2439f60dfe99d'

@st.cache_resource
def load_spacy_model():
    return spacy.load("en_core_web_sm")

# Function to fetch article content and image using asynchronous requests
async def fetch_article_content_async(session, url):
    async with session.get(url) as response:
        content = await response.read()
        soup = BeautifulSoup(content, 'lxml')  # Use lxml for faster parsing

        # Extract content
        paragraphs = soup.find_all('p')
        content = ' '.join([para.get_text() for para in paragraphs]) if paragraphs else 'Content not available'

        # Extract image
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

# OpenCage API key
OPENCAGE_API_KEY = 'dcbeeba6d26b4628bef1806606c11c21'  # Replace with your OpenCage API key

# Initialize geocoder
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# Function to extract relevant entities from text
@st.cache_data
def extract_relevant_entities(text):
    nlp = load_spacy_model()
    doc = nlp(text)
    entities = [ent.text for ent in doc.ents if ent.label_ in ['PERSON', 'ORG', 'GPE']]
    return list(set(entities))

# Function to generate a question based on the article
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

# Function to determine the type of poll based on the article
def determine_poll_type(article):
    if "policy" in article['title'].lower() or "election" in article['title'].lower():
        return "yes_no"
    else:
        return "entity_based"

# Function to get the user's location
@st.cache_data
def get_user_location(api_key):
    response = requests.get(f'https://ipinfo.io/json?token={api_key}')
    return response.json()

# Function to get coordinates of a country
@st.cache_data
def get_country_coordinates(country_name):
    result = geocoder.geocode(country_name)
    if result and len(result):
        return result[0]['geometry']['lat'], result[0]['geometry']['lng']
    return None, None

# Function to plot world map with location-based votes
def plot_world_map(location_votes):
    data = []
    for country, votes in location_votes.items():
        lat, lon = get_country_coordinates(country)
        if lat and lon:
            for _ in range(votes):
                data.append({'lat': lat, 'lon': lon})
    return data

# Function to create social media share buttons
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

# Function to toggle visibility of voting section and votes
def toggle_voting_section():
    if 'show_voting_section' not in st.session_state:
        st.session_state['show_voting_section'] = True
    show_voting_section = st.session_state['show_voting_section']
    return st.checkbox("Show/Hide Voting Section", value=show_voting_section, key='toggle_voting')

# Function to toggle dark/light mode
def toggle_dark_light_mode():
    if 'dark_mode' not in st.session_state:
        st.session_state['dark_mode'] = False
    st.session_state['dark_mode'] = st.sidebar.checkbox("Dark Mode", value=st.session_state['dark_mode'])
    return st.session_state['dark_mode']

# Set custom CSS for changing the font of the title and dark mode
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
    # Set custom CSS for responsive title and header
def set_custom_css():
    css = """
    <style>
        h1 {
            font-family: 'Garamond';
            font-weight: bold;
            font-size: 3em;
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
    st.markdown(css, unsafe_allow_html=True)

# Call the function to set custom CSS
set_custom_css()


# Function to search for articles
def search_articles(feed, query):
    if not query:
        return feed.entries
    filtered_entries = []
    for entry in feed.entries:
        if query.lower() in entry.title.lower() or query.lower() in entry.summary.lower():
            filtered_entries.append(entry)
    return filtered_entries

# Main App

dark_mode = toggle_dark_light_mode()
set_custom_css(dark_mode)

st.title("- VOICES -")
st.header("HAVE YOUR SAY")

# Add category section

# User input for searching articles
user_query = st.text_input("Search for articles containing:")

news_sources = {
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
    "RTE": "https://www.rte.ie/rss/news.xml",
    "Al Jazeera": "http://www.aljazeera.com/xml/rss/all.xml",
    #"Times of India": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
}

news_source = st.sidebar.selectbox("Select news source:", list(news_sources.keys()))
feed_url = news_sources[news_source]

if st.button("Reload Feed"):
    feed = feedparser.parse(feed_url)
else:
    feed = feedparser.parse(feed_url)

show_voting_section = toggle_voting_section()

# Sidebar for saved articles
# Sidebar for saved articles
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

# Main section
# Assuming `filtered_entries` and `articles` are defined and populated earlier in the script
if show_voting_section:
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

                    # Styling for the card
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

                        custom_option = st.text_input(f"Enter a custom option for article {idx}:")
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

# Custom CSS for card layout
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
