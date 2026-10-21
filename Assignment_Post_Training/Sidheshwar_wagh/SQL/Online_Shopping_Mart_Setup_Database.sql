-- ============================================================================
-- Snowflake Cortex Search - E-Commerce RAG Assistant Setup
-- Domain: Online Shopping Mart Customer Support Help Center
-- ============================================================================

-- 1. Create the primary database and schema for our e-commerce data
CREATE DATABASE IF NOT EXISTS ECOM_CORTEX_DB; 
USE DATABASE ECOM_CORTEX_DB;

CREATE SCHEMA IF NOT EXISTS SUPPORT; 
USE SCHEMA SUPPORT;

-- 2. Create the virtual warehouse that will power the ingestion and index refreshes
CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH 
  WITH WAREHOUSE_SIZE = 'XSMALL' 
  AUTO_SUSPEND = 60 
  AUTO_RESUME = TRUE 
  INITIALLY_SUSPENDED = TRUE;

USE WAREHOUSE COMPUTE_WH;

-- 3. Create the table that will store our pre-chunked help center articles
CREATE OR REPLACE TABLE HELP_CENTER_CHUNKS (
    DOC_URL VARCHAR,      -- URL pathway mimicking a CMS or website link
    CATEGORY VARCHAR,     -- Policy classification for filtering (e.g., Returns, Billing)
    CHUNK VARCHAR,        -- The actual text passage containing policy details
    CHUNK_INDEX INTEGER   -- Sequencing identifier for ordered passages
);

-- 4. Insert Sample E-Commerce Knowledge Base Data
-- Note: Instead of parsing raw PDFs, this simulates extracting text blocks directly 
-- from a CMS (Content Management System) like Zendesk or a knowledge base.
INSERT INTO HELP_CENTER_CHUNKS (DOC_URL, CATEGORY, CHUNK, CHUNK_INDEX) VALUES

-- Returns Category Data
('/policies/returns', 'Returns', 'Online Shopping Mart Standard Return Policy: Customers have 30 days from the date of delivery to return unworn apparel, shoes, and home goods for a full refund to the original payment method. Items must include all original tags and packaging. Return shipping is free for VIP members, whereas non-members will have a $5.99 return shipping fee deducted from their refund.', 0),
('/policies/returns', 'Returns', 'Online Shopping Mart Electronics Return Policy: Electronics, including laptops, mobile devices, and smart home appliances, must be returned within 14 days of delivery. All electronics must be in original condition, unactivated, and include all cords and manuals. A 15% restocking fee applies to open-box electronics unless the item arrived defective or damaged.', 1),

-- Shipping Category Data
('/policies/shipping', 'Shipping', 'Online Shopping Mart Shipping Tiers: We offer three shipping speeds within the continental US. 1) Standard Shipping takes 3-5 business days and costs $4.99 (Free on orders over $50). 2) Expedited Shipping takes 2 business days and costs $12.99. 3) Same-Day Delivery is available in select metropolitan zip codes for orders placed before 12:00 PM local time, costing $19.99.', 0),
('/policies/shipping', 'Shipping', 'International Shipping & Customs: Online Shopping Mart ships internationally to Canada, the UK, and Australia. International standard delivery takes 7-14 business days. Customers are responsible for all import duties, VAT, and customs clearance fees. We cannot mark packages as "gifts" to bypass customs regulations.', 1),

-- Loyalty Program Data
('/programs/vip', 'Loyalty', 'Online Shopping Mart VIP Loyalty Program: The VIP program requires an annual subscription fee of $99. Benefits include: Free Expedited (2-day) shipping on all orders with no minimum purchase, waived return shipping fees, 5% cash back on all Online Shopping Mart brand purchases, and early access to Black Friday and Cyber Monday sales events.', 0),

-- Billing & Price Match Data
('/policies/price-match', 'Billing', 'Price Match Guarantee: Online Shopping Mart will match the price of identical items shipped and sold by major online retailers (e.g., Amazon, BestBuy, Walmart) within 7 days of your purchase. The item must be in stock at the competitor. We do not price match third-party marketplace sellers, auction sites, or refurbished items. Furthermore, we do not accept competitor coupons.', 0),
('/policies/payment-methods', 'Billing', 'Accepted Payment Methods: We accept all major credit cards (Visa, Mastercard, American Express, Discover), PayPal, Apple Pay, and Google Pay. We also offer Buy Now, Pay Later options through Klarna and Affirm for orders over $150. We do not accept cryptocurrency or cash-on-delivery (COD).', 0);

-- 5. Initialize the Hybrid Vector + Lexical Search Engine
-- The search service automatically indexes the 'CHUNK' column and allows filtering on 'CATEGORY'
CREATE OR REPLACE CORTEX SEARCH SERVICE SHOPNOVA_SEARCH_SVC
  ON CHUNK 
  ATTRIBUTES CATEGORY 
  WAREHOUSE = COMPUTE_WH 
  TARGET_LAG = '1 minute'
  AS (
    SELECT CHUNK, CHUNK_INDEX, DOC_URL, CATEGORY 
    FROM HELP_CENTER_CHUNKS
  );
