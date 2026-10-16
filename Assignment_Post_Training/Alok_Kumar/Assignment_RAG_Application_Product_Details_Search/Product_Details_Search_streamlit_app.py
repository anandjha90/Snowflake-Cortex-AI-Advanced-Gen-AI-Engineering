import os
import time
import json
import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Product Document Search",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
session = get_active_session()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
SCHEMA = "DATA"
CHUNKS_TABLE = f"{DATABASE}.{SCHEMA}.DOCS_CHUNKS_TABLE"
STAGE = f"@{DATABASE}.{SCHEMA}.DOCS"
SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"

AVAILABLE_MODELS = [
    "claude-sonnet-4-5",
    "mistral-large3",
    "llama3.1-8b",
    "llama3.3-70b",
    "openai-gpt-5-mini",
]

CATEGORY_OPTIONS = ["All", "Snow", "Bike"]

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("show_chat_history", True)
st.session_state.setdefault("selected_model", AVAILABLE_MODELS[0])
st.session_state.setdefault("selected_category", "All")
st.session_state.setdefault("num_results", 5)
st.session_state.setdefault("response_length", 300)
st.session_state.setdefault("last_doc_refresh", 0.0)
st.session_state.setdefault("stage_files", pd.DataFrame())

# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120)
def get_document_inventory():
    return session.sql(f"""
        SELECT
            RELATIVE_PATH,
            CATEGORY,
            COUNT(*) AS CHUNKS,
            MAX(CHUNK_INDEX) + 1 AS TOTAL_CHUNKS
        FROM {CHUNKS_TABLE}
        GROUP BY RELATIVE_PATH, CATEGORY
        ORDER BY CATEGORY, RELATIVE_PATH
    """).to_pandas()


@st.cache_data(ttl=60)
def get_stage_files():
    rows = session.sql(f"LIST {STAGE}").collect()
    if rows:
        return pd.DataFrame([r.as_dict() for r in rows])
    return pd.DataFrame()


@st.cache_data(ttl=120)
def get_categories():
    df = session.sql(f"SELECT DISTINCT CATEGORY FROM {CHUNKS_TABLE} ORDER BY CATEGORY").to_pandas()
    return df["CATEGORY"].tolist()


def search_docs(query, category, num_results):
    """Call Cortex Search service via SEARCH_PREVIEW SQL function."""
    filter_obj = {"@eq": {"category": category}} if category != "All" else {}
    request_body = {
        "query": query,
        "columns": ["chunk", "relative_path", "category"],
        "filter": filter_obj,
        "limit": num_results,
    }
    service_fqn = f"{DATABASE}.{SCHEMA}.{SEARCH_SERVICE}"
    result = session.sql(
        "SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?)) AS res",
        params=[service_fqn, json.dumps(request_body)],
    ).collect()

    if result:
        parsed = json.loads(result[0]["RES"])
        return parsed.get("results", [])
    return []


def generate_answer(question, context, model, max_tokens):
    """Use Cortex COMPLETE to answer based on search context."""
    context_text = "\n\n---\n\n".join(
        [f"[{r.get('relative_path', 'unknown')}]\n{r.get('chunk', '')}" for r in context]
    )
    prompt = f"""You are a helpful product information assistant. Answer the user's question
ONLY based on the provided document context. If the answer cannot be found in the
context, respond: "This data is not available in the provided documents."

Be specific and cite which document the information comes from.

<context>
{context_text}
</context>

<question>
{question}
</question>

Answer (limit to roughly {max_tokens} words):"""

    response = session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS answer",
        params=[model, prompt],
    ).collect()

    if response:
        return response[0]["ANSWER"]
    return "Unable to generate a response."


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    st.subheader("LLM Model")
    selected_model = st.selectbox(
        "Choose a model for answers",
        AVAILABLE_MODELS,
        key="selected_model",
    )

    st.markdown("---")
    st.subheader("Search Filters")

    selected_category = st.selectbox(
        "Product Category",
        CATEGORY_OPTIONS,
        key="selected_category",
    )

    num_results = st.slider(
        "Number of search results",
        min_value=1,
        max_value=10,
        key="num_results",
    )

    response_length = st.slider(
        "Response length (approx. words)",
        min_value=50,
        max_value=1000,
        step=50,
        key="response_length",
    )

    st.markdown("---")
    st.subheader("Chat History")
    show_history = st.checkbox(
        "Show chat history",
        key="show_chat_history",
    )

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.experimental_rerun()

    st.markdown("---")
    st.caption(
        f"Database: `{DATABASE}`  \nSchema: `{SCHEMA}`  \n"
        f"Search Service: `{SEARCH_SERVICE}`"
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Product Document Search")
st.markdown(
    "Search product documentation using **Cortex Search** and get AI-powered answers. "
    "Documents are automatically indexed as new PDFs arrive at the stage."
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_search, tab_insights, tab_docs, tab_state = st.tabs(
    [
        "🔍 Product Search",
        "💡 AI Insights",
        "📄 Document Library",
        "🗄 Session State",
    ]
)

# =========================================================================
# TAB 1 — Product Search (Chat)
# =========================================================================
with tab_search:
    # Display chat history
    if st.session_state.show_chat_history and st.session_state.messages:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(
                    f'<div style="background-color:#e3f2fd;padding:10px 15px;border-radius:8px;margin-bottom:8px;">'
                    f'<strong>🧑 You:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="background-color:#f5f5f5;padding:10px 15px;border-radius:8px;margin-bottom:8px;">'
                    f'<strong>🤖 Assistant:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
                if "sources" in msg and msg["sources"]:
                    with st.expander("Sources"):
                        for src in msg["sources"]:
                            st.markdown(f"- **{src['file']}** ({src['category']})")
        st.markdown("---")

    # Suggestion chips only before first message
    if not st.session_state.messages:
        st.info("Ask questions about product specifications, features, or usage guidelines.")
        SUGGESTIONS = {
            "What ski products are available?": "What ski products are available?",
            "Tell me about the Xtreme Road Bike": "Tell me about the Xtreme Road Bike 105 SL",
            "What are TDBootz ski boot features?": "What are the key features of TDBootz Special ski boots?",
            "Compare bike products": "Compare the different bike products available",
        }
        cols = st.columns(len(SUGGESTIONS))
        selected = None
        for i, (label, query) in enumerate(SUGGESTIONS.items()):
            if cols[i].button(label, key=f"suggest_{i}"):
                selected = query
        if selected:
            st.session_state.messages.append({"role": "user", "content": selected})
            st.experimental_rerun()

    # Process pending query (shows answer above the input box)
    pending = st.session_state.pop("_pending_query", None)
    if pending:
        prompt = pending
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.markdown(
            f'<div style="background-color:#e3f2fd;padding:10px 15px;border-radius:8px;margin-bottom:8px;">'
            f'<strong>🧑 You:</strong> {prompt}</div>',
            unsafe_allow_html=True,
        )

        with st.spinner("Searching documents..."):
            search_results = search_docs(
                prompt,
                st.session_state.selected_category,
                st.session_state.num_results,
            )

        if not search_results:
            answer = "This data is not available in the provided documents."
            st.markdown(
                f'<div style="background-color:#f5f5f5;padding:10px 15px;border-radius:8px;margin-bottom:8px;">'
                f'<strong>🤖 Assistant:</strong> {answer}</div>',
                unsafe_allow_html=True,
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "sources": []}
            )
        else:
            with st.spinner(f"Generating answer with {st.session_state.selected_model}..."):
                answer = generate_answer(
                    prompt,
                    search_results,
                    st.session_state.selected_model,
                    st.session_state.response_length,
                )
            st.markdown(
                f'<div style="background-color:#f5f5f5;padding:10px 15px;border-radius:8px;margin-bottom:8px;">'
                f'<strong>🤖 Assistant:</strong> {answer}</div>',
                unsafe_allow_html=True,
            )

            sources = [
                {
                    "file": r.get("relative_path", "unknown"),
                    "category": r.get("category", ""),
                }
                for r in search_results
            ]
            unique_sources = list({s["file"]: s for s in sources}.values())

            with st.expander("Sources"):
                for src in unique_sources:
                    st.markdown(f"- **{src['file']}** ({src['category']})")

            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "sources": unique_sources}
            )

    # Search input — always at the bottom
    def _submit_query():
        if st.session_state.get("_chat_input_val"):
            st.session_state["_pending_query"] = st.session_state["_chat_input_val"]
            st.session_state["_chat_input_val"] = ""

    st.markdown("""
    <style>
    /* Highlight the search input box */
    .stTextInput input,
    .stTextInput > div > div > input,
    input[type="text"] {
        background-color: #1a73e8 !important;
        border: 2px solid white !important;
        border-radius: 25px !important;
        padding: 10px 18px !important;
        font-size: 16px !important;
        color: white !important;
    }
    .stTextInput input:focus,
    .stTextInput > div > div > input:focus,
    input[type="text"]:focus {
        border-color: white !important;
        box-shadow: none !important;
        outline: none !important;
    }
    /* Remove red/default focus border from wrapper divs */
    .stTextInput > div,
    .stTextInput > div > div,
    .stTextInput [data-baseweb="input"],
    .stTextInput [data-baseweb="base-input"] {
        border-color: white !important;
        box-shadow: none !important;
    }
    .stTextInput > div:focus-within,
    .stTextInput > div > div:focus-within,
    .stTextInput [data-baseweb="input"]:focus-within,
    .stTextInput [data-baseweb="base-input"]:focus-within {
        border-color: white !important;
        box-shadow: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    input_col, btn_col = st.columns([12, 1])
    with input_col:
        st.text_input(
            "Ask about product documentation...",
            key="_chat_input_val",
            on_change=_submit_query,
        )
    with btn_col:
        st.markdown(
            '<div style="padding-top:29px;">'
            '<div style="background-color:#1a73e8;color:white;border-radius:50%;'
            'width:42px;height:42px;display:flex;align-items:center;'
            'justify-content:center;font-size:22px;cursor:pointer;">➤</div></div>',
            unsafe_allow_html=True,
        )

# =========================================================================
# TAB 2 — AI Insights
# =========================================================================
with tab_insights:
    st.subheader("AI-Powered Document Insights")
    st.markdown("Use Cortex AI functions to analyze product documents.")

    doc_inventory = get_document_inventory()
    doc_names = doc_inventory["RELATIVE_PATH"].tolist()

    col_doc, col_model = st.columns([2, 1])
    with col_doc:
        selected_doc = st.selectbox(
            "Select a document",
            doc_names,
            key="insight_doc",
        )
    with col_model:
        insight_model = st.selectbox(
            "Model for insights",
            AVAILABLE_MODELS,
            key="insight_model",
        )

    if selected_doc:
        # Fetch all chunks for the selected doc
        chunks_df = session.sql(
            f"SELECT CHUNK, CHUNK_INDEX, CATEGORY FROM {CHUNKS_TABLE} WHERE RELATIVE_PATH = ? ORDER BY CHUNK_INDEX",
            params=[selected_doc],
        ).to_pandas()

        doc_text = "\n\n".join(chunks_df["CHUNK"].tolist())
        doc_category = chunks_df["CATEGORY"].iloc[0] if len(chunks_df) > 0 else "Unknown"

        st.markdown(f"**Category:** {doc_category} | **Chunks:** {len(chunks_df)}")

        insight_tab_summary, insight_tab_sentiment, insight_tab_classify, insight_tab_raw = st.tabs(
            ["Summary", "Sentiment", "Classification", "Raw Chunks"]
        )

        # --- Summary ---
        with insight_tab_summary:
            if st.button("Generate Summary", key="btn_summary"):
                with st.spinner("Generating summary..."):
                    truncated = doc_text[:8000]
                    summary_prompt = (
                        "Summarize the following product document in a clear, "
                        "structured way with bullet points for key features "
                        "and specifications:\n\n" + truncated
                    )
                    result = session.sql(
                        "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS summary",
                        params=[insight_model, summary_prompt],
                    ).collect()
                    if result:
                        st.markdown(result[0]["SUMMARY"])

        # --- Sentiment ---
        with insight_tab_sentiment:
            if st.button("Analyze Sentiment", key="btn_sentiment"):
                with st.spinner("Analyzing sentiment per chunk..."):
                    sentiment_results = []
                    for _, row in chunks_df.iterrows():
                        chunk_preview = row["CHUNK"][:500]
                        res = session.sql(
                            "SELECT AI_SENTIMENT(?) AS score",
                            params=[chunk_preview],
                        ).collect()
                        if res:
                            sentiment_results.append({
                                "Chunk": int(row["CHUNK_INDEX"]),
                                "Score": float(res[0]["SCORE"]),
                                "Preview": row["CHUNK"][:100] + "...",
                            })

                    if sentiment_results:
                        sent_df = pd.DataFrame(sentiment_results)
                        avg_score = sent_df["Score"].mean()

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Average Sentiment", f"{avg_score:.3f}")
                        col2.metric("Most Positive", f"{sent_df['Score'].max():.3f}")
                        col3.metric("Most Negative", f"{sent_df['Score'].min():.3f}")

                        st.bar_chart(sent_df, x="Chunk", y="Score")
                        with st.expander("Detail Table"):
                            st.dataframe(sent_df, use_container_width=True)

        # --- Classification ---
        with insight_tab_classify:
            st.markdown("Classify document chunks into product-related categories.")
            classify_categories = st.text_input(
                "Categories (comma-separated)",
                value="specifications, features, safety, maintenance, overview",
                key="classify_cats",
            )
            if st.button("Classify Chunks", key="btn_classify"):
                cats_list = [c.strip() for c in classify_categories.split(",") if c.strip()]
                if cats_list:
                    with st.spinner("Classifying..."):
                        cats_json = json.dumps(cats_list)
                        classify_results = []
                        for _, row in chunks_df.iterrows():
                            chunk_preview = row["CHUNK"][:1000]
                            res = session.sql(
                                "SELECT AI_CLASSIFY(?, PARSE_JSON(?)::ARRAY) AS classification",
                                params=[chunk_preview, cats_json],
                            ).collect()
                            if res:
                                parsed = json.loads(res[0]["CLASSIFICATION"])
                                classify_results.append({
                                    "Chunk": int(row["CHUNK_INDEX"]),
                                    "Label": parsed.get("label", "unknown"),
                                    "Score": round(float(parsed.get("score", 0)), 3),
                                    "Preview": row["CHUNK"][:80] + "...",
                                })

                        if classify_results:
                            cls_df = pd.DataFrame(classify_results)
                            label_counts = cls_df["Label"].value_counts()
                            st.bar_chart(label_counts)
                            with st.expander("Detail Table"):
                                st.dataframe(cls_df, use_container_width=True)

        # --- Raw Chunks ---
        with insight_tab_raw:
            st.markdown(f"**All {len(chunks_df)} chunks** for *{selected_doc}*:")
            for _, row in chunks_df.iterrows():
                with st.expander(f"Chunk {int(row['CHUNK_INDEX'])}"):
                    st.text(row["CHUNK"])

# =========================================================================
# TAB 3 — Document Library
# =========================================================================
with tab_docs:
    st.subheader("Document Library")
    st.markdown(
        "All PDF documents available on the stage. "
        "The list auto-refreshes every 60 seconds to pick up new files."
    )

    # Auto-refresh logic
    now = time.time()
    if now - st.session_state.last_doc_refresh > 60:
        get_stage_files.clear()
        st.session_state.last_doc_refresh = now

    stage_df = get_stage_files()

    if stage_df is not None and len(stage_df) > 0:
        display_df = stage_df.copy()
        if "name" in display_df.columns:
            display_df["Document"] = display_df["name"].apply(
                lambda x: x.split("/")[-1] if "/" in str(x) else x
            )
        if "size" in display_df.columns:
            display_df["Size (KB)"] = (display_df["size"].astype(float) / 1024).round(1)

        cols_to_show = []
        if "Document" in display_df.columns:
            cols_to_show.append("Document")
        if "Size (KB)" in display_df.columns:
            cols_to_show.append("Size (KB)")
        if "last_modified" in display_df.columns:
            cols_to_show.append("last_modified")
        if "md5" in display_df.columns:
            cols_to_show.append("md5")

        if cols_to_show:
            st.dataframe(
                display_df[cols_to_show],
                use_container_width=True,
            )
        else:
            st.dataframe(display_df, use_container_width=True)

        st.metric("Total Documents", len(stage_df))
    else:
        st.info("No documents found on the stage.")

    st.markdown("---")
    st.subheader("Document Inventory (Chunked)")
    st.markdown("Shows how each document was chunked for search indexing.")
    inventory_df = get_document_inventory()
    st.dataframe(inventory_df, use_container_width=True)

    st.caption(
        f"Last refreshed: {time.strftime('%H:%M:%S', time.localtime(st.session_state.last_doc_refresh))} "
        f"| Auto-refresh every 60s | Cortex Search Service refreshes every 30 min"
    )

# =========================================================================
# TAB 4 — Session State
# =========================================================================
with tab_state:
    st.subheader("Session State")
    st.markdown("Current session state keys and values for debugging.")

    state_items = []
    for key in sorted(st.session_state.keys()):
        val = st.session_state[key]
        val_type = type(val).__name__
        if isinstance(val, list):
            display_val = f"[{len(val)} items]"
        elif isinstance(val, pd.DataFrame):
            display_val = f"DataFrame({len(val)} rows)"
        elif isinstance(val, dict):
            display_val = f"dict({len(val)} keys)"
        elif isinstance(val, str) and len(val) > 100:
            display_val = val[:100] + "..."
        else:
            display_val = str(val)
        state_items.append({"Key": key, "Type": val_type, "Value": display_val})

    if state_items:
        st.dataframe(
            pd.DataFrame(state_items),
            use_container_width=True,
        )

    with st.expander("Full Session State (JSON)"):
        safe_state = {}
        for k in sorted(st.session_state.keys()):
            v = st.session_state[k]
            if isinstance(v, pd.DataFrame):
                safe_state[k] = f"<DataFrame: {len(v)} rows>"
            elif isinstance(v, list):
                safe_state[k] = v
            else:
                try:
                    json.dumps(v)
                    safe_state[k] = v
                except (TypeError, ValueError):
                    safe_state[k] = str(v)
        st.json(safe_state)
