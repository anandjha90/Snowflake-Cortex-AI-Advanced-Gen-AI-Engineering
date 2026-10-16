import streamlit as st
from snowflake.snowpark.context import get_active_session
#from snowflake.cortex import Complete
import _snowflake
import pandas as pd
import json



pd.set_option("max_colwidth", None)

### Default Values
NUM_CHUNKS = 3
slide_window = 7

# service parameters
CORTEX_SEARCH_DATABASE = "CC_QUICKSTART_CORTEX_SEARCH_DOCS"
CORTEX_SEARCH_SCHEMA = "DATA"
CORTEX_SEARCH_SERVICE = "CC_SEARCH_SERVICE_CS"

# columns to query in the service
COLUMNS = [
    "chunk",
    "chunk_index",
    "relative_path",
    "category"
]

session = get_active_session()

### Functions

def cortex_complete(model, prompt):
    cmd = "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS response"
    result = session.sql(cmd, params=[model, prompt]).collect()
    return result[0].RESPONSE

def config_options():

       
    st.sidebar.selectbox('Select your model:', (
        'mistral-large3', 'llama3.1-70b',
        'llama3.1-8b', 'claude-sonnet-4-5', 'gemini-3.5-flash',
        'claude-haiku-4-5', 'openai-gpt-5',
        'qwen3-32b', 'gemma-4-31b'), key="model_name")

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
    if st.session_state.clear_conversation or "messages" not in st.session_state:
        st.session_state.messages = []


def get_similar_chunks_search_service(query):
    request_body = {
        "query": query,
        "columns": COLUMNS,
        "limit": NUM_CHUNKS
    }

    if st.session_state.category_value != "ALL":
        request_body["filter"] = {"@eq": {"category": st.session_state.category_value}}

    resp = _snowflake.send_snow_api_request(
        "POST",
        f"/api/v2/databases/{CORTEX_SEARCH_DATABASE}/schemas/{CORTEX_SEARCH_SCHEMA}/cortex-search-services/{CORTEX_SEARCH_SERVICE}:query",
        {},
        {},
        request_body,
        {},
        30000
    )

    if resp["status"] < 400:
        results = json.loads(resp["content"])
        st.sidebar.json(results)
        return json.dumps(results)
    else:
        raise Exception(f"Cortex Search request failed: {resp['content']}")


def get_chat_history():
    chat_history = []
    start_index = max(0, len(st.session_state.messages) - slide_window)
    for i in range(start_index, len(st.session_state.messages) - 1):
        chat_history.append(st.session_state.messages[i])
    return chat_history


def summarize_question_with_history(chat_history, question):
    prompt = f"""
        Based on the chat history below and the question, generate a query that extend the question
        with the chat history provided. The query should be in natual language. 
        Answer with only the query. Do not add any explanation.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        """

    #sumary = Complete(st.session_state.model_name, prompt)
    sumary = cortex_complete(st.session_state.model_name, prompt)

    if st.session_state.debug:
        st.sidebar.text("Summary to be used to find similar chunks in the docs:")
        st.sidebar.caption(sumary)

    sumary = sumary.replace("'", "")
    return sumary


def create_prompt(myquestion):
    if st.session_state.use_chat_history:
        chat_history = get_chat_history()
        if chat_history != []:
            question_summary = summarize_question_with_history(chat_history, myquestion)
            prompt_context = get_similar_chunks_search_service(question_summary)
        else:
            prompt_context = get_similar_chunks_search_service(myquestion)
    else:
        prompt_context = get_similar_chunks_search_service(myquestion)
        chat_history = ""

    prompt = f"""
           You are an expert chat assistance that extracs information from the CONTEXT provided
           between <context> and </context> tags.
           You offer a chat experience considering the information included in the CHAT HISTORY
           provided between <chat_history> and </chat_history> tags..
           When ansering the question contained between <question> and </question> tags
           be concise and do not hallucinate. 
           If you don´t have the information just say so.
           
           Do not mention the CONTEXT used in your answer.
           Do not mention the CHAT HISTORY used in your asnwer.

           Only anwer the question if you can extract it from the CONTEXT provideed.
           
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
    relative_paths = set(item['relative_path'] for item in json_data['results'])

    return prompt, relative_paths


def answer_question(myquestion):
    prompt, relative_paths = create_prompt(myquestion)
    response = cortex_complete(st.session_state.model_name, prompt)
    return response, relative_paths


def main():

    st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(to right, #ebe9e6, #493240);
    }
    </style>
    """,
    unsafe_allow_html=True
    )

    
    st.title(f":speech_balloon: Chat Document Assistant : Ask Anything")
    st.write("This is the list of documents you already have and that will be used to answer your questions:")
    docs_available = session.sql("ls @docs").collect()
    
    list_docs = []
    for doc in docs_available:
        dc_name=doc["name"]
        list_docs.append(dc_name[5:])
    st.dataframe(list_docs)

    config_options()
    init_messages()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if question := st.chat_input("What do you want to know about your products?"):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            question = question.replace("'", "")
            with st.spinner(f"{st.session_state.model_name} thinking..."):
                response, relative_paths = answer_question(question)
                response = response.replace("'", "")
                message_placeholder.markdown(response)

                if relative_paths != "None":
                    with st.sidebar.expander("Related Documents"):
                        for path in relative_paths:
                            cmd2 = f"select GET_PRESIGNED_URL(@docs, '{path}', 360) as URL_LINK from directory(@docs)"
                            df_url_link = session.sql(cmd2).to_pandas()
                            url_link = df_url_link._get_value(0, 'URL_LINK')
                            display_url = f"Doc: [{path}]({url_link})"
                            st.sidebar.markdown(display_url)

        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()