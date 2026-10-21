"""
================================================================================
Online Shopping Mart Support Assistant (E-Commerce RAG Chatbot)
================================================================================
"""
import os
import streamlit as st
try:
    # Import Snowflake libraries for establishing a secure connection to Cortex
    from snowflake.snowpark.context import get_active_session
    from snowflake.snowpark import Session
    from snowflake.core import Root
except ImportError:
    st.error("Snowflake libraries not found.")

# Configure the Streamlit page layout and title
st.set_page_config(page_title="Online Shopping Mart Support Assistant", page_icon="🛍️", layout="wide")

# Inject custom CSS to style the user and bot chat bubbles for an e-commerce aesthetic
st.markdown("""
<style>
    .chat-user { background-color: #F3E8FF; border-left: 4px solid #9333EA; padding: 12px; border-radius: 8px; margin-bottom: 12px; }
    .chat-bot { background-color: #F8FAFC; border-left: 4px solid #0EA5E9; padding: 12px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #E2E8F0; }
</style>
""", unsafe_allow_html=True)

# Define constants mapping to our Snowflake environment
DATABASE_NAME = "ECOM_CORTEX_DB"
SCHEMA_NAME = "SUPPORT"
SEARCH_SERVICE_NAME = "SHOPNOVA_SEARCH_SVC" # Maintained service name internally but updated UI references

@st.cache_resource(show_spinner=False)
def init_session():
    """Initializes the Snowflake session securely."""
    try:
        # Tries to get the active session if running natively in Streamlit in Snowflake (SiS)
        return get_active_session()
    except Exception:
        # Falls back to local credentials stored in .streamlit/secrets.toml if running locally
        return Session.builder.configs(st.secrets["connections"]["snowflake"]).create()

# Establish session and initialize the Cortex root object for API calls
session = init_session()
cortex_root = Root(session)

def retrieve_support_articles(query: str, category: str, limit: int = 3):
    """
    Queries the Snowflake Cortex Search Service (Hybrid Search).
    Extracts the most relevant policy chunks based on the user's question.
    """
    try:
        # Locate the specific search service in our database and schema
        svc = cortex_root.databases[DATABASE_NAME].schemas[SCHEMA_NAME].cortex_search_services[SEARCH_SERVICE_NAME]
        
        # Apply metadata filtering if a specific category is selected in the UI
        filter_obj = {"@eq": {"CATEGORY": category}} if category != "All" else None
        
        # Execute the search and return the top matching chunks
        res = svc.search(query=query, columns=["CHUNK", "DOC_URL", "CATEGORY"], filter=filter_obj, limit=limit)
        return res.results if res and res.results else []
    except Exception as e:
        st.error(f"Search Error: {e}")
        return []

def generate_support_answer(question: str, context_chunks: list, model: str):
    """
    Passes the retrieved knowledge base chunks and the user's question to a Cortex LLM.
    Strictly instructs the LLM not to hallucinate policies outside the provided text.
    """
    # Format the retrieved chunks into a single readable context block
    context_text = "\n\n---\n\n".join([f"Source: {c['DOC_URL']}\n{c['CHUNK']}" for c in context_chunks])
    
    # Construct the RAG prompt with strict grounding instructions
    prompt = f"""
    You are a polite, helpful customer support agent for the online retailer 'Online Shopping Mart'.
    Answer the customer's question STRICTLY based on the official policy context below.
    If the answer is not in the context, say "I'm sorry, I don't have that information in our current policy documents."
    <context>{context_text}</context>
    Customer Question: {question}
    Support Agent Response:"""
    
    try:
        # Execute the serverless LLM call using SNOWFLAKE.CORTEX.COMPLETE
        sql = "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS resp"
        result = session.sql(sql, params=[model, prompt]).collect()
        return result[0]["RESP"].strip()
    except Exception as e:
        return f"Error: {e}"

# --- Sidebar Configuration ---
with st.sidebar:
    st.title("🛍️ Online Shopping Mart Settings")
    model = st.selectbox("Cortex Model", ["claude-3-5-sonnet", "llama3.1-70b", "mistral-large2"])
    category = st.selectbox("Policy Category", ["All", "Returns", "Shipping", "Loyalty", "Billing"])
    rag_mode = st.toggle("Use Help Center Docs (RAG)", value=True)
    if st.button("Clear Chat"):
        st.session_state.chat = []
        st.rerun()

# --- Main Application Interface ---
st.title("🛍️ Online Shopping Mart Customer Support")

# Initialize session state for storing chat history and retrieved sources
if "chat" not in st.session_state:
    st.session_state.chat = [{"role": "assistant", "content": "Hi! Welcome to Online Shopping Mart. How can I assist you today?"}]
if "sources" not in st.session_state:
    st.session_state.sources = {}

# Render the conversation history on screen
for idx, msg in enumerate(st.session_state.chat):
    div_class = "chat-user" if msg["role"] == "user" else "chat-bot"
    sender = "👤 You" if msg["role"] == "user" else "🎧 Online Shopping Mart Support"
    st.markdown(f'<div class="{div_class}"><strong>{sender}:</strong><br>{msg["content"]}</div>', unsafe_allow_html=True)
    
    # Render expandable source citations if they exist for this specific bot response
    if idx in st.session_state.sources:
        with st.expander("📄 View Knowledge Base Evidence"):
            for s in st.session_state.sources[idx]:
                st.write(s['CHUNK'])

# --- Handle User Input ---
if prompt := st.chat_input("Ask a question..."):
    # Save and display user message immediately
    st.session_state.chat.append({"role": "user", "content": prompt})
    st.markdown(f'<div class="chat-user"><strong>👤 You:</strong><br>{prompt}</div>', unsafe_allow_html=True)
    
    with st.spinner("Searching policies..."):
        # Branch 1: RAG Mode Enabled (Grounded Answer)
        if rag_mode:
            chunks = retrieve_support_articles(prompt, category)
            ans = generate_support_answer(prompt, chunks, model) if chunks else "No policy found."
        
        # Branch 2: Direct LLM Mode (Ungrounded, risk of hallucination)
        else:
            res = session.sql("SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) as R", params=[model, prompt]).collect()
            ans, chunks = res[0]["R"], []
            
    # Save the assistant's response to history and trigger UI refresh
    bot_idx = len(st.session_state.chat)
    st.session_state.chat.append({"role": "assistant", "content": ans})
    if chunks: 
        st.session_state.sources[bot_idx] = chunks
    st.rerun()
