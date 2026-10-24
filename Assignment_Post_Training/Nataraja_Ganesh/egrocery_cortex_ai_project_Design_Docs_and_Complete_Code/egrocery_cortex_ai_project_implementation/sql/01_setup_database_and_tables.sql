-- ====================================================================
-- Script: 01_setup_database_and_tables.sql
-- Description: Creates Database, Schema, Tables, and Staging Areas
-- ====================================================================

USE ROLE ACCOUNTADMIN;
CREATE DATABASE IF NOT EXISTS E_GROCERY_DB;
CREATE SCHEMA IF NOT EXISTS E_GROCERY_DB.SUPPORT_SCHEMA;
CREATE WAREHOUSE IF NOT EXISTS E_GROCERY_WH 
    WAREHOUSE_SIZE = 'XSMALL' 
    AUTO_SUSPEND = 60 
    AUTO_RESUME = TRUE;

USE DATABASE E_GROCERY_DB;
USE SCHEMA SUPPORT_SCHEMA;
USE WAREHOUSE E_GROCERY_WH;

-- Enable Cross-Region Cortex Functions
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- 1. Product Catalog Table
CREATE OR REPLACE TABLE PRODUCT_CATALOG (
    PRODUCT_ID STRING,
    PRODUCT_NAME STRING,
    CATEGORY STRING,
    PRICE FLOAT,
    STOCK_QTY INT,
    DIETARY_INFO STRING,
    SPECIFICATIONS STRING
);

INSERT INTO PRODUCT_CATALOG VALUES 
('P001', 'Organic Whole Milk 1L', 'Dairy', 3.49, 120, 'Organic, Pasteurized, Contains Dairy', 'Fresh farm organic whole milk, keep refrigerated.'),
('P002', 'Gluten-Free Almond Bread', 'Bakery', 5.99, 45, 'Gluten-Free, Vegan, Nut Allergy Warning', 'Artisanal gluten-free sliced bread made with almond flour.'),
('P003', 'Fresh Hass Avocados (Pack of 4)', 'Produce', 4.99, 85, 'Vegan, Non-GMO, Raw', 'Ripe and ready-to-eat Hass avocados sourced locally.'),
('P004', 'Organic Honeycrisp Apples 2lb', 'Produce', 6.49, 10, 'Organic, Fresh Fruit', 'Crisp and sweet organic apples.');

-- 2. Stage for Storing Raw Policy Documents
CREATE OR REPLACE STAGE ONLINE_POLICY_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- 3. Policy Document Chunks & Vector Store Table
CREATE OR REPLACE TABLE POLICY_DOCUMENT_CHUNKS (
    DOC_NAME STRING,
    CHUNK_ID NUMBER AUTOINCREMENT,
    CHUNK_TEXT STRING,
    CHUNK_EMBEDDING VECTOR(FLOAT, 768),
    UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 4. Customer Orders Table
CREATE OR REPLACE TABLE CUSTOMER_ORDERS (
    ORDER_ID STRING,
    CUSTOMER_ID STRING,
    PRODUCT_NAME STRING,
    CATEGORY STRING,
    ORDER_DATE TIMESTAMP_NTZ,
    STATUS STRING,
    TOTAL_AMOUNT FLOAT
);

INSERT INTO CUSTOMER_ORDERS VALUES 
('ORD-9001', 'CUST-101', 'Organic Honeycrisp Apples 2lb', 'Produce', DATEADD('hour', -12, CURRENT_TIMESTAMP()), 'Delivered', 6.49),
('ORD-9002', 'CUST-101', 'Organic Whole Milk 1L', 'Dairy', DATEADD('day', -3, CURRENT_TIMESTAMP()), 'Delivered', 3.49),
('ORD-9003', 'CUST-102', 'Gluten-Free Almond Bread', 'Bakery', CURRENT_TIMESTAMP(), 'Out for Delivery', 5.99);

-- 5. Customer Feedback & Sentiment Log Table
CREATE OR REPLACE TABLE CUSTOMER_FEEDBACK (
    FEEDBACK_ID NUMBER AUTOINCREMENT,
    CUSTOMER_ID STRING,
    ORDER_ID STRING,
    MESSAGE STRING,
    CATEGORY STRING,
    SENTIMENT_SCORE FLOAT,
    LOGGED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
