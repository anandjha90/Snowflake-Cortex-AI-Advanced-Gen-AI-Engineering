-- ====================================================================
-- Script: 02_ingest_and_embed_policies.sql
-- Description: Parses uploaded documents & creates vector embeddings
-- ====================================================================

USE DATABASE E_GROCERY_DB;
USE SCHEMA SUPPORT_SCHEMA;
USE WAREHOUSE E_GROCERY_WH;

-- 1. Chunk and Embed uploaded policies from stage @ONLINE_POLICY_STAGE
INSERT INTO POLICY_DOCUMENT_CHUNKS (DOC_NAME, CHUNK_TEXT, CHUNK_EMBEDDING)
WITH PARSED_POLICIES AS (
    SELECT 
        RELATIVE_PATH AS DOC_NAME,
        SNOWFLAKE.CORTEX.PARSE_DOCUMENT(@ONLINE_POLICY_STAGE, RELATIVE_PATH, {'mode': 'LAYOUT'}) AS RAW_CONTENT
    FROM DIRECTORY(@ONLINE_POLICY_STAGE)
),
SPLIT_POLICIES AS (
    SELECT 
        DOC_NAME,
        CHUNK.VALUE::STRING AS CHUNK_TEXT
    FROM PARSED_POLICIES,
    LATERAL FLATTEN(
        INPUT => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(
            RAW_CONTENT:content::STRING, 
            'markdown', 
            800, 
            100
        )
    ) CHUNK
)
SELECT 
    DOC_NAME,
    CHUNK_TEXT,
    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', CHUNK_TEXT) AS CHUNK_EMBEDDING
FROM SPLIT_POLICIES;

-- 2. Fallback Direct Ingestion (Ensures vector data exists even without stage file sync)
INSERT INTO POLICY_DOCUMENT_CHUNKS (DOC_NAME, CHUNK_TEXT, CHUNK_EMBEDDING)
SELECT 
    'E_GROCERY_ONLINE_SHOPPING_POLICIES.md',
    'Freshness & Quality Guarantee: We guarantee 100% freshness on all perishable products including organic dairy, fresh produce, meat, and baked goods. If any item delivered is expired, bruised, rotten, or spoiled, customers are eligible for an instant store credit or full refund if reported within 48 hours of delivery.',
    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', 'Freshness & Quality Guarantee: We guarantee 100% freshness on all perishable products including organic dairy, fresh produce, meat, and baked goods. If any item delivered is expired, bruised, rotten, or spoiled, customers are eligible for an instant store credit or full refund if reported within 48 hours of delivery.');

INSERT INTO POLICY_DOCUMENT_CHUNKS (DOC_NAME, CHUNK_TEXT, CHUNK_EMBEDDING)
SELECT 
    'E_GROCERY_ONLINE_SHOPPING_POLICIES.md',
    'Order Cancellations & Modifications: Orders can be modified or canceled free of charge up to 2 hours before the scheduled delivery window. Once an order enters the "Out for Delivery" or "Packing" state, cancellations incur a $5.00 restocking fee.',
    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', 'Order Cancellations & Modifications: Orders can be modified or canceled free of charge up to 2 hours before the scheduled delivery window. Once an order enters the "Out for Delivery" or "Packing" state, cancellations incur a $5.00 restocking fee.');
