import os
import time
import streamlit as st
from snowflake.core import Root

import pandas as pd
import json

pd.set_option("max_colwidth", None)

st.set_page_config(page_title="Document Assistant", layout="wide")

### Default Values
NUM_CHUNKS = 3
MAX_HISTORY_TURNS = 10

# service parameters
CORTEX_SEARCH_DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
CORTEX_SEARCH_SCHEMA = "DATA"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"

COLUMNS = [
    "chunk",
    "chunk_index",
    "relative_path",
    "category"
]

SAMPLE_QUESTIONS = [
    "Is there any special lubricant to be used with the premium bike?",
    "What are the maintenance intervals for the mountain bike?",
    "How do I adjust the brake system?",
    "What warranty coverage is provided?",
]

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
session = conn.session()
root = Root(session)

svc = root.databases[CORTEX_SEARCH_DATABASE].schemas[CORTEX_SEARCH_SCHEMA].cortex_search_services[CORTEX_SEARCH_SERVICE]


def config_options():
    st.sidebar.selectbox(
        "Select your model:",
        ("llama3.1-70b", "llama3.1-8b", "snowflake-arctic"),
        key="model_name",
    )

    categories = session.sql(
        "select category from CC_QUICKSTART_CORTEX_SEARCH_DOCS.DATA.docs_chunks_table group by category"
    ).collect()

    cat_list = ["ALL"]
    for cat in categories:
        cat_list.append(cat.CATEGORY)

    st.sidebar.selectbox(
        "Select what products you are looking for", cat_list, key="category_value"
    )

    st.sidebar.slider(
        "Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1, key="temperature"
    )
    st.sidebar.slider(
        "Max Tokens", min_value=100, max_value=4096, value=1024, step=100, key="max_tokens"
    )

    st.sidebar.expander("Session State").write(st.session_state)


def get_similar_chunks_search_service(query):
    if st.session_state.category_value == "ALL":
        response = svc.search(query, COLUMNS, limit=NUM_CHUNKS)
    else:
        filter_obj = {"@eq": {"category": st.session_state.category_value}}
        response = svc.search(query, COLUMNS, filter=filter_obj, limit=NUM_CHUNKS)

    st.sidebar.json(response.json())
    return response.json()


def build_system_message(context=None):
    base = (
        "You are an expert chat assistant that extracts information from the CONTEXT provided. "
        "Be concise and do not hallucinate. If you don't have the information just say so. "
        "Only answer the question if you can extract it from the CONTEXT provided. "
        "Do not mention the CONTEXT used in your answer."
    )
    if context:
        return f"{base}\n\nCONTEXT:\n{context}"
    return base


def get_history_messages():
    messages = st.session_state.get("messages", [])
    recent = messages[-(MAX_HISTORY_TURNS * 2):]
    return [
        {"role": m["role"], "content": m["content"]}
        for m in recent
    ]


def get_context_and_paths(myquestion):
    if st.session_state.rag == 1:
        prompt_context = get_similar_chunks_search_service(myquestion)
        json_data = json.loads(prompt_context)
        relative_paths = set(item["relative_path"] for item in json_data["results"])
        return prompt_context, relative_paths
    return None, None


def build_conversation(myquestion, context=None):
    system_msg = build_system_message(context)
    history = get_history_messages()
    conversation = [{"role": "system", "content": system_msg}]
    conversation.extend(history)
    conversation.append({"role": "user", "content": myquestion})
    return conversation


def complete_and_stream(conversation):
    conversation_json = json.dumps(conversation)
    options = json.dumps({
        "temperature": st.session_state.temperature,
        "max_tokens": st.session_state.max_tokens,
    })
    cmd = "select snowflake.cortex.complete(?, parse_json(?), parse_json(?)) as response"
    df_response = session.sql(
        cmd, params=[st.session_state.model_name, conversation_json, options]
    ).collect()

    res_text = df_response[0].RESPONSE
    result = json.loads(res_text)
    answer = result["choices"][0]["messages"]

    for word in answer.split(" "):
        yield word + " "
        time.sleep(0.03)


def render_related_docs(relative_paths):
    with st.expander("Related Documents"):
        for path in relative_paths:
            cmd2 = f"select GET_PRESIGNED_URL(@CC_QUICKSTART_CORTEX_SEARCH_DOCS.DATA.docs, '{path}', 360) as URL_LINK from directory(@CC_QUICKSTART_CORTEX_SEARCH_DOCS.DATA.docs)"
            df_url_link = session.sql(cmd2).to_pandas()
            url_link = df_url_link._get_value(0, "URL_LINK")
            st.markdown(f"[{path}]({url_link})")


def main():
    config_options()
    st.session_state.rag = st.sidebar.checkbox("Use your own documents as context?")

    if st.sidebar.button("Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    # --- Header ---
    st.title(":speech_balloon: Chat Document Assistant")
    st.caption("Powered by Snowflake Cortex Search")

    # --- Document list in expander ---
    with st.expander("Available Documents", expanded=False):
        docs_available = session.sql(
            "ls @CC_QUICKSTART_CORTEX_SEARCH_DOCS.DATA.docs"
        ).collect()
        list_docs = [doc["name"] for doc in docs_available]
        st.dataframe(list_docs, use_container_width=True)

    # --- Initialize chat history ---
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- Show sample questions only when chat is empty ---
    if not st.session_state.messages:
        st.divider()
        st.subheader("Sample Questions")
        cols = st.columns(2)
        for i, q in enumerate(SAMPLE_QUESTIONS):
            if cols[i % 2].button(q, key=f"sample_{i}", use_container_width=True):
                st.session_state["asked_question"] = q
                st.rerun()
        st.divider()

    # --- Render chat history ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("relative_paths"):
                render_related_docs(msg["relative_paths"])

    # --- Handle pending sample question or new chat input ---
    question = st.session_state.pop("asked_question", None)
    if question is None:
        question = st.chat_input("Type your question here...")

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        context, relative_paths = get_context_and_paths(question)
        conversation = build_conversation(question, context)

        with st.chat_message("assistant"):
            answer = st.write_stream(complete_and_stream(conversation))

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "relative_paths": relative_paths,
        })

        if relative_paths:
            render_related_docs(relative_paths)


if __name__ == "__main__":
    main()
