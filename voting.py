import streamlit as st
import requests
import spacy
from opencage.geocoder import OpenCageGeocode
from bs4 import BeautifulSoup
import feedparser

# Set Streamlit page configuration
st.set_page_config(layout='wide')
IPINFO_API_KEY = 'f2439f60dfe99d'

# Function to fetch article content and image
def fetch_article_content(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract content
    paragraphs = soup.find_all('p')
    if paragraphs:
        content = ' '.join([para.get_text() for para in paragraphs])
    else:
        content = 'Content not available'

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

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# OpenCage API key
OPENCAGE_API_KEY = 'dcbeeba6d26b4628bef1806606c11c21'  # Replace with your OpenCage API key

# Initialize geocoder
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# Function to extract relevant entities from text
def extract_relevant_entities(text):
    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        if ent.label_ in ['PERSON', 'ORG', 'GPE']:
            entities.append(ent.text)
    return list(set(entities))

# Function to generate a question based on the article
def generate_question(article):
    title = article['title']
    description = article['description'] or ''
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
def get_user_location(api_key):
    response = requests.get(f'https://ipinfo.io/json?token={api_key}')
    return response.json()

# Function to get coordinates of a country
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
    twitter_url = f"https://twitter.com/intent/tweet?url={article_title}&text={website_url}&hashtags={votes}&options={options_str}"
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
            font-family: 'Times New Roman', Times, serif;
            font-weight: bold;
            font-size: 4em;
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
        .stMarkdown {
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
        .stMarkdown {
            color: #000000;
        }
    </style>
    """
    if dark_mode:
        st.markdown(dark_css, unsafe_allow_html=True)
    else:
        st.markdown(light_css, unsafe_allow_html=True)
    st.markdown(css, unsafe_allow_html=True)

dark_mode = toggle_dark_light_mode()
set_custom_css(dark_mode)

st.title("VOICES")
st.header(f"HAVE YOUR SAY")

# User input for filtering articles by keyword
user_query = st.sidebar.text_input("Search for articles containing:", key="search_input")

# News source selection
news_sources = {
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
    "RTE": "https://www.rte.ie/rss/news.xml",
    "Al Jazeera": "http://www.aljazeera.com/xml/rss/all.xml",
    #"Times of India": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
}

news_source = st.sidebar.selectbox("Select news source:", list(news_sources.keys()))
feed_url = news_sources[news_source]

# Reload Button
if st.button("Reload Feed"):
    feed = feedparser.parse(feed_url)
else:
    feed = feedparser.parse(feed_url)

show_voting_section = toggle_voting_section()

# Sidebar for saved articles
with st.sidebar:
    st.header("Saved Articles")
    if 'saved_posts' not in st.session_state:
        st.session_state.saved_posts = []
    if st.session_state.saved_posts:
        for post in st.session_state.saved_posts:
            if st.button(f"Remove {post['title']}", key=post['link']):
                # Remove the article from saved posts
                st.session_state.saved_posts = [p for p in st.session_state.saved_posts if p['link'] != post['link']]
                st.experimental_rerun()
            st.markdown(f"### [{post['title']}]({post['link']})")
            st.markdown(f"{post['summary']}")
    else:
        st.write("No articles saved.")

if show_voting_section:
    if feed.entries:
        num_cols = min(len(feed.entries), 3)
        cols = st.columns(num_cols)

        for idx, entry in enumerate(feed.entries):
            col = cols[idx % num_cols]
            with col:
                with st.container():
                    article_url = entry.link
                    content, image = fetch_article_content(article_url)

                    # Initialize like/dislike counters
                    like_key = f"like_{idx}"
                    dislike_key = f"dislike_{idx}"
                    if like_key not in st.session_state:
                        st.session_state[like_key] = 0
                    if dislike_key not in st.session_state:
                        st.session_state[dislike_key] = 0

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
                        
                    card_html += f"""
                        <div style="margin-top: 10px;">
                            <button onclick="window.parent.streamlit.setComponentValue('{like_key}', window.parent.streamlit.getComponentValue('{like_key}') + 1)">👍 Like ({st.session_state[like_key]})</button>
                            <button onclick="window.parent.streamlit.setComponentValue('{dislike_key}', window.parent.streamlit.getComponentValue('{dislike_key}') + 1)">👎 Dislike ({st.session_state[dislike_key]})</button>
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                    
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

                                st.success("Thank you for voting!")

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
