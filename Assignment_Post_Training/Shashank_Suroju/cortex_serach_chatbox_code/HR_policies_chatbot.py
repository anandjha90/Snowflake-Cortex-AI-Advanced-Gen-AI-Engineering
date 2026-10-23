# Import required libraries
import streamlit as st
from snowflake.snowpark.context import get_active_session
import json

# Page configuration
st.set_page_config(
    page_title="HR Policy RAG vs Direct LLM Comparison",
    page_icon="🤖",
    layout="wide"
)

# Initialize Snowflake session
session = get_active_session()

st.title("📊 Empirical Comparison: Cortex Search (RAG) vs. Direct LLM")
st.markdown("""
This application allows you to empirically test and compare responses generated **With RAG (Cortex Search Context)** versus **Without RAG (Direct LLM)** using your company HR policy documents.
""")

# Sidebar configuration for Model Selection and RAG Toggle
st.sidebar.header("Configuration Panel")

# 1. LLM Model Selection
available_models = [
    "snowflake-arctic",
    "llama3-70b",
    "llama3-8b",
    "mistral-large2",
    "reka-core"
]
selected_model = st.sidebar.selectbox(
    "Select LLM Model",
    options=available_models,
    index=0,
    help="Choose the foundational model used by SNOWFLAKE.CORTEX.COMPLETE"
)

st.sidebar.divider()

# 2. Augmentation Toggle Checkbox (User Instruction requirement)
use_rag = st.sidebar.checkbox(
    "Use your own documents as context",
    value=True,
    help="Check to enable Cortex Search RAG augmentation. Uncheck to query the raw LLM directly."
)

# Search parameters configuration (if RAG is enabled)
if use_rag:
    st.sidebar.subheader("Cortex Search Settings")
    top_k = st.sidebar.slider("Retrieved Chunks Limit (Top-K)", min_value=1, max_value=5, value=3)
else:
    top_k = 0

st.divider()

# Main Chat / Query Input
user_query = st.text_input(
    "Enter your HR policy question:",
    placeholder="e.g., What is our parental leave policy and how many weeks are paid?"
)

if user_query:
    col1, col2 = st.columns([2, 1] if use_rag else [1, 1])
    
    context_text = ""
    retrieved_results = []
    
    if use_rag:
        with st.spinner("Searching HR document chunks via Cortex Search..."):
            try:
                search_payload = json.dumps({
                    "query": user_query,
                    "columns": ["CHUNK", "CATEGORY", "RELATIVE_PATH", "CHUNK_INDEX"],
                    "limit": top_k
                })
                
                res_df = session.sql(f"""
                    SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                        'HR_POLICY_SEARCH_SERVICE',
                        '{search_payload}'
                    )) AS results
                """).to_pandas()
                
                raw_results = res_df["RESULTS"][0]
                if isinstance(raw_results, str) and raw_results:
                    parsed_json = json.loads(raw_results)
                else:
                    parsed_json = raw_results
                    
                retrieved_results = parsed_json.get("results", [])
                
                # Concatenate retrieved chunks into context string
                context_chunks = []
                for idx, r in enumerate(retrieved_results):
                    chunk_str = r.get("CHUNK", "")
                    category = r.get("CATEGORY", "General")
                    file_name = r.get("RELATIVE_PATH", "Handbook")
                    context_chunks.append(f"[Source {idx+1}: {file_name} | Category: {category}]\n{chunk_str}")
                
                context_text = "\n\n".join(context_chunks)
            except Exception as e:
                st.error(f"Error querying Cortex Search Service: {e}")

    # Generate Response using SNOWFLAKE.CORTEX.COMPLETE
    with st.spinner(f"Generating response using model `{selected_model}` (RAG Enabled: {use_rag})..."):
        try:
            if use_rag and context_text:
                prompt = f"""You are a helpful HR assistant. Answer the user question accurately based ONLY on the provided context. If the answer cannot be found in the context, state that you do not know based on company policies.

Context:
{context_text}

Question: {user_query}
Answer:"""
            else:
                prompt = f"""You are a helpful HR assistant. Answer the user question based on general knowledge without specific company policy grounding.

Question: {user_query}
Answer:"""

            # Escape single quotes in prompt for safe SQL interpolation
            escaped_prompt = prompt.replace("'", "''")
            
            completion_sql = f"""
                SELECT SNOWFLAKE.CORTEX.COMPLETE(
                    '{selected_model}',
                    '{escaped_prompt}'
                ) AS response
            """
            response_df = session.sql(completion_sql).to_pandas()
            final_response = response_df["RESPONSE"][0]
            
        except Exception as e:
            final_response = f"Error executing Cortex Complete: {e}"

    # Render Output Layout
    with col1:
        st.subheader("🤖 Chatbot Response")
        if use_rag:
            st.success(f"Mode: **Cortex Search RAG Enabled** (Model: `{selected_model}`)")
        else:
            st.warning(f"Mode: **Standard Direct LLM** (Model: `{selected_model}` - No Context)")
            
        st.markdown(final_response)

    if use_rag:
        with col2:
            st.subheader("🔍 Retrieved Context Chunks")
            st.info(f"Top {len(retrieved_results)} relevant policy chunks matched.")
            for i, r in enumerate(retrieved_results):
                with st.expander(f"Chunk {i+1}: {r.get('RELATIVE_PATH')} ({r.get('CATEGORY')})"):
                    st.write(r.get("CHUNK"))
