import streamlit as st  # Import python packages
from snowflake.snowpark.context import get_active_session

import pandas as pd
import json

pd.set_option("max_colwidth", None)

### Default Values
NUM_CHUNKS = 3  # Num-chunks provided as context. Play with this to check how it affects your accuracy
slide_window = 7  # how many last conversations to remember. This is the slide window.

# service parameters
CORTEX_SEARCH_DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
CORTEX_SEARCH_SCHEMA = "DATA"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"
SERVICE_FQN = f"{CORTEX_SEARCH_DATABASE}.{CORTEX_SEARCH_SCHEMA}.{CORTEX_SEARCH_SERVICE}"
######

# columns to query in the service
COLUMNS = [
    "chunk",
    "chunk_index",
    "relative_path",
    "category"
]

session = get_active_session()


### Cortex helpers (SQL-based, no REST endpoints)

def cortex_complete(model, prompt):
    """Call the LLM through the SQL function instead of the REST API."""
    return session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)",
        params=[model, prompt]
    ).collect()[0][0]


def cortex_search(query, category=None):
    """Query the Cortex Search service through SQL instead of the REST API."""
    search_query = {
        "query": query,
        "columns": COLUMNS,
        "limit": NUM_CHUNKS
    }
    if category and category != "ALL":
        search_query["filter"] = {"@eq": {"category": category}}

    return session.sql(
        "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?)",
        params=[SERVICE_FQN, json.dumps(search_query)]
    ).collect()[0][0]  # JSON string with a "results" key


### Functions

def config_options():

    st.sidebar.selectbox('Select your model:', ('mistral-large2', 'llama3.1-70b',
                                                'llama3.1-8b', 'snowflake-arctic'), key="model_name")

    categories = session.table('docs_chunks_table').select('category').distinct().collect()

    cat_list = ['ALL']
    for cat in categories:
        cat_list.append(cat.CATEGORY)

    st.sidebar.selectbox('Select what products you are looking for', cat_list, key="category_value")

    st.sidebar.checkbox('Do you want that I remember the chat history?', key="use_chat_history", value=True)

    st.sidebar.checkbox('Debug: Click to see summary generated of previous conversation', key="debug", value=True)
    st.sidebar.button("Start Over", key="clear_conversation", on_click=init_messages)
    st.sidebar.expander("Session State").write(st.session_state)


def init_messages():

    # Initialize chat history
    if st.session_state.get("clear_conversation") or "messages" not in st.session_state:
        st.session_state.messages = []


def get_similar_chunks_search_service(query):

    response = cortex_search(query, st.session_state.category_value)

    st.sidebar.json(response)

    return response


def get_chat_history():
    # Get the history from the st.session_state.messages according to the slide window parameter

    chat_history = []

    start_index = max(0, len(st.session_state.messages) - slide_window)
    for i in range(start_index, len(st.session_state.messages) - 1):
        chat_history.append(st.session_state.messages[i])

    return chat_history


def summarize_question_with_history(chat_history, question):
    # To get the right context, use the LLM to first summarize the previous conversation
    # This will be used to get embeddings and find similar chunks in the docs for context

    prompt = f"""
        Based on the chat history below and the question, generate a query that extend the question
        with the chat history provided. The query should be in natural language.
        Answer with only the query. Do not add any explanation.

        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        """

    summary = cortex_complete(st.session_state.model_name, prompt)

    if st.session_state.debug:
        st.sidebar.text("Summary to be used to find similar chunks in the docs:")
        st.sidebar.caption(summary)

    summary = summary.replace("'", "")

    return summary


def create_prompt(myquestion):

    if st.session_state.use_chat_history:
        chat_history = get_chat_history()

        if chat_history != []:  # There is chat_history, so not first question
            question_summary = summarize_question_with_history(chat_history, myquestion)
            prompt_context = get_similar_chunks_search_service(question_summary)
        else:
            prompt_context = get_similar_chunks_search_service(myquestion)  # First question when using history
    else:
        prompt_context = get_similar_chunks_search_service(myquestion)
        chat_history = ""

    prompt = f"""
           You are an expert chat assistance that extracts information from the CONTEXT provided
           between <context> and </context> tags.
           You offer a chat experience considering the information included in the CHAT HISTORY
           provided between <chat_history> and </chat_history> tags.
           When answering the question contained between <question> and </question> tags
           be concise and do not hallucinate.
           If you don't have the information just say so.

           Do not mention the CONTEXT used in your answer.
           Do not mention the CHAT HISTORY used in your answer.

           Only answer the question if you can extract it from the CONTEXT provided.

           <chat_history>
           {chat_history}
           </chat_history>
           <context>
           {prompt_context}
           </context>
           <question>
           {myquestion}
           </question>
           Answer:
           """

    json_data = json.loads(prompt_context)

    relative_paths = set(item['relative_path'] for item in json_data.get('results', []))

    return prompt, relative_paths


def answer_question(myquestion):

    prompt, relative_paths = create_prompt(myquestion)

    response = cortex_complete(st.session_state.model_name, prompt)

    return response, relative_paths


def main():

    st.title(f":speech_balloon: Chat Document Assistant with Snowflake Cortex")
    st.write("This is the list of documents you already have and that will be used to answer your questions:")
    docs_available = session.sql("ls @docs").collect()
    list_docs = []
    for doc in docs_available:
        list_docs.append(doc["name"])
    st.dataframe(list_docs)

    config_options()
    init_messages()

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if question := st.chat_input("What do you want to know about your products?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": question})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(question)
        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            message_placeholder = st.empty()

            question = question.replace("'", "")

            with st.spinner(f"{st.session_state.model_name} thinking..."):
                try:
                    response, relative_paths = answer_question(question)
                    response = response.replace("'", "")
                except Exception as e:
                    response = f"Sorry, something went wrong: {e}"
                    relative_paths = set()
                message_placeholder.markdown(response)

                if relative_paths:
                    with st.sidebar.expander("Related Documents"):
                        for path in relative_paths:
                            # GET_PRESIGNED_URL needs the path as a literal at compile
                            # time, so bind parameters (?) don't work here.
                            safe_path = path.replace("'", "''")
                            df_url_link = session.sql(
                                f"SELECT GET_PRESIGNED_URL(@docs, '{safe_path}', 360) AS URL_LINK"
                            ).to_pandas()
                            url_link = df_url_link._get_value(0, 'URL_LINK')

                            display_url = f"Doc: [{path}]({url_link})"
                            st.sidebar.markdown(display_url)

        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
