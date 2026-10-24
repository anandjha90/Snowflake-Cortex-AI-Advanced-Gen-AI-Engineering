**PROJECT EXECUTION & VERIFICATION**

Follow this exact sequence to deploy and test the entire solution in Snowflake:

**Step 1 (Run DDL Script):** Execute sql/01_setup_database_and_tables.sql in a Snowflake SQL Worksheet under
the ACCOUNTADMIN role.

**Step 2 (Upload Documents):** In Snowflake Snowsight UI, navigate to Data » Databases » E_GROCERY_DB »
SUPPORT_SCHEMA » Stages » ONLINE_POLICY_STAGE and upload your .md policy files.

**Step 3 (Vector Generation):** Execute sql/02_ingest_and_embed_policies.sql to chunk and compute e5-basev2
embeddings.

**Step 4 (Launch Streamlit App):** Go to Projects » Streamlit, create a new app named E_GROCERY_SUPPORT_APP, set the
database to E_GROCERY_DB, schema to SUPPORT_SCHEMA, paste streamlit_app/app.py into the editor, and click Run.

**Step 5 (Verification):** Submit test queries such as "Can I get a refund for bruised avocados?" or "Do you have gluten-free
bread in stock?" and check the expandable drawer to verify citation source mapping and sentiment score logging in
CUSTOMER_FEEDBACK.

