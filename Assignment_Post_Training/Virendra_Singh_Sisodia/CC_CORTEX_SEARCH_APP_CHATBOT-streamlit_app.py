import os
import json
import uuid

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Cortex Search Chatbot",
    page_icon=":speech_balloon:",
    layout="wide",
)

pd.set_option("max_colwidth", None)

### Default Values
CORTEX_SEARCH_DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
CORTEX_SEARCH_SCHEMA = "DATA"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"
FQ_SCHEMA = f"{CORTEX_SEARCH_DATABASE}.{CORTEX_SEARCH_SCHEMA}"
FQ_SERVICE = f"{FQ_SCHEMA}.{CORTEX_SEARCH_SERVICE}"
CHUNKS_TABLE = f"{FQ_SCHEMA}.DOCS_CHUNKS_TABLE"
SESSIONS_TABLE = f"{FQ_SCHEMA}.CHAT_SESSIONS"
MESSAGES_TABLE = f"{FQ_SCHEMA}.CHAT_MESSAGES"
DOCS_STAGE = f"@{FQ_SCHEMA}.docs"

# columns to query in the service
COLUMNS = ["chunk", "chunk_index", "relative_path", "category"]

# Cortex COMPLETE models verified as available in this account/region
MODELS = [
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-haiku-4-5",
    "openai-gpt-5",
    "openai-gpt-5.1",
    "openai-gpt-5-mini",
    "openai-gpt-5-nano",
    "gemini-2.5-flash",
    "mistral-large3",
    "mistral-7b",
    "llama3.3-70b",
    "llama3.1-70b",
    "llama3.1-8b",
]

LANGUAGES = {
    "French": "fr", "German": "de", "Spanish": "es", "Italian": "it", "Portuguese": "pt",
    "Japanese": "ja", "Korean": "ko", "Chinese": "zh", "Hindi": "hi", "Russian": "ru",
    "Arabic": "ar", "Dutch": "nl", "Polish": "pl", "Swedish": "sv",
}

session = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL")).session()

### Styling

st.markdown(
    """
    <style>
    .hero {
        background: linear-gradient(120deg, #7C3AED 0%, #2563EB 50%, #06B6D4 100%);
        padding: 1.4rem 1.8rem; border-radius: 18px; color: white; margin-bottom: 1rem;
        box-shadow: 0 10px 30px rgba(124, 58, 237, 0.25);
    }
    .hero h1 { color: white; margin: 0; font-size: 2.1rem; }
    .hero p { color: #E0E7FF; margin: .3rem 0 0 0; font-size: 1.02rem; }
    .pill {
        display: inline-block; padding: .18rem .7rem; margin: .15rem .25rem .15rem 0;
        border-radius: 999px; font-size: .8rem; font-weight: 600;
        background: #EDE9FE; color: #5B21B6; border: 1px solid #DDD6FE;
    }
    .kpi {
        border-radius: 16px; padding: 1rem 1.2rem; color: white;
        box-shadow: 0 6px 18px rgba(0,0,0,.08);
    }
    .kpi .v { font-size: 1.9rem; font-weight: 800; }
    .kpi .l { font-size: .85rem; opacity: .9; }
    .k1 { background: linear-gradient(135deg,#7C3AED,#A855F7); }
    .k2 { background: linear-gradient(135deg,#2563EB,#3B82F6); }
    .k3 { background: linear-gradient(135deg,#0891B2,#06B6D4); }
    .k4 { background: linear-gradient(135deg,#DB2777,#F472B6); }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F5F3FF 0%, #EEF2FF 60%, #ECFEFF 100%);
    }
    .stTabs [data-baseweb="tab"] { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def kpi(col, value, label, css):
    col.markdown(
        f'<div class="kpi {css}"><div class="v">{value}</div><div class="l">{label}</div></div>',
        unsafe_allow_html=True,
    )


### Snowflake helpers

@st.cache_resource(show_spinner=False)
def ensure_history_tables():
    session.sql(
        f"""create table if not exists {SESSIONS_TABLE} (
            chat_id string, title string, user_name string,
            created_at timestamp_ltz default current_timestamp(),
            updated_at timestamp_ltz default current_timestamp())"""
    ).collect()
    session.sql(
        f"""create table if not exists {MESSAGES_TABLE} (
            chat_id string, msg_id string, role string, content string,
            model string, sources string,
            created_at timestamp_ltz default current_timestamp())"""
    ).collect()
    return True


@st.cache_data(ttl=600, show_spinner=False)
def current_user():
    return session.sql("select current_user() as u").collect()[0]["U"]


@st.cache_data(ttl=600, show_spinner=False)
def load_categories():
    rows = session.sql(f"select distinct category from {CHUNKS_TABLE} order by 1").collect()
    return [r["CATEGORY"] for r in rows if r["CATEGORY"]]


@st.cache_data(ttl=600, show_spinner=False)
def load_documents():
    df = session.sql(f"ls {DOCS_STAGE}").to_pandas()
    # LS column names may come back quoted/uppercased (e.g. '"name"'), so normalize them
    df.columns = [c.strip('"').lower() for c in df.columns]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_chunks():
    return session.sql(
        f"""select relative_path, category, chunk_index, chunk, length(chunk) as chunk_len
            from {CHUNKS_TABLE}"""
    ).to_pandas()


def complete(model, prompt, temperature=0.3):
    """Run AI_COMPLETE with the chosen model and temperature."""
    try:
        rows = session.sql(
            """select ai_complete(model => ?, prompt => ?,
                   model_parameters => object_construct('temperature', ?::float)) as r""",
            params=[model, prompt, float(temperature)],
        ).collect()
        return rows[0]["R"]
    except Exception as e:
        return f":warning: Model `{model}` failed: {e}"


def search_chunks(query, category, limit):
    search_request = {"query": query, "columns": COLUMNS, "limit": limit}
    if category != "ALL":
        search_request["filter"] = {"@eq": {"category": category}}
    # SEARCH_PREVIEW requires constant arguments, so escape the JSON as a SQL string literal
    request_literal = json.dumps(search_request).replace("\\", "\\\\").replace("'", "''")
    response = session.sql(
        f"select snowflake.cortex.search_preview('{FQ_SERVICE}', '{request_literal}') as response"
    ).collect()[0]["RESPONSE"]
    return json.loads(response).get("results", [])


def presigned_url(path):
    rows = session.sql(
        f"select get_presigned_url({DOCS_STAGE}, ?, 360) as url", params=[path]
    ).collect()
    return rows[0]["URL"]


### Chat persistence

def list_chats(user):
    return session.sql(
        f"""select chat_id, title, updated_at from {SESSIONS_TABLE}
            where user_name = ? order by updated_at desc limit 50""",
        params=[user],
    ).collect()


def load_messages(chat_id):
    rows = session.sql(
        f"""select role, content, model, sources from {MESSAGES_TABLE}
            where chat_id = ? order by created_at, msg_id""",
        params=[chat_id],
    ).collect()
    return [
        {
            "role": r["ROLE"],
            "content": r["CONTENT"],
            "model": r["MODEL"],
            "sources": json.loads(r["SOURCES"]) if r["SOURCES"] else [],
        }
        for r in rows
    ]


def save_message(chat_id, msg):
    session.sql(
        f"""insert into {MESSAGES_TABLE} (chat_id, msg_id, role, content, model, sources)
            values (?, ?, ?, ?, ?, ?)""",
        params=[
            chat_id, str(uuid.uuid4()), msg["role"], msg["content"],
            msg.get("model"), json.dumps(msg.get("sources", [])),
        ],
    ).collect()
    session.sql(
        f"update {SESSIONS_TABLE} set updated_at = current_timestamp() where chat_id = ?",
        params=[chat_id],
    ).collect()


def create_chat(chat_id, user, first_question, model):
    title = complete(
        model,
        "Create a short title (max 6 words, no quotes) for a chat that starts with: "
        + first_question,
        0.2,
    ).strip().strip('"')[:80]
    if title.startswith(":warning:"):
        title = first_question[:60]
    session.sql(
        f"insert into {SESSIONS_TABLE} (chat_id, title, user_name) values (?, ?, ?)",
        params=[chat_id, title, user],
    ).collect()


def delete_chat(chat_id):
    session.sql(f"delete from {MESSAGES_TABLE} where chat_id = ?", params=[chat_id]).collect()
    session.sql(f"delete from {SESSIONS_TABLE} where chat_id = ?", params=[chat_id]).collect()


### Session state

def new_chat():
    st.session_state.chat_id = None
    st.session_state.messages = []
    st.session_state.debug_info = {}


def start_over():
    keep = {"model_name", "category_value"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]
    new_chat()


def open_chat(chat_id):
    st.session_state.chat_id = chat_id
    st.session_state.messages = load_messages(chat_id)
    st.session_state.debug_info = {}


def remove_chat(chat_id):
    delete_chat(chat_id)
    if st.session_state.get("chat_id") == chat_id:
        new_chat()


def refresh_data():
    load_categories.clear()
    load_documents.clear()
    load_chunks.clear()


if "messages" not in st.session_state:
    new_chat()

ensure_history_tables()
user = current_user()

### Sidebar

with st.sidebar:
    st.markdown("## :rainbow[Cortex Chatbot]")
    st.button("➕ New chat", on_click=new_chat, use_container_width=True, type="primary")

    st.selectbox("Select your model:", MODELS, key="model_name")
    st.selectbox(
        "Select what products you are looking for", ["ALL"] + load_categories(), key="category_value"
    )

    use_history = st.checkbox("Do you want that I remember the chat history?", value=True)
    history_len = st.slider(
        "Messages to remember", 2, 20, 7, disabled=not use_history,
        help="Number of previous messages used as context",
    )
    debug = st.checkbox("Debug: Click to see summary generated of previous conversation")

    with st.expander("⚙️ Advanced settings"):
        num_chunks = st.slider("Chunks retrieved as context", 1, 10, 3)
        temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.05)
        use_rag = st.toggle("Use my documents as context (RAG)", value=True)

    c1, c2 = st.columns(2)
    c1.button("🔄 Start Over", on_click=start_over, use_container_width=True)
    c2.button("♻️ Refresh data", on_click=refresh_data, use_container_width=True)

    st.markdown("### 🕘 Recent chats")
    chats = list_chats(user)
    if not chats:
        st.caption("No saved chats yet.")
    for c in chats:
        cc1, cc2 = st.columns([5, 1])
        active = c["CHAT_ID"] == st.session_state.chat_id
        cc1.button(
            ("🟣 " if active else "💬 ") + (c["TITLE"] or "Untitled"),
            key=f"open_{c['CHAT_ID']}", on_click=open_chat, args=(c["CHAT_ID"],),
            use_container_width=True,
        )
        cc2.button("🗑️", key=f"del_{c['CHAT_ID']}", on_click=remove_chat, args=(c["CHAT_ID"],))

    with st.expander("Session State"):
        st.write(st.session_state)

### Header

st.markdown(
    """
    <div class="hero">
      <h1>💬 Chat Document Assistant with Snowflake Cortex</h1>
      <p>Ask questions about your product documents · powered by Cortex Search + Cortex AI functions</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_chat, tab_docs, tab_ai, tab_corpus, tab_analytics = st.tabs(
    ["💬 Chat", "📄 Document Explorer", "🧠 AI Insights", "📊 Corpus Insights", "🗂️ Chat Analytics"]
)

### Chat tab

def summarize_history(history, question, model):
    prompt = f"""Based on the chat history below and the question, generate a standalone search
query that extends the question with the relevant context from the history.
Answer with only the query, no explanation.
<chat_history>{history}</chat_history>
<question>{question}</question>"""
    return complete(model, prompt, 0.0).replace("'", "")


def build_prompt(question, model):
    history = []
    if use_history:
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[-history_len:]
        ]
    debug_info = {"history_used": len(history)}

    if not use_rag:
        prompt = f"""You are a helpful assistant.
<chat_history>{history}</chat_history>
Question: {question}
Answer:"""
        debug_info["prompt"] = prompt
        return prompt, [], debug_info

    search_query = question
    if history:
        search_query = summarize_history(history, question, model)
        debug_info["history_summary"] = search_query

    results = search_chunks(search_query, st.session_state.category_value, num_chunks)
    debug_info["retrieved_chunks"] = results

    prompt = f"""
You are an expert chat assistant that extracts information from the CONTEXT provided
between <context> and </context> tags.
You offer a chat experience considering the information included in the CHAT HISTORY
provided between <chat_history> and </chat_history> tags.
When answering the question contained between <question> and </question> tags
be concise and do not hallucinate.
If you don't have the information just say so.
Do not mention the CONTEXT used in your answer.
Do not mention the CHAT HISTORY used in your answer.
Use markdown formatting (bullets, bold) where it helps readability.

<chat_history>{history}</chat_history>
<context>{json.dumps(results)}</context>
<question>{question}</question>
Answer:
"""
    debug_info["prompt"] = prompt
    sources = sorted({r["relative_path"] for r in results})
    return prompt, sources, debug_info


def render_sources(sources, key_prefix):
    if not sources:
        return
    with st.expander(f"🔎 Sources ({len(sources)})"):
        for path in sources:
            try:
                st.markdown(f"📘 [{path}]({presigned_url(path)})")
            except Exception:
                st.markdown(f"📘 {path}")


with tab_chat:
    docs_df = load_documents()
    with st.expander(f"📚 Documents available ({len(docs_df)}) — used to answer your questions"):
        show_cols = [c for c in ["name", "size", "last_modified"] if c in docs_df.columns]
        st.dataframe(docs_df[show_cols or list(docs_df.columns)], hide_index=True, use_container_width=True)

    st.markdown(
        f'<span class="pill">🤖 {st.session_state.model_name}</span>'
        f'<span class="pill">🏷️ {st.session_state.category_value}</span>'
        f'<span class="pill">🧠 Memory {"ON" if use_history else "OFF"}</span>'
        f'<span class="pill">📎 RAG {"ON" if use_rag else "OFF"}</span>',
        unsafe_allow_html=True,
    )

    if not st.session_state.messages:
        st.info("👋 Hi! Ask me anything about your documents, e.g. *Is there any special lubricant to be used with the premium bike?*")

    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "❄️"):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                if m.get("model"):
                    st.caption(f"Answered by `{m['model']}`")
                render_sources(m.get("sources"), f"hist_{i}")

    question = st.chat_input("What do you want to know about your products?")
    if question:
        model = st.session_state.model_name
        if st.session_state.chat_id is None:
            st.session_state.chat_id = str(uuid.uuid4())
            create_chat(st.session_state.chat_id, user, question, model)

        user_msg = {"role": "user", "content": question}
        with st.chat_message("user", avatar="🧑"):
            st.markdown(question)

        with st.chat_message("assistant", avatar="❄️"):
            with st.spinner(f"{model} is thinking..."):
                prompt, sources, debug_info = build_prompt(question, model)
                answer = complete(model, prompt, temperature)
            st.markdown(answer)
            st.caption(f"Answered by `{model}`")
            render_sources(sources, "new")

        assistant_msg = {"role": "assistant", "content": answer, "model": model, "sources": sources}
        st.session_state.messages += [user_msg, assistant_msg]
        st.session_state.debug_info = debug_info
        save_message(st.session_state.chat_id, user_msg)
        save_message(st.session_state.chat_id, assistant_msg)
        st.rerun()

    if debug and st.session_state.debug_info:
        info = st.session_state.debug_info
        with st.expander("🐞 Debug information", expanded=True):
            st.write(f"Messages of history used: **{info.get('history_used', 0)}**")
            if "history_summary" in info:
                st.markdown("**Summary of previous conversation (used as search query):**")
                st.info(info["history_summary"])
            if "retrieved_chunks" in info:
                st.markdown("**Retrieved chunks:**")
                st.json(info["retrieved_chunks"], expanded=False)
            st.markdown("**Final prompt:**")
            st.code(info.get("prompt", ""), language="text")

### Document Explorer tab

with tab_docs:
    chunks_df = load_chunks()
    st.subheader("📄 Explore document chunks")
    f1, f2, f3 = st.columns([1, 2, 1])
    cats = f1.multiselect("Category", sorted(chunks_df["CATEGORY"].dropna().unique()))
    filtered = chunks_df[chunks_df["CATEGORY"].isin(cats)] if cats else chunks_df
    docs = f2.multiselect("Document", sorted(filtered["RELATIVE_PATH"].unique()))
    if docs:
        filtered = filtered[filtered["RELATIVE_PATH"].isin(docs)]
    keyword = f3.text_input("Keyword contains")
    if keyword:
        filtered = filtered[filtered["CHUNK"].str.contains(keyword, case=False, na=False)]

    k1, k2, k3, k4 = st.columns(4)
    kpi(k1, filtered["RELATIVE_PATH"].nunique(), "Documents", "k1")
    kpi(k2, len(filtered), "Chunks", "k2")
    kpi(k3, filtered["CATEGORY"].nunique(), "Categories", "k3")
    kpi(k4, int(filtered["CHUNK_LEN"].mean()) if len(filtered) else 0, "Avg chunk length", "k4")

    st.markdown("#### Chunks per document")
    st.bar_chart(
        filtered.groupby("RELATIVE_PATH").size().rename("chunks"), color="#7C3AED", horizontal=True
    )
    st.dataframe(
        filtered.sort_values(["RELATIVE_PATH", "CHUNK_INDEX"]),
        hide_index=True, use_container_width=True,
        column_config={"CHUNK_LEN": st.column_config.ProgressColumn(
            "Chunk length", min_value=0, max_value=int(chunks_df["CHUNK_LEN"].max()), format="%d")},
    )

### AI Insights tab

with tab_ai:
    st.subheader("🧠 AI Insights with Cortex AI functions")
    all_docs = sorted(load_chunks()["RELATIVE_PATH"].unique())
    doc = st.selectbox("Select a document to analyze", all_docs, key="ai_doc")
    doc_where = f"from {CHUNKS_TABLE} where relative_path = ?"

    t_sum, t_sent, t_cls, t_ext, t_tr, t_flt, t_sim, t_tok, t_agg = st.tabs(
        ["📝 Summarize", "😊 Sentiment", "🏷️ Classify", "🔍 Extract", "🌍 Translate",
         "✅ Filter", "🔗 Similarity", "🔢 Tokens", "🧩 Custom AI_AGG"]
    )

    with t_sum:
        st.caption("`AI_SUMMARIZE_AGG` — summarize all chunks of the document")
        if st.button("Summarize document", key="b_sum"):
            with st.spinner("Summarizing..."):
                r = session.sql(f"select ai_summarize_agg(chunk) as r {doc_where}", params=[doc]).collect()
            st.success(r[0]["R"])

    with t_sent:
        st.caption("`AI_SENTIMENT` — sentiment of each chunk")
        if st.button("Analyze sentiment", key="b_sent"):
            with st.spinner("Scoring sentiment..."):
                df = session.sql(
                    f"""select chunk_index, ai_sentiment(chunk):categories[0]:sentiment::string as sentiment,
                        left(chunk, 200) as preview {doc_where} order by chunk_index""",
                    params=[doc],
                ).to_pandas()
            c1, c2 = st.columns([1, 2])
            c1.bar_chart(df["SENTIMENT"].value_counts(), color="#06B6D4")
            c2.dataframe(df, hide_index=True, use_container_width=True)

    with t_cls:
        st.caption("`AI_CLASSIFY` — classify each chunk into your labels")
        labels = st.multiselect(
            "Labels", ["Maintenance", "Specifications", "Safety", "Warranty", "Accessories", "Performance", "Pricing"],
            default=["Maintenance", "Specifications", "Safety", "Warranty"],
        )
        if st.button("Classify chunks", key="b_cls", disabled=len(labels) < 2):
            with st.spinner("Classifying..."):
                df = session.sql(
                    f"""select chunk_index, ai_classify(chunk, parse_json(?)::array):labels[0]::string as label,
                        left(chunk, 200) as preview {doc_where} order by chunk_index""",
                    params=[json.dumps(labels), doc],
                ).to_pandas()
            c1, c2 = st.columns([1, 2])
            c1.bar_chart(df["LABEL"].value_counts(), color="#A855F7")
            c2.dataframe(df, hide_index=True, use_container_width=True)

    with t_ext:
        st.caption("`AI_EXTRACT` — pull structured fields out of the document")
        fields = st.data_editor(
            pd.DataFrame({
                "field": ["product", "material", "weight", "warranty", "price"],
                "question": ["What product is described?", "What materials are used?",
                             "What is the weight?", "What is the warranty?", "What is the price?"],
            }),
            num_rows="dynamic", use_container_width=True, key="ext_fields",
        )
        if st.button("Extract fields", key="b_ext"):
            fmt = {r["field"]: r["question"] for _, r in fields.iterrows() if r["field"] and r["question"]}
            with st.spinner("Extracting..."):
                r = session.sql(
                    f"""select ai_extract(text => left(listagg(chunk, ' ') within group (order by chunk_index), 100000),
                        responseFormat => parse_json(?)):response as r {doc_where}""",
                    params=[json.dumps(fmt), doc],
                ).collect()
            res = json.loads(r[0]["R"])
            st.dataframe(pd.DataFrame(res.items(), columns=["Field", "Value"]), hide_index=True, use_container_width=True)

    with t_tr:
        st.caption("`AI_TRANSLATE` — translate a chunk")
        lang = st.selectbox("Target language", list(LANGUAGES))
        idx = st.number_input("Chunk index", min_value=0, value=0, step=1)
        if st.button("Translate", key="b_tr"):
            with st.spinner("Translating..."):
                r = session.sql(
                    f"""select chunk, ai_translate(chunk, 'en', ?) as t {doc_where} and chunk_index = ?""",
                    params=[LANGUAGES[lang], doc, int(idx)],
                ).collect()
            if r:
                c1, c2 = st.columns(2)
                c1.markdown("**Original**")
                c1.write(r[0]["CHUNK"])
                c2.markdown(f"**{lang}**")
                c2.write(r[0]["T"])
            else:
                st.warning("No chunk with that index.")

    with t_flt:
        st.caption("`AI_FILTER` — find chunks that satisfy a yes/no condition")
        cond = st.text_input("Condition", "Does this text mention brakes or braking?")
        scope = st.radio("Scope", ["Selected document", "All documents"], horizontal=True)
        if st.button("Run filter", key="b_flt"):
            sql = f"""select relative_path, chunk_index, chunk from {CHUNKS_TABLE}
                      where ai_filter(concat(?, ' Text: ', chunk))"""
            params = [cond]
            if scope == "Selected document":
                sql += " and relative_path = ?"
                params.append(doc)
            with st.spinner("Filtering..."):
                df = session.sql(sql, params=params).to_pandas()
            st.metric("Matching chunks", len(df))
            st.dataframe(df, hide_index=True, use_container_width=True)

    with t_sim:
        st.caption("`AI_SIMILARITY` — semantic similarity between documents and a text")
        text = st.text_input("Compare all documents against", "high performance mountain bike for downhill")
        if st.button("Compute similarity", key="b_sim"):
            with st.spinner("Computing..."):
                df = session.sql(
                    f"""select relative_path, max(ai_similarity(chunk, ?)) as similarity
                        from {CHUNKS_TABLE} group by 1 order by 2 desc""",
                    params=[text],
                ).to_pandas()
            st.bar_chart(df.set_index("RELATIVE_PATH")["SIMILARITY"], color="#DB2777", horizontal=True)

    with t_tok:
        st.caption("`AI_COUNT_TOKENS` — estimate tokens (and cost) per document")
        tok_model = st.selectbox("Model for token count", ["llama3.3-70b", "llama3.1-70b", "llama3.1-8b", "mistral-7b"])
        if st.button("Count tokens", key="b_tok"):
            with st.spinner("Counting..."):
                df = session.sql(
                    f"""select relative_path, sum(ai_count_tokens('ai_complete', ?, chunk)) as tokens
                        from {CHUNKS_TABLE} group by 1 order by 2 desc""",
                    params=[tok_model],
                ).to_pandas()
            st.metric("Total tokens in corpus", f"{int(df['TOKENS'].sum()):,}")
            st.bar_chart(df.set_index("RELATIVE_PATH")["TOKENS"], color="#2563EB", horizontal=True)

    with t_agg:
        st.caption("`AI_AGG` — run your own instruction over the whole document")
        instr = st.text_area("Instruction", "List the 5 most important features and who this product is for.")
        if st.button("Run AI_AGG", key="b_agg"):
            with st.spinner("Aggregating..."):
                r = session.sql(f"select ai_agg(chunk, ?) as r {doc_where}", params=[instr, doc]).collect()
            st.markdown(r[0]["R"])

### Corpus Insights tab

@st.cache_data(ttl=3600, show_spinner=False)
def category_summaries():
    return session.sql(
        f"select category, ai_summarize_agg(chunk) as summary from {CHUNKS_TABLE} group by 1 order by 1"
    ).to_pandas()


@st.cache_data(ttl=3600, show_spinner=False)
def faq_questions(model):
    titles = ", ".join(load_chunks()["RELATIVE_PATH"].unique())
    return complete(
        model,
        f"Here are product documents: {titles}. Suggest 8 useful questions a customer could ask "
        "a support chatbot about them, as a markdown numbered list.",
        0.5,
    )


with tab_corpus:
    st.subheader("📊 Corpus-wide insights")
    cdf = load_chunks()
    k1, k2, k3, k4 = st.columns(4)
    kpi(k1, cdf["RELATIVE_PATH"].nunique(), "Documents", "k1")
    kpi(k2, len(cdf), "Chunks", "k2")
    kpi(k3, cdf["CATEGORY"].nunique(), "Categories", "k3")
    kpi(k4, f"{int(cdf['CHUNK_LEN'].sum()):,}", "Characters indexed", "k4")

    c1, c2 = st.columns(2)
    c1.markdown("#### Chunks by category")
    c1.bar_chart(cdf.groupby("CATEGORY").size().rename("chunks"), color="#7C3AED")
    c2.markdown("#### Text volume by document")
    c2.bar_chart(cdf.groupby("RELATIVE_PATH")["CHUNK_LEN"].sum(), color="#06B6D4", horizontal=True)

    st.markdown("#### 🧾 AI summary per category")
    if st.button("Generate category summaries"):
        with st.spinner("Summarizing each category with AI_SUMMARIZE_AGG..."):
            for _, r in category_summaries().iterrows():
                with st.expander(f"🏷️ {r['CATEGORY']}", expanded=True):
                    st.write(r["SUMMARY"])

    st.markdown("#### ❓ Suggested FAQs")
    if st.button("Suggest questions"):
        with st.spinner("Generating..."):
            st.markdown(faq_questions(st.session_state.model_name))

### Chat Analytics tab

with tab_analytics:
    st.subheader("🗂️ Your chat analytics")
    hist = session.sql(
        f"""select m.chat_id, m.role, m.model, m.content, m.created_at
            from {MESSAGES_TABLE} m join {SESSIONS_TABLE} s on s.chat_id = m.chat_id
            where s.user_name = ?""",
        params=[user],
    ).to_pandas()
    if hist.empty:
        st.info("Start chatting to see analytics here.")
    else:
        k1, k2, k3, k4 = st.columns(4)
        kpi(k1, hist["CHAT_ID"].nunique(), "Chats", "k1")
        kpi(k2, (hist["ROLE"] == "user").sum(), "Questions asked", "k2")
        kpi(k3, hist["MODEL"].nunique(), "Models used", "k3")
        kpi(k4, int(hist[hist["ROLE"] == "assistant"]["CONTENT"].str.len().mean()), "Avg answer length", "k4")

        hist["DAY"] = pd.to_datetime(hist["CREATED_AT"]).dt.date
        c1, c2 = st.columns(2)
        c1.markdown("#### Messages per day")
        c1.bar_chart(hist.groupby("DAY").size().rename("messages"), color="#2563EB")
        c2.markdown("#### Model usage")
        c2.bar_chart(hist[hist["ROLE"] == "assistant"]["MODEL"].value_counts(), color="#DB2777")

        st.markdown("#### Recent questions")
        st.dataframe(
            hist[hist["ROLE"] == "user"].sort_values("CREATED_AT", ascending=False)[["CREATED_AT", "CONTENT"]].head(20),
            hide_index=True, use_container_width=True,
        )
