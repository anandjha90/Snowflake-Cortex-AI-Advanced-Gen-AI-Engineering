# End to End RAG Pipeline
## End to End RAG Pipeline Using Cortex and Streamlit

### Precheck (If you have access to Snowflake Notebooks)
1. Create a stage to store the PDFs (Demo uses a stage called RAG)
2. Load the pdfs via the UI
3. Go to projects, notebooks, and upload 4_rag_sf_notebook.ipynb
4. In the packages drop down add in the packages from the environment.yml file
5. Run the notebook!

### Precheck (If running from Visual Studio Code
1. Utilize the `environment.yml` file to set up your Python environment for the demo:
    - Examples in the terminal:
        - `conda env create -f environment.yml`
        - `micromamba create -f environment.yml -y`
2. Create a `.env` file and populate it with your account details:

    ```plaintext
    SNOWFLAKE_ACCOUNT = abc123
    SNOWFLAKE_USER = username
    SNOWFLAKE_PASSWORD = your_password
    SNOWFLAKE_ROLE = your_role
    SNOWFLAKE_WAREHOUSE = warehouse_name
    SNOWFLAKE_DATABASE = database_name
    SNOWFLAKE_SCHEMA = schema_name
    ```

### Step 1: Run notebook `1_rag.ipynb`

This lesson will:
- Create a stage for your unstructured documents (PDFs in this case).
- Create a UDF named `readpdf` that reads in the PDF as raw text.
- Create a UDF that chunks the text leveraging Langchain.
- Create a vector store leveraging Cortex to create embeddings out of the chunks.


### Step 2: Run `2_rag.sql`

- Show the vector store.
- Create a table that will track all inputs and outputs from the Streamlit app.
- Showcase how we can query the most relevant chunks from the vector store.
- Showcase how we can leverage Cortex LLMs to get answers from the relevant chunks.

### Step 3: Streamlit App Integration

Copy Streamlit app code into SiS and ask the question: "What % of Snowflake customers process unstructured data?" and watch it in action!
