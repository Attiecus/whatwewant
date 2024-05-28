import streamlit as st
import requests
import spacy
from opencage.geocoder import OpenCageGeocode

# Load spaCy model
st.set_page_config(layout='wide')
nlp = spacy.load("en_core_web_sm")

# OpenCage API key
OPENCAGE_API_KEY = 'dcbeeba6d26b4628bef1806606c11c21'  # Replace with your OpenCage API key

# Initialize geocoder
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# NewsAPI key
NEWS_API_KEY = 'c18531a160cb4b729778ecbf3c643ead'  # Replace with your NewsAPI key
IPINFO_API_KEY = 'f2439f60dfe99d'  # Replace with your ipinfo API key

def fetch_news(api_key, query=None, category=None, country='us'):
    if query:
        url = f'https://newsapi.org/v2/everything?q={query}&apiKey={api_key}'
    else:
        url = f'https://newsapi.org/v2/top-headlines?country={country}&category={category}&apiKey={api_key}'
    response = requests.get(url)
    return response.json()

def extract_relevant_entities(text):
    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        if ent.label_ in ['PERSON', 'ORG', 'GPE']:  # Extended to include geopolitical entities
            entities.append(ent.text)
    return list(set(entities))  # Use set to remove duplicates

def generate_question(article):
    title = article['title']
    description = article['description'] or ''
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

def get_user_location(api_key):
    response = requests.get(f'https://ipinfo.io/json?token={api_key}')
    return response.json()

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

categories = ['business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology']
selected_category = st.sidebar.selectbox("Select a category:", categories)

# Text input for user-specific news
user_query = st.sidebar.text_input("What kind of news do you want to see?")

# Fetch news data based on user query or selected category
if user_query:
    news_data = fetch_news(NEWS_API_KEY, query=user_query)
else:
    news_data = fetch_news(NEWS_API_KEY, category=selected_category)

st.title("WELCOME TO WHAT WE WANT!")
st.header(f"HAVE YOUR SAY")

if user_query:
    st.header(f"Trending News for '{user_query}'")
else:
    st.header(f"Trending News in {selected_category.capitalize()}")

if news_data['status'] == 'ok':
    articles = news_data['articles']

    for article in articles:
        title = article['title']
        description = article['description']
        content = article.get('content', description)
        image_url = article.get('urlToImage')
        url = article['url']
        
        st.subheader(title)
        if image_url:
            st.image(image_url, caption=title)
        
        st.write(description)
        st.markdown(f"[Read more]({url})")

        if content:
            poll_type = determine_poll_type(article)
            if poll_type == "yes_no":
                options = ["Yes", "No"]
            else:
                options = extract_relevant_entities(content)

            hashtag_options = [f"#{option.replace(' ', '')}" for option in options]

            if options:
                # Create a unique key for each article's voting state
                vote_key = f"votes_{title.replace(' ', '_')}"
                location_key = f"location_votes_{title.replace(' ', '_')}"

                if vote_key not in st.session_state:
                    st.session_state[vote_key] = {option: 0 for option in options}
                if location_key not in st.session_state:
                    st.session_state[location_key] = {}

                votes = st.session_state[vote_key]
                location_votes = st.session_state[location_key]

                # AI-generated prompt
                question = generate_question(article)
                st.write(question)

                voted_option = st.radio("Vote on this news:", hashtag_options, key=title)

                if st.button("Vote", key=f"vote_{title}"):
                    if voted_option in votes:
                        votes[voted_option] += 1
                    else:
                        votes[voted_option] = 1
                    st.session_state[vote_key] = votes  # Update session state

                    # Get user location
                    user_location = get_user_location(IPINFO_API_KEY)
                    country = user_location.get('country', 'Unknown')

                    # Update location-based vote count
                    if country not in location_votes:
                        location_votes[country] = 1
                    else:
                        location_votes[country] += 1
                    st.session_state[location_key] = location_votes

                    st.success("Thank you for voting!")

                # Display poll results if the user has voted
                if any(count > 0 for count in votes.values()):
                    st.write("Current Poll Results:")
                    total_votes = sum(votes.values())
                    for option, count in votes.items():
                        percentage = count / total_votes * 100 if total_votes != 0 else 0
                        st.write(f"{option}: {count} votes ({percentage:.2f}% of total)")
                        st.progress(percentage / 100)
                    st.write("---")

                    # Display location-based poll results
                    st.write("Votes by Country:")
                    for country, count in location_votes.items():
                        st.write(f"{country}: {count} votes")

                    # Plot the world map with points
                    st.write("World Map of Votes:")
                    map_data = plot_world_map(location_votes)
                    st.map(map_data)
                st.write("---")

            else:
                st.write("No relevant entities found for voting.")
        else:
            st.write("No content available for deeper analysis.")
else:
    st.error("Failed to fetch trending news.")
