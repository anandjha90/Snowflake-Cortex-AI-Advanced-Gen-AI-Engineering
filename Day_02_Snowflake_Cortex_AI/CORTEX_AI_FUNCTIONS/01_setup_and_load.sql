-- =====================================================================
-- 01_setup_and_load.sql
-- Snowflake Cortex AI Functions demo - environment, tables and data
-- Run this file first. Everything after it depends on these objects.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Privileges you need before anything else
--    Run the GRANTs as ACCOUNTADMIN once, then switch back to your role.
-- ---------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER       TO ROLE ACCOUNTADMIN;  -- most AI functions
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_EMBED_USER TO ROLE ACCOUNTADMIN;  -- AI_EMBED / AI_SIMILARITY
GRANT USE AI FUNCTIONS ON ACCOUNT               TO ROLE ACCOUNTADMIN;  -- account level gate
-- Cross-region routing (only if the model is not hosted in your region):
-- ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

--USE ROLE SYSADMIN;

-- CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
--   WAREHOUSE_SIZE = 'XSMALL'
--   AUTO_SUSPEND   = 60
--   AUTO_RESUME    = TRUE
--   INITIALLY_SUSPENDED = TRUE;

CREATE DATABASE IF NOT EXISTS CORTEX_DB;
CREATE SCHEMA   IF NOT EXISTS CORTEX_SC;

USE WAREHOUSE COMPUTE_WH;
USE DATABASE  CORTEX_DB;
USE SCHEMA    CORTEX_SC;

-- ---------------------------------------------------------------------
-- 1. Tables
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE customer_reviews (
  review_id      NUMBER,
  product_id     VARCHAR,
  reviewer_name  VARCHAR,
  review_date    DATE,
  rating         NUMBER,
  language       VARCHAR,
  review_text    VARCHAR
);

CREATE OR REPLACE TABLE support_tickets (
  ticket_id      NUMBER,
  customer_id    VARCHAR,
  created_date   DATE,
  category       VARCHAR,
  priority       VARCHAR,
  ticket_text    VARCHAR
);

CREATE OR REPLACE TABLE product_catalog (
  product_id     VARCHAR,
  product_name   VARCHAR,
  category       VARCHAR,
  list_price     NUMBER(10,2),
  description    VARCHAR
);

CREATE OR REPLACE TABLE customer_notes_pii (
  note_id        NUMBER,
  note_date      DATE,
  note_text      VARCHAR
);

CREATE OR REPLACE TABLE call_transcripts (
  call_id          NUMBER,
  customer_id      VARCHAR,
  duration_seconds NUMBER,
  transcript_text  VARCHAR
);

CREATE OR REPLACE TABLE contracts (
  contract_id    NUMBER,
  counterparty   VARCHAR,
  contract_type  VARCHAR,
  signed_date    DATE,
  clause_text    VARCHAR
);

-- ---------------------------------------------------------------------
-- 2a. LOAD OPTION A - load the supplied CSV files from a stage
--     Use this if you want the CSVs in the data/ folder to be the source.
--     PUT only works from SnowSQL, the Snowflake CLI or a driver, not from
--     a worksheet. In Snowsight you can instead use Data > Add Data > Load.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT csv_demo_ff
  TYPE = CSV
  FIELD_DELIMITER = ','
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('')
  EMPTY_FIELD_AS_NULL = TRUE;

CREATE OR REPLACE STAGE cortex_function_stage
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')   -- SSE is required for AI file functions
  FILE_FORMAT = csv_demo_ff;

COPY INTO customer_reviews FROM @CORTEX_FUNCTION_STAGE/customer_reviews.csv;
COPY INTO support_tickets FROM @CORTEX_FUNCTION_STAGE/support_tickets.csv;
COPY INTO product_catalog FROM @CORTEX_FUNCTION_STAGE/product_catalog.csv; 
COPY INTO customer_notes_pii FROM @CORTEX_FUNCTION_STAGE/customer_notes_pii.csv;
COPY INTO call_transcripts FROM @CORTEX_FUNCTION_STAGE/call_transcripts.csv;
COPY INTO contracts FROM @CORTEX_FUNCTION_STAGE/contracts.csv;

-- ---------------------------------------------------------------------
-- 3. Verify
-- ---------------------------------------------------------------------
SELECT 'customer_reviews'   AS table_name, COUNT(*) AS row_count FROM customer_reviews
UNION ALL SELECT 'support_tickets',    COUNT(*) FROM support_tickets
UNION ALL SELECT 'product_catalog',    COUNT(*) FROM product_catalog
UNION ALL SELECT 'customer_notes_pii', COUNT(*) FROM customer_notes_pii
UNION ALL SELECT 'call_transcripts',   COUNT(*) FROM call_transcripts
UNION ALL SELECT 'contracts',          COUNT(*) FROM contracts
ORDER BY table_name;

-- Confirm the AI functions are callable at all before running the rest:
SELECT AI_COMPLETE('claude-sonnet-4-6', 'Reply with the single word: ready') AS smoke_test;

--SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS; --You can Pick any model showing GA
