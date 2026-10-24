import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="E-Grocery Support Agent",
    page_icon="🛒",
    layout="wide"
)

# Active Snowflake Session
session = get_active_session()

# --- Sidebar Customer Session Profile ---
st.sidebar.title("👤 Customer Session")
customer_id = st.sidebar.text_input("Active Customer ID:", value="CUST-101")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ AI Model Controls")
llm_model = st.sidebar.selectbox(
    "Cortex LLM Engine:",
    ("claude-3-5-sonnet", "llama3.1-70b", "mistral-large2"),
    index=0
)

# --- Header Section ---
st.title("🛒 E-Grocery Autonomous AI Support Agent")
st.caption("Powered by Snowflake Cortex AI & Vector Search (RAG)")

# Session Chat Memory
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Core Helper Functions ---
def fetch_customer_order_history(cust_id):
    """Fetches transactional order record for active customer."""
    query = f"""
        SELECT ORDER_ID, PRODUCT_NAME, CATEGORY, ORDER_DATE, STATUS, TOTAL_AMOUNT 
        FROM CUSTOMER_ORDERS 
        WHERE CUSTOMER_ID = '{cust_id}' 
        ORDER BY ORDER_DATE DESC
    """
    return session.sql(query).to_pandas()

def fetch_product_catalog():
    """Fetches active product inventory and dietary information."""
    query = "SELECT PRODUCT_ID, PRODUCT_NAME, CATEGORY, PRICE, STOCK_QTY, DIETARY_INFO, SPECIFICATIONS FROM PRODUCT_CATALOG"
    return session.sql(query).to_pandas()

def search_policy_documents(query_text, top_k=3):
    """Retrieves online shopping policies using vector similarity search."""
    clean_q = query_text.replace("'", "''")
    vector_sql = f"""
        WITH query_vec AS (
            SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', '{clean_q}') AS q_emb
        )
        SELECT 
            DOC_NAME,
            CHUNK_TEXT,
            VECTOR_COSINE_SIMILARITY(CHUNK_EMBEDDING, q_emb) AS SIMILARITY_SCORE
        FROM POLICY_DOCUMENT_CHUNKS, query_vec
        ORDER BY SIMILARITY_SCORE DESC
        LIMIT {top_k}
    """
    return session.sql(vector_sql).to_pandas()

def analyze_and_log_feedback(cust_id, message_text):
    """Calculates sentiment score and logs feedback into database."""
    clean_msg = message_text.replace("'", "''")
    
    # 1. Sentiment Score (-1 to 1)
    sentiment_df = session.sql(f"SELECT SNOWFLAKE.CORTEX.SENTIMENT('{clean_msg}') AS SCORE").to_pandas()
    score = float(sentiment_df.iloc[0]['SCORE'])
    
    # 2. Category Classification
    cat_prompt = f"Categorize this message into ONE of [Delivery Issue, Quality Issue, Refund/Return, General Inquiry]: '{clean_msg}'. Return ONLY the category name."
    cat_df = session.sql(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b', '{cat_prompt.replace(chr(39), chr(39)+chr(39))}') AS CAT").to_pandas()
    category = cat_df.iloc[0]['CAT'].strip()
    
    # 3. Log to Table
    log_sql = f"""
        INSERT INTO CUSTOMER_FEEDBACK (CUSTOMER_ID, ORDER_ID, MESSAGE, CATEGORY, SENTIMENT_SCORE)
        VALUES ('{cust_id}', 'N/A', '{clean_msg}', '{category}', {score})
    """
    session.sql(log_sql).collect()
    
    return score, category

# --- User Query Processing Pipeline ---
if user_input := st.chat_input("Ask about delivery rules, damaged items, cancellations, or your orders..."):
    
    # Display User Input
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Searching online shopping policies & order logs..."):
            
            # 1. Sentiment Logging
            sentiment_score, feedback_category = analyze_and_log_feedback(customer_id, user_input)
            
            # 2. Vector Search across Policy Documents
            policy_results_df = search_policy_documents(user_input, top_k=3)
            
            # 3. Fetch Transactional & Catalog Data
            orders_df = fetch_customer_order_history(customer_id)
            catalog_df = fetch_product_catalog()
            
            # Format Context Strings
            policy_context = "\n\n".join([
                f"--- Document: [{row['DOC_NAME']}] ---\n{row['CHUNK_TEXT']}" 
                for _, row in policy_results_df.iterrows()
            ])
            orders_context = orders_df.to_string(index=False) if not orders_df.empty else "No recent order history found."
            catalog_context = catalog_df.to_string(index=False)

            # 4. Prompt Engineering for Cortex LLM
            prompt = f"""
            You are an official E-Grocery Customer Support Agent. Answer the customer query accurately and politely.
            
            CRITICAL INSTRUCTIONS:
            1. Rely STRICTLY on the Online Shopping Policy Documents, Product Catalog, and Customer Order History provided below.
            2. When referencing policy guidelines (such as return windows, cancellation fees, or refund times), EXPLICITLY CITE the document source name.
            3. If the sentiment score is less than -0.5 (frustrated customer), offer an immediate escalation option to human support.
            
            Customer Profile ID: {customer_id}
            
            Online Shopping Policy Documents Context:
            {policy_context}
            
            Product Catalog & Stock Data:
            {catalog_context}
            
            Customer Order History:
            {orders_context}
            
            Customer Query: {user_input}
            """
            
            escaped_prompt = prompt.replace("'", "''")
            llm_sql = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{llm_model}', '{escaped_prompt}') AS RESPONSE"
            response_df = session.sql(llm_sql).to_pandas()
            assistant_reply = response_df.iloc[0]['RESPONSE']

            # Render Response
            st.markdown(assistant_reply)
            
            # Expandable Section displaying Document Grounding Citations
            with st.expander("📄 Referenced Online Policy Documents & Grounding Data"):
                st.write("**Retrieved Policy Chunks (Vector Cosine Match):**")
                for _, row in policy_results_df.iterrows():
                    st.markdown(f"📄 **Document:** `{row['DOC_NAME']}` | **Match Score:** `{row['SIMILARITY_SCORE']:.4f}`")
                    st.caption(row['CHUNK_TEXT'])
                    st.divider()
                
                st.write("**Customer Transaction Log:**")
                st.dataframe(orders_df, use_container_width=True)

    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
