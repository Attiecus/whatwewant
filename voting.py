import streamlit as st
import requests
import spacy
import matplotlib.pyplot as plt

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# NewsAPI key
NEWS_API_KEY = 'c18531a160cb4b729778ecbf3c643ead'

def fetch_news_by_category(api_key, category, country='us'):
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

categories = ['business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology']
selected_category = st.sidebar.selectbox("Select a category:", categories)

news_data = fetch_news_by_category(NEWS_API_KEY, selected_category)

st.title(f"Trending News in {selected_category.capitalize()}")

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
            entities = extract_relevant_entities(content)
            if entities:
                # Create a unique key for each article's voting state
                vote_key = f"votes_{title.replace(' ', '_')}"
                if vote_key not in st.session_state:
                    st.session_state[vote_key] = {entity: 0 for entity in entities}
                
                votes = st.session_state[vote_key]
                
                # AI-generated prompt
                question = generate_question(article)
                st.write(question)
                
                voted_option = st.radio("Vote on this news:", entities, key=title)
                
                if st.button("Vote", key=f"vote_{title}"):
                    votes[voted_option] += 1
                    st.session_state[vote_key] = votes  # Update session state

                # Display poll results
                st.write("Current Poll Results:")
                total_votes = sum(votes.values())
                for entity, count in votes.items():
                    percentage = count / total_votes * 100 if total_votes != 0 else 0
                    st.write(f"{entity}: {count} votes ({percentage:.2f}% of total)")
                    st.progress(percentage / 100)
                st.write("---")
            else:
                st.write("No relevant entities found for voting.")
        else:
            st.write("No content available for deeper analysis.")
else:
    st.error("Failed to fetch trending news.")
