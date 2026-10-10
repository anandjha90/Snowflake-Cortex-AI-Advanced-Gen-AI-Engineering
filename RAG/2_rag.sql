USE DATABASE RAG_DB;
USE SCHEMA PUBLIC;

-- This table will track all propmts and responses used in the streamlit app
create or replace TABLE RAG_INPUTS (
	RESPONSE VARCHAR(16777216),
	PROMPT VARCHAR(16777216)
);

-- View the raw text
select * from raw_text;

-- View the chunked text
select * from chunk_text limit 10;

-- Add Vector datatype to the chunk_text table
ALTER TABLE chunk_text ADD COLUMN vec VECTOR(FLOAT, 768);
-- Create the embeddings
UPDATE chunk_text SET vec = SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', chunk);

-- View the chunked text with embeddings
select * from chunk_text limit 10;

-- Show mistral-7b without RAG
select snowflake.cortex.complete('mistral-7b','What percent of snowflake customers process unstructured data?') as mistral_response;

-- Result with Rag
with results as
(SELECT RELATIVE_PATH,
   VECTOR_COSINE_SIMILARITY(chunk_text.vec,
     SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', 'What % of snowflake customers process unstructured data?')
   ) as distance,
   chunk
from chunk_text
order by distance desc
limit 2)
SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large',
    CONCAT('Answer this question: ', 'What % of snowflake customers process unstructured data?',  'using this text: ', array_agg(chunk)::varchar)) as result from results;
