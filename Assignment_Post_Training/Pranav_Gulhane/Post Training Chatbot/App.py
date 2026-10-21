import streamlit as st
from snowflake.snowpark.context import get_active_session

# Set page configuration
st.set_page_config(page_title="Snowflake File Chatbot", page_icon="🤖", layout="wide")

# Get active Snowpark session
session = get_active_session()

st.title("💬 Snowflake File Chatbot (Powered by Cortex)")
st.write("Ask questions about the files and documents stored securely in your Snowflake tables.")

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ App Settings")
    selected_model = st.selectbox(
        "Choose LLM Model",
        ["claude-3-5-sonnet", "mistral-large2", "llama3-70b-instruct"],
        index=0
    )
    
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.info("This app uses Snowflake Cortex `COMPLETE` to answer queries based on your internal data table.")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input from chat bar
if prompt := st.chat_input("Ask a question about your files..."):
    # Add user message to state and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate assistant response using Snowflake Cortex
    with st.chat_message("assistant"):
        with st.spinner("Searching documents and generating response..."):
            try:
                # Escape single quotes in user prompt to prevent SQL injection/syntax errors
                escaped_prompt = prompt.replace("'", "''")
                
                # Construct query retrieving context from your table and passing it to Cortex LLM
                # (You can replace 'DOCUMENTS_TABLE' and 'file_content' with your actual table/columns)
                cortex_query = f"""
                    SELECT SNOWFLAKE.CORTEX.COMPLETE(
                        '{selected_model}',
                        CONCAT(
                            'You are a helpful corporate AI assistant. Answer the user question accurately based ONLY on the provided context. If the answer cannot be found in the context, say "I cannot find the answer in the provided documents."\\n\\nContext:\\n',
                            (SELECT COALESCE(LISTAGG(file_content, '\\n---\\n'), 'No documents available') FROM DOCUMENTS_TABLE),
                            '\\n\\nQuestion: ',
                            '{escaped_prompt}'
                        )
                    ) AS answer
                """
                
                # Execute query via Snowpark
                df = session.sql(cortex_query).collect()
                response_text = df[0]['ANSWER'] if df and 'ANSWER' in df[0] else "No response generated."
                
                st.markdown(response_text)
                
                # Append assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
            except Exception as e:
                error_message = f"An error occurred while querying Snowflake Cortex: `{e}`"
                st.error(error_message)
