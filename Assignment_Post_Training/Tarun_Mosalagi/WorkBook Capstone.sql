CREATE OR REPLACE WAREHOUSE DEMO_WAREHOUSE
  WAREHOUSE_SIZE = 'MEDIUM'
  MIN_CLUSTER_COUNT = 1
  MAX_CLUSTER_COUNT = 5
  AUTO_SUSPEND = 300
  AUTO_RESUME = TRUE
  ENABLE_QUERY_ACCELERATION = TRUE;

USE WAREHOUSE DEMO_WAREHOUSE;
CREATE DATABASE CC_QUICKSTART_CORTEX_SEARCH_DOCS;
CREATE SCHEMA DATA;

create or replace stage docs ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') DIRECTORY = ( ENABLE = true );

ls @docs;

CREATE OR REPLACE TEMPORARY TABLE RAW_TEXT AS
WITH FILE_TABLE as (
  (SELECT 
        RELATIVE_PATH,
        SIZE,
        FILE_URL,
        build_scoped_file_url(@docs, relative_path) as scoped_file_url,
        TO_FILE('@DOCS', RELATIVE_PATH) AS docs 
    FROM 
        DIRECTORY(@DOCS))
)
SELECT 
    RELATIVE_PATH,
    SIZE,
    FILE_URL,
    scoped_file_url,
    TO_VARCHAR (
        SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT (
            docs,
            {'mode': 'LAYOUT'} ):content
        ) AS EXTRACTED_LAYOUT 
FROM 
    FILE_TABLE;

create or replace TABLE DOCS_CHUNKS_TABLE ( 
    RELATIVE_PATH VARCHAR(16777216), -- Relative path to the PDF file
    SIZE NUMBER(38,0), -- Size of the PDF
    FILE_URL VARCHAR(16777216), -- URL for the PDF
    SCOPED_FILE_URL VARCHAR(16777216), -- Scoped url (you can choose which one to keep depending on your use case)
    CHUNK VARCHAR(16777216), -- Piece of text
    CHUNK_INDEX INTEGER, -- Index for the text
    CATEGORY VARCHAR(16777216) -- Will hold the document category to enable filtering
);

insert into docs_chunks_table (relative_path, size, file_url,
                            scoped_file_url, chunk, chunk_index)

    select relative_path, 
            size,
            file_url, 
            scoped_file_url,
            c.value::TEXT as chunk,
            c.INDEX::INTEGER as chunk_index
            
    from 
        raw_text,
        LATERAL FLATTEN( input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER (
              EXTRACTED_LAYOUT,
              'markdown',
              1512,
              256,
              ['\n\n', '\n', ' ', '']
           )) c;


CREATE OR REPLACE TEMPORARY TABLE docs_categories AS WITH unique_documents AS (
  SELECT
    DISTINCT relative_path, chunk
  FROM
    docs_chunks_table
  WHERE 
    chunk_index = 0
  ),
 docs_category_cte AS (
  SELECT
    relative_path,
    TRIM(snowflake.cortex.AI_CLASSIFY (
      'Title:' || relative_path || 'Content:' || chunk, ['Bike', 'Snow']
     )['labels'][0], '"') AS CATEGORY
  FROM
    unique_documents
)
SELECT
  *
FROM
  docs_category_cte;

  select * from docs_categories;

update docs_chunks_table 
  SET category = docs_categories.category
  from docs_categories
  where  docs_chunks_table.relative_path = docs_categories.relative_path;

create or replace CORTEX SEARCH SERVICE CC_SEARCH_SERVICE_CS
ON chunk
ATTRIBUTES category
warehouse = COMPUTE_WH
TARGET_LAG = '1 minute'
as (
    select chunk,
        chunk_index,
        relative_path,
        file_url,
        category
    from docs_chunks_table
);


create or replace stream insert_docs_stream on stage docs;
create or replace stream delete_docs_stream on stage docs;


create or replace procedure insert_delete_docs_sp()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN

DELETE FROM docs_chunks_table
    USING delete_docs_stream
    WHERE docs_chunks_table.RELATIVE_PATH = delete_docs_stream.RELATIVE_PATH
    and delete_docs_stream.METADATA$ACTION = 'DELETE';

CREATE OR REPLACE TEMPORARY TABLE RAW_TEXT AS
    WITH FILE_TABLE as 
      (SELECT 
            RELATIVE_PATH,
            SIZE,
            FILE_URL,
            build_scoped_file_url(@docs, relative_path) as scoped_file_url,
            TO_FILE('@DOCS', RELATIVE_PATH) AS docs 
        FROM 
            insert_docs_stream
        WHERE 
            METADATA$ACTION = 'INSERT'        
        )
    SELECT 
        RELATIVE_PATH,
        SIZE,
        FILE_URL,
        scoped_file_url,
        TO_VARCHAR (
            SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT (
                docs,
                {'mode': 'LAYOUT'} ):content
            ) AS EXTRACTED_LAYOUT 
    FROM 
        FILE_TABLE;
    

    -- Insert new docs chunks
insert into docs_chunks_table (relative_path, size, file_url,
                            scoped_file_url, chunk, chunk_index)

select relative_path, 
            size,
            file_url, 
            scoped_file_url,
            c.value::TEXT as chunk,
            c.INDEX::INTEGER as chunk_index
            
    from 
        RAW_TEXT,
        LATERAL FLATTEN( input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER (
              EXTRACTED_LAYOUT,
              'markdown',
              1512,
              256,
              ['\n\n', '\n', ' ', '']
           )) c;

    -- Classify the new documents

    CREATE OR REPLACE TEMPORARY TABLE docs_categories AS 
    WITH unique_documents AS (
      SELECT DISTINCT
        d.relative_path, d.chunk
      FROM
        docs_chunks_table d
      INNER JOIN
        RAW_TEXT r
        ON d.relative_path = r.relative_path
      WHERE 
        d.chunk_index = 0
    ),
    docs_category_cte AS (
      SELECT
        relative_path,
        TRIM(snowflake.cortex.AI_CLASSIFY (
            'Title:' || relative_path || 'Content:' || chunk, ['Bike', 'Snow']
            )['labels'][0], '"') AS CATEGORY
      FROM
        unique_documents
    )
    SELECT
      *
    FROM
      docs_category_cte;

    -- Update cathegories

    update docs_chunks_table 
        SET category = docs_categories.category
        from docs_categories
        where  docs_chunks_table.relative_path = docs_categories.relative_path;
END;
$$;

create or replace task insert_delete_docs_task
    warehouse = COMPUTE_WH
    schedule = '5 minute'
    when system$stream_has_data('delete_docs_stream')
as
    call insert_delete_docs_sp();


alter task  insert_delete_docs_task resume;

select * from delete_docs_stream;
select * from insert_docs_stream;

execute task insert_delete_docs_task;

alter task insert_delete_docs_task suspend;