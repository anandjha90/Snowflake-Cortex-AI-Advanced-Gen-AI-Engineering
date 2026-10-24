# Intelligent Customer Support Agent for E-Grocery using Streamlit & Snowflake Cortex AI

## Overview
This repository contains production-ready, deployment-optimized code and sample data for an autonomous, data-aware AI Support Agent for an Online Grocery platform. Built natively inside Snowflake using **Snowflake Cortex AI** and **Streamlit in Snowflake (SiS)**.

---

## Folder Structure
```
egrocery_cortex_rag_project/
├── README.md
├── requirements.txt
├── data/
│   ├── E_GROCERY_ONLINE_SHOPPING_POLICIES.md
│   └── REFUND_ELIGIBILITY_AND_PAYMENT_TIMELINES.md
├── sql/
│   ├── 01_setup_database_and_tables.sql
│   └── 02_ingest_and_embed_policies.sql
└── streamlit_app/
    ├── app.py
    └── environment.yml
```

---

## Setup & Deployment Instructions

### Step 1: Execute SQL Setup Scripts
1. Log in to your Snowflake account with `ACCOUNTADMIN` role (or role with schema creation privileges).
2. Open a SQL Worksheet and execute `sql/01_setup_database_and_tables.sql`.
3. Upload policy files in `data/` into `@ONLINE_POLICY_STAGE`.
4. Run `sql/02_ingest_and_embed_policies.sql` to chunk and embed policy documents.

### Step 2: Deploy Streamlit in Snowflake (SiS)
1. In Snowflake, navigate to **Projects -> Streamlit**.
2. Click **+ Streamlit App**.
3. Select Database: `E_GROCERY_DB`, Schema: `SUPPORT_SCHEMA`, Warehouse: `E_GROCERY_WH`.
4. Paste the code from `streamlit_app/app.py` into the editor and click **Run**.
