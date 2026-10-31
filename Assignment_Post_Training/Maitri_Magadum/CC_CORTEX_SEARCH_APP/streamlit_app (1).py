import json

import streamlit as st
from snowflake.core import Root
from snowflake.snowpark.context import get_active_session

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CORTEX_SEARCH_DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
CORTEX_SEARCH_SCHEMA = "DATA"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"

COLUMNS = ["chunk", "chunk_index", "relative_path", "category"]
MODELS = [
    "llama3.1-70b",
    "llama3.1-8b",
    "snowflake-llama-3.3-70b",
    "claude-4-sonnet",
    "mistral-large2",
]
LINK_TTL_SECONDS = 3600

SUGGESTIONS = [
    "Is there a special lubricant for the premium bike?",
    "What maintenance does the bike need each season?",
    "Which accessories fit the mountain bike?",
]

st.set_page_config(page_title="Ask your documents", page_icon="❄️", layout="centered")

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    :root {
        --ink: #0F2A3D;
        --ink-soft: #4C6475;
        --frost: #EAF4FA;
        --mist: #F6FAFC;
        --line: #D5E3EC;
        --blue: #1F8FD6;
        --blue-deep: #11567F;
    }

    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--mist); }

    /* hide Streamlit chrome */
    #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
    .block-container { padding-top: 2.5rem; max-width: 780px; }

    /* hero */
    .hero {
        background: linear-gradient(135deg, var(--blue-deep) 0%, var(--blue) 100%);
        border-radius: 22px;
        padding: 2.2rem 2.2rem 2rem 2.2rem;
        color: #fff;
        margin-bottom: 1.4rem;
    }
    .hero h1 {
        font-size: 2rem; font-weight: 800; letter-spacing: -0.02em;
        margin: 0 0 .4rem 0; color: #fff;
    }
    .hero p { margin: 0; font-size: 1rem; opacity: .88; max-width: 34rem; }

    /* chat bubbles */
    [data-testid="stChatMessage"] {
        background: #fff;
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 1rem 1.2rem;
        margin-bottom: .8rem;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background: var(--frost);
        border-color: transparent;
    }

    /* suggestion buttons */
    div.stButton > button {
        width: 100%;
        text-align: left;
        background: #fff;
        color: var(--ink);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: .75rem 1rem;
        font-weight: 500;
        transition: border-color .15s ease, background .15s ease;
    }
    div.stButton > button:hover { border-color: var(--blue); background: var(--frost); color: var(--blue-deep); }
    div.stButton > button:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }

    /* chat input */
    [data-testid="stChatInput"] { border-radius: 14px; border: 1px solid var(--line); }

    /* sources */
    [data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 12px; background: var(--mist); }
    [data-testid="stExpander"] a { color: var(--blue-deep); font-weight: 600; text-decoration: none; }
    [data-testid="stExpander"] a:hover { text-decoration: underline; }

    /* sidebar */
    section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--line); }
    section[data-testid="stSidebar"] h3 { font-size: 1rem; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Snowflake connections
# ---------------------------------------------------------------------------
session = get_active_session()


@st.cache_resource
def get_search_service():
    root = Root(session)
    return (
        root.databases[CORTEX_SEARCH_DATABASE]
        .schemas[CORTEX_SEARCH_SCHEMA]
        .cortex_search_services[CORTEX_SEARCH_SERVICE]
    )


@st.cache_data(ttl=600)
def get_categories():
    rows = session.sql("select category from docs_chunks_table group by category").collect()
    return ["All"] + [row.CATEGORY for row in rows]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def search_chunks(query, category, num_chunks):
    svc = get_search_service()
    if category == "All":
        response = svc.search(query, COLUMNS, limit=num_chunks)
    else:
        response = svc.search(
            query, COLUMNS, filter={"@eq": {"category": category}}, limit=num_chunks
        )
    return json.loads(response.json())["results"]


def build_prompt(question, chunks):
    if not chunks:
        return f"Question: {question}\nAnswer:"

    context = "\n\n".join(item["chunk"] for item in chunks)
    return f"""
You are an expert assistant that extracts information from the CONTEXT provided
between <context> and </context> tags.
When answering the question between <question> and </question> tags,
be concise and do not hallucinate.
If you don't have the information, just say so.
Only answer if you can extract the answer from the CONTEXT.
Do not mention the CONTEXT in your answer.

<context>
{context}
</context>
<question>
{question}
</question>
Answer:
"""


def get_source_links(chunks):
    links = []
    for path in sorted({item["relative_path"] for item in chunks}):
        try:
            row = session.sql(
                "select GET_PRESIGNED_URL(@docs, ?, ?) as URL_LINK",
                params=[path, LINK_TTL_SECONDS],
            ).collect()[0]
            links.append((path, row["URL_LINK"]))
        except Exception:
            links.append((path, None))
    return links


def ask(question, model, use_docs, category, num_chunks):
    chunks = search_chunks(question, category, num_chunks) if use_docs else []
    prompt = build_prompt(question, chunks)

    result = session.sql(
        "select AI_COMPLETE(?, ?) as response",
        params=[model, prompt],
    ).collect()

    sources = get_source_links(chunks) if chunks else []
    return result[0]["RESPONSE"], sources


def render_sources(sources):
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for path, url in sources:
            st.markdown(f"[{path}]({url})" if url else path)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Settings")
    use_docs = st.toggle("Answer from my documents", value=True)

    category = "All"
    if use_docs:
        category = st.selectbox("Product category", get_categories())

    model = st.selectbox("Model", MODELS)
    num_chunks = st.slider("Passages per answer", 1, 8, 3, disabled=not use_docs)

    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

pending = st.session_state.pop("pending_question", None)

if not st.session_state.messages and not pending:
    st.markdown(
        """
        <div class="hero">
            <h1>Ask your documents</h1>
            <p>Get short, sourced answers from your product manuals and guides.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for i, text in enumerate(SUGGESTIONS):
        if st.button(text, key=f"suggestion_{i}"):
            st.session_state.pending_question = text
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_sources(msg.get("sources"))

question = st.chat_input("Ask a question about your documents") or pending

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching your documents..." if use_docs else "Thinking..."):
            try:
                answer, sources = ask(question, model, use_docs, category, num_chunks)
            except Exception as exc:
                answer, sources = f"Something went wrong while answering: {exc}", []
        st.markdown(answer)
        render_sources(sources)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )