import streamlit as st
import json
from snowflake.snowpark import Session
from snowflake.core import Root

# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Corporate HR Policy Assistant | Cortex RAG Evaluator",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Corporate HR Policy Assistant")
st.subheader("Comparative RAG Evaluation: Snowflake Cortex Search vs. Direct LLM")

# -----------------------------------------------------------------------------
# Snowflake Connection Initialization
# -----------------------------------------------------------------------------
@st.cache_resource
def get_snowflake_session():
    """Returns an active Snowflake session."""
    return Session.builder.getOrCreate()

try:
    session = get_snowflake_session()
    root = Root(session)
except Exception as e:
    st.error(f"Failed to connect to Snowflake: {str(e)}")
    st.stop()

# Configuration Parameters
DATABASE = "HR_RAG_DB"
SCHEMA = "HR_POLICIES_SCHEMA"
SEARCH_SERVICE = "HR_POLICY_SEARCH_SERVICE"
MODEL_NAME = "mistral-large2" # Snowflake Cortex supported model

# Sidebar Controls
st.sidebar.header("⚙️ Configuration")
category_filter = st.sidebar.selectbox(
    "Filter by Category",
    ["All", "Paid Time Off & Leave", "Code of Conduct & Ethics", "Compensation & Performance", "Remote Work & Equipment", "Benefits & Health"]
)

top_k = st.sidebar.slider("Number of Context Chunks (Top-K):", min_value=1, max_value=5, value=3)

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def query_cortex_search(query_text: str, category: str, limit: int):
    """Queries Snowflake Cortex Search Service for relevant contextual chunks."""
    cortex_search_service = (
        root.databases[DATABASE]
        .schemas[SCHEMA]
        .cortex_search_services[SEARCH_SERVICE]
    )
    
    filter_obj = {}
    if category != "All":
        filter_obj = {"@eq": {"CATEGORY": category}}
        
    response = cortex_search_service.search(
        query=query_text,
        columns=["CHUNK", "CATEGORY", "FILE_NAME"],
        filter=filter_obj,
        limit=limit
    )
    return response.results

def generate_cortex_llm_response(prompt: str):
    """Executes a direct LLM completion call via Snowflake Cortex SQL."""
    escaped_prompt = prompt.replace("'", "''")
    sql = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{MODEL_NAME}', '{escaped_prompt}') AS RESPONSE"
    res = session.sql(sql).collect()
    return res[0]["RESPONSE"]

# -----------------------------------------------------------------------------
# Chat Interface & Comparison Engine
# -----------------------------------------------------------------------------
user_query = st.text_input(
    "Ask a question regarding HR policies:", 
    placeholder="e.g., What is our remote work stipend, and how often can I claim it?"
)

if user_query:
    st.divider()
    col1, col2 = st.columns(2)

    # -------------------------------------------------------------------------
    # Column 1: WITH Cortex Search (RAG Enabled)
    # -------------------------------------------------------------------------
    with col1:
        st.markdown("### 🔍 WITH Cortex Search (RAG Enabled)")
        with st.spinner("Retrieving facts & generating grounded answer..."):
            try:
                # 1. Retrieve context chunks
                context_chunks = query_cortex_search(user_query, category_filter, top_k)
                context_str = "\n\n".join([f"Excerpt {i+1}:\n" + c["CHUNK"] for i, c in enumerate(context_chunks)])
                
                # 2. Build Grounded Prompt
                rag_prompt = f"""
                You are an authoritative HR AI assistant. Answer the user's question accurately using ONLY the following context. 
                If the context does not contain the answer, explicitly state that the policy does not specify it.

                CONTEXT:
                {context_str}

                USER QUESTION:
                {user_query}

                ANSWER:
                """
                
                # 3. Complete LLM Response
                rag_response = generate_cortex_llm_response(rag_prompt)
                
                st.success("Grounding Context Successfully Retrieved!")
                st.markdown(rag_response)
                
