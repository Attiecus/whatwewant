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
# Function to fetch article content and image
def fetch_article_content(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract content
    paragraphs = soup.find_all('p')
    if paragraphs:
        content = ' '.join([para.get_text() for para in paragraphs])  # Join all paragraphs
    else:
        content = 'Content not available'

    # Extract image
    image = None
    img_tag = soup.find('meta', property='og:image')
    if img_tag and img_tag['content']:
        image = img_tag['content']
    
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
        if ent.label_ in ['PERSON', 'ORG', 'GPE']:  # Extended to include geopolitical entities
            entities.append(ent.text)
    return list(set(entities))  # Use set to remove duplicates

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

# Fetch RSS feed
rss_url = 'http://feeds.bbci.co.uk/news/rss.xml'
feed = feedparser.parse(rss_url)

# Display articles in Streamlit

# User input for filtering articles by keyword
user_query = st.sidebar.text_input("Search for articles containing:")
def create_social_media_share_buttons(article_title, votes, options):
    website_url = "https://whatwewant.streamlit.app/"
    options_str = "%20".join(options)  # Convert options list to URL-friendly string
    twitter_url = f"https://twitter.com/intent/tweet?url={article_title}&text={website_url}&hashtags={votes}&options={options_str}"
    facebook_url = f"https://www.facebook.com/sharer/sharer.php?u={website_url}"
    linkedin_url = f"https://www.linkedin.com/shareArticle?mini=true&url={website_url}&title={article_title}"

    buttons_html = f"""
    <div>
        <a href="{twitter_url}" target="_blank">
            <img src="https://img.icons8.com/fluent/48/000000/twitter.png" />
        </a>
        <a href="{facebook_url}" target="_blank">
            <img src="https://img.icons8.com/fluent/48/000000/facebook-new.png" />
        </a>
        <a href="{linkedin_url}" target="_blank">
            <img src="https://img.icons8.com/fluent/48/000000/linkedin.png" />
        </a>
    </div>
    """
    st.markdown(buttons_html, unsafe_allow_html=True)

# Function to toggle visibility of voting section and votes
def toggle_voting_section():
    if 'show_voting_section' not in st.session_state:
        st.session_state['show_voting_section'] = True  # Default visibility
    show_voting_section = st.session_state['show_voting_section']
    return st.checkbox("Show/Hide Voting Section", value=show_voting_section, key='toggle_voting')

# Display articles in Streamlit
st.title("WELCOME TO WHAT WE WANT!")
st.header(f"HAVE YOUR SAY")
# User input for filtering articles by keyword
# User input for filtering articles by keyword
user_query = st.sidebar.text_input("Search for articles containing:", key="search_input")


# Inject the CSS into the Streamlit app


show_voting_section = toggle_voting_section()

if show_voting_section:
    if feed.entries:
        # Determine the number of columns based on the number of entries
        num_cols = min(len(feed.entries), 3)
        cols = st.columns(num_cols)
        rss_url = 'http://feeds.bbci.co.uk/news/rss.xml'
        feed = feedparser.parse(rss_url)

        num_cols = 3  # Define the number of columns for the layout
        cols = st.columns(num_cols)  # Create columns in Streamlit

        # Iterate over each entry in the feed
        for idx, entry in enumerate(feed.entries):
            col = cols[idx % num_cols]  # Select the column based on index

            with col:
                article_url = entry.link  # URL of the article
                content, image = fetch_article_content(article_url)  # Fetch the article content and image

                if image:
                    st.image(image, width=500)

                # Display the article title as a link
                st.markdown(f"### [{entry.title}]({entry.link})")

                # Show the article summary
                st.write(entry.summary)

                # Provide a 'Read more' link
                st.markdown(f"[Read more...]({entry.link})", unsafe_allow_html=True)

                # Generate and display social media sharing buttons
                


                # Add a separator for visual separation
                st.markdown("---")
                if content:
                    poll_type = determine_poll_type({'title': entry.title, 'description': entry.summary})
                    if poll_type == "yes_no":
                        options = ["Yes", "No"]
                    else:
                            # Extract relevant entities from content
                            relevant_entities = extract_relevant_entities(content)

                            # Count the frequency of each entity
                            entity_counts = {entity: relevant_entities.count(entity) for entity in set(relevant_entities)}

                            # Sort entities based on their frequency
                            sorted_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)

                            # Limit the number of options to 5-6
                            options = [entity[0] for entity in sorted_entities[:5]]

                    # Allow users to input custom options
                    custom_option = st.text_input(f"Enter a custom option for article {idx}:")  # Unique key for each input
                    if custom_option:
                        options.append(custom_option)

                    hashtag_options = [f"#{option.replace(' ', '')}" for option in options]
                    create_social_media_share_buttons(article_url, entry.title, hashtag_options)
                    if options:
                        # Create a unique key for each article's voting state
                        vote_key = f"votes_{idx}"
                        location_key = f"location_votes_{idx}"

                        if vote_key not in st.session_state:
                            st.session_state[vote_key] = {option: 0 for option in options}
                        if location_key not in st.session_state:
                            st.session_state[location_key] = {}

                        votes = st.session_state[vote_key]
                        location_votes = st.session_state[location_key]

                        # AI-generated prompt
                        question = generate_question({'title': entry.title, 'description': entry.summary})
                        st.write(question)

                        voted_option = st.radio("Vote on this news:", hashtag_options, key=f"radio_{idx}")

                        if st.button("Vote", key=f"vote_{idx}"):
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
