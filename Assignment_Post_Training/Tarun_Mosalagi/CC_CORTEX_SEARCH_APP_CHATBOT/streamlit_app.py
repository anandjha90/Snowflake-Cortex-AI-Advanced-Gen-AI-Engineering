import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import json

# Must be the first Streamlit command
st.set_page_config(
    page_title="Cortex Document Assistant",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    escaped_prompt = prompt.replace("'", "\\'")
    cmd = "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS response"
    result = session.sql(cmd, params=[model, prompt]).collect()
    return result[0].RESPONSE

def config_options():
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        st.selectbox(
            'Select your model:', 
            ('claude-sonnet-4-5', 'llama3.1-70b', 'llama3.1-8b'), 
            key="model_name"
        )

        categories = session.table('docs_chunks_table').select('category').distinct().collect()
        cat_list = ['ALL'] + [cat.CATEGORY for cat in categories]

        st.selectbox(
            'Product Category Filter', 
            cat_list, 
            key="category_value"
        )

        st.divider()
        st.header("🛠️ Advanced Settings")
        
        st.toggle('Remember chat history', key="use_chat_history", value=True)
        st.toggle('Debug mode (show summaries & JSON)', key="debug", value=False)
        
        st.button("🗑️ Start Over", key="clear_conversation", on_click=init_messages, use_container_width=True)
        
        with st.expander("System State"):
            st.write(st.session_state)

def init_messages():
    if st.session_state.get("clear_conversation") or "messages" not in st.session_state:
        st.session_state.messages = []

def get_similar_chunks_search_service(query):
    if st.session_state.category_value == "ALL":
        search_params = {
            "query": query,
            "columns": COLUMNS,
            "limit": NUM_CHUNKS
        }
    else:
        search_params = {
            "query": query,
            "columns": COLUMNS,
            "filter": {"@eq": {"category": st.session_state.category_value}},
            "limit": NUM_CHUNKS
        }

    fqn = f"{CORTEX_SEARCH_DATABASE}.{CORTEX_SEARCH_SCHEMA}.{CORTEX_SEARCH_SERVICE}"
    sql = f"SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('{fqn}', $${json.dumps(search_params)}$$) AS results"
    result = session.sql(sql).collect()
    response = result[0]['RESULTS']
    
    return response

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
    sumary = cortex_complete(st.session_state.model_name, prompt)
    sumary = sumary.replace("'", "")
    return sumary

def create_prompt(myquestion):
    summary = None
    if st.session_state.use_chat_history:
        chat_history = get_chat_history()
        if chat_history != []:
            summary = summarize_question_with_history(chat_history, myquestion)
            prompt_context = get_similar_chunks_search_service(summary)
        else:
            prompt_context = get_similar_chunks_search_service(myquestion)
    else:
        prompt_context = get_similar_chunks_search_service(myquestion)
        chat_history = ""

    prompt = f"""
           You are an expert chat assistance that extracs information from the CONTEXT provided
           between <context> and </context> tags.
           You offer a chat experience considering the information included in the CHAT HISTORY
           provided between <chat_history> and </chat_history> tags.
           When ansering the question contained between <question> and </question> tags
           be concise and do not hallucinate.
           If you don't have the information just say so.

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

    return prompt, relative_paths, summary, json_data

def answer_question(myquestion):
    prompt, relative_paths, summary, json_data = create_prompt(myquestion)
    response = cortex_complete(st.session_state.model_name, prompt)
    return response, relative_paths, summary, json_data

def main():
    # Header Section
    st.title("💬 Cortex Document Assistant")
    st.caption("Ask questions about your products and get answers powered by Snowflake Cortex.")
    
    # Hide the large dataframe behind an expander to keep the UI clean
    docs_available = session.sql("ls @docs").collect()
    list_docs = [doc["name"] for doc in docs_available]
    with st.expander("📚 View Available Documents", expanded=False):
        st.dataframe(list_docs, use_container_width=True)

    config_options()
    init_messages()

    # Display Chat History
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Re-render citations and debug info for past messages
            if "citations" in message and message["citations"]:
                with st.expander("📄 Related Documents"):
                    for url_link, path in message["citations"]:
                        st.markdown(f"- [{path}]({url_link})")
                        
            if st.session_state.debug and "debug_info" in message:
                with st.expander("🐛 Debug Information"):
                    if message["debug_info"].get("summary"):
                        st.markdown("**Generated Search Summary:**")
                        st.info(message["debug_info"]["summary"])
                    st.markdown("**Search Results JSON:**")
                    st.json(message["debug_info"]["json_data"])

    # Handle New Chat Input
    if question := st.chat_input("What do you want to know about your products?"):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
            
        with st.chat_message("assistant"):
            question_clean = question.replace("'", "")
            
            with st.spinner(f"✨ {st.session_state.model_name} is thinking..."):
                response, relative_paths, summary, json_data = answer_question(question_clean)
                response_clean = response.replace("'", "")
                
                # Render the main response
                st.markdown(response_clean)

                # Process and render citations directly under the chat message
                citations = []
                if relative_paths and relative_paths != "None":
                    with st.expander("📄 Related Documents"):
                        for path in relative_paths:
                            cmd2 = f"select GET_PRESIGNED_URL(@docs, '{path}', 360) as URL_LINK from directory(@docs)"
                            df_url_link = session.sql(cmd2).to_pandas()
                            url_link = df_url_link._get_value(0, 'URL_LINK')
                            st.markdown(f"- [{path}]({url_link})")
                            citations.append((url_link, path))

                # Render debug information if enabled
                if st.session_state.debug:
                    with st.expander("🐛 Debug Information"):
                        if summary:
                            st.markdown("**Generated Search Summary:**")
                            st.info(summary)
                        st.markdown("**Search Results JSON:**")
                        st.json(json_data)

            # Append the full context to the session state so it persists on reload
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response_clean,
                "citations": citations,
                "debug_info": {"summary": summary, "json_data": json_data}
            })

if __name__ == "__main__":
    main()