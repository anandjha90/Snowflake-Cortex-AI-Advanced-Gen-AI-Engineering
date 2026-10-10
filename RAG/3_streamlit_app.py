from snowflake.snowpark.context import get_active_session
from textwrap import dedent

session = get_active_session()
session.sql("USE DATABASE RAG_DB").collect()
session.sql("USE SCHEMA PUBLIC").collect()

VECTOR_TABLE = 'RAG_DB.PUBLIC.CHUNK_TEXT'

class ComposedPrompt:
    def __init__(self, prompt: str, document: str, model: str):
        self.prompt = prompt
        self.document = document
        self.model = model
        self.system_message = 'Answer the question based on the context. Be concise.'
        self.context = f'''select array_agg(*)::varchar from (
                        (select chunk from {VECTOR_TABLE} 
                        where RELATIVE_PATH = '{self.document}'
                        order by vector_l2_distance(
                        snowflake.cortex.embed_text_768('e5-base-v2', 
                        '{self.prompt}'
                        ), snowflake.cortex.embed_text_768('e5-base-v2', chunk)
                        ) limit 5))
                            '''

    def __str__(self) -> str:
        return dedent(f'''
        select snowflake.cortex.complete(
            '{self.model}',
            concat( '{self.system_message}','Context: ',
                    ({self.context}),
                    'Question: ', 
                    '{self.prompt}',
                    'Answer: ')
                ) as RESPONSE
                ''')

def get_documents():
    return session.table(VECTOR_TABLE).select('RELATIVE_PATH').distinct().collect()

# Configuration
model = 'llama3.1-70b'
prompt = 'What % of snowflake customers process unstructured data?'

print("RAG Chat Demo")
print(f"Model: {model}")
print(f"Prompt: {prompt}\n")

docs = get_documents()
print(f"Available documents: {[row[0] for row in docs]}\n")

doc = docs[0][0] if docs else None

if doc and prompt:
    comp_prompt = ComposedPrompt(prompt=prompt, model=model, document=doc).__str__()
    response = session.sql(comp_prompt).select("RESPONSE").to_pandas()["RESPONSE"][0]
    print(f"--- Response (with RAG) ---\n{response}")
else:
    print("No documents available in chunk_text. Upload PDFs to the @RAG stage first.")
