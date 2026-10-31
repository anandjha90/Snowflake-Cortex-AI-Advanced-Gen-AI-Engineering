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

SLIDE_WINDOW = 7          # how many recent messages the assistant remembers

SUGGESTIONS = [
    "Is there a special lubricant for the premium bike?",
    "What maintenance does the bike need each season?",
    "Which accessories fit the mountain bike?",
]

st.set_page_config(page_title="Chatbot", page_icon="❄️", layout="centered")

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

    #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
    .block-container { padding-top: 2.5rem; max-width: 780px; }

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

    [data-testid="stChatInput"] { border-radius: 14px; border: 1px solid var(--line); }


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
    rows = session.table("docs_chunks_table").select("category").distinct().collect()
    return ["All"] + sorted(row.CATEGORY for row in rows)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def complete(model, prompt):
    row = session.sql(
        "select AI_COMPLETE(?, ?) as response", params=[model, prompt]
    ).collect()[0]
    return row["RESPONSE"]


def search_chunks(query, category, num_chunks):
    svc = get_search_service()
    if category == "All":
        response = svc.search(query, COLUMNS, limit=num_chunks)
    else:
        response = svc.search(
            query, COLUMNS, filter={"@eq": {"category": category}}, limit=num_chunks
        )
    return json.loads(response.json())["results"]


def format_history(history):
    return "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in history
    )


def rewrite_question(history, question, model):
    """Turn a follow-up like 'what about the cheaper one?' into a standalone search query."""
    prompt = f"""
Based on the chat history below and the question, write a query that extends the
question with the chat history. The query should be in natural language.
Answer with only the query. Do not add any explanation.

<chat_history>
{format_history(history)}
</chat_history>
<question>
{question}
</question>
"""
    return complete(model, prompt).strip()


def build_prompt(question, chunks, history):
    context = "\n\n".join(item["chunk"] for item in chunks)

    if not chunks:
        return f"""
You are a helpful assistant. Use the conversation so far if it helps.

<chat_history>
{format_history(history)}
</chat_history>
<question>
{question}
</question>
Answer:
"""

    return f"""
You are an expert assistant that extracts information from the CONTEXT provided
between <context> and </context> tags.
You also consider the conversation in <chat_history> and </chat_history> tags.
When answering the question between <question> and </question> tags,
be concise and do not hallucinate.
If you don't have the information, just say so.
Only answer if you can extract the answer from the CONTEXT.
Do not mention the CONTEXT or the CHAT HISTORY in your answer.

<chat_history>
{format_history(history)}
</chat_history>
<context>
{context}
</context>
<question>
{question}
</question>
Answer:
"""


def ask(question, history, settings):
    model = settings["model"]

    search_query = question
    if settings["remember"] and history:
        search_query = rewrite_question(history, question, model)

    chunks = []
    if settings["use_docs"]:
        chunks = search_chunks(search_query, settings["category"], settings["num_chunks"])

    prompt = build_prompt(question, chunks, history if settings["remember"] else [])
    return complete(model, prompt)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


def start_over():
    st.session_state.messages = []


with st.sidebar:
    st.markdown("### Settings")
    use_docs = st.toggle("Answer from my documents", value=True)

    category = "All"
    if use_docs:
        category = st.selectbox("Product category", get_categories())

    model = st.selectbox("Model", MODELS)
    remember = st.toggle("Remember this conversation", value=True)
    num_chunks = st.slider("Passages per answer", 1, 8, 3, disabled=not use_docs)

    st.button("Start over", on_click=start_over)

settings = {
    "use_docs": use_docs,
    "category": category,
    "model": model,
    "remember": remember,
    "num_chunks": num_chunks,
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
pending = st.session_state.pop("pending_question", None)
question = st.chat_input("Ask a question about your documents") or pending

# Hide the welcome screen as soon as a question is asked (typed or clicked)
if not st.session_state.messages and not question:
    st.markdown(
        """
        <div class="hero">
            <h1>Document Assistant Chatbot</h1>
            <p>Get short, clear answers from your product manuals and guides.</p>
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

if question:
    # Take the history before adding the new question
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[-SLIDE_WINDOW:]
    ]

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching your documents..." if use_docs else "Thinking..."):
            try:
                answer = ask(question, history, settings)
            except Exception as exc:
                answer = f"Something went wrong while answering: {exc}"
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})