# Architecture & Technical Specification: HR Policy RAG Chatbot with Snowflake Cortex Search

## 1. Overview & System Objectives

The **HR Policy Assistant** is an enterprise Retrieval-Augmented Generation (RAG) system built natively inside Snowflake. It enables employees to query complex corporate HR policies (e.g., Paid Leave, Remote Work, Ethics, Health Benefits) in natural language and receive immediate, context-grounded answers.

### Key System Objectives:
* **Context Grounding:** Eliminate LLM hallucinations by restricting answers to retrieved chunks from official company policy documents (`docs/global_pto_policy.md`, `docs/benefits_and_health_coverage.md`, etc.).
* **Hybrid Search with Metadata Filtering:** Utilize Snowflake Cortex Search (combining vector similarity and BM25 lexical matching) with strict metadata filtering by policy category.
* **Dual Execution Modes:** Support both RAG Mode (Cortex Search Enabled) and Direct Standard LLM Mode (Cortex Search Disabled) for comparative auditing and testing.
* **Native Security & Governance:** Process all data, chunking, classification, vector indexing, and LLM inference inside Snowflake's security perimeter without external API calls.

---

## 2. System Architecture & Layers

### 2.1 Architectural Layers & Components Matrix

| Layer                 | Components                                                                                                  | Primary Responsibility |
| **Ingestion**         | Stage `HR_DOCS_STAGE`                                                                                       | Load the docs to stage|
| **Processing**        | Procedure `PROCESS_HR_DOCS()`, `AI_PARSE_DOCUMENT()`, `SPLIT_TEXT_RECURSIVE_CHARACTER()`, `CLASSIFY_TEXT()` | Text parsing, recursive chunking, and LLM-based categorization into predefined policy domains. |
| **Knowledge Store**   | Table `RAW_HR_DOCUMENTS`, Table `DOCS_CHUNKS_TABLE`                                                         | Persistence layer storing raw parsed content and indexed chunked passages with metadata. |
| **Retrieval**         | Cortex Search Service `HR_POLICY_SEARCH_SERVICE`                                                            | Serverless hybrid semantic + lexical retrieval with real-time `@eq` filtering on `CATEGORY`. |
| **Generation**        | `SNOWFLAKE.CORTEX.COMPLETE` (`llama3-70b`, `mistral-large`, `snowflake-arctic`)                             | Context-aware query expansion, prompt synthesis, and grounded answer generation. |
| **Presentation**      | Streamlit in Snowflake (`streamlit_app.py` UI, `core.py` logic)                                             | Interactive conversational chat interface, model selector, category filters, and live context inspector. |
| **Platform**          | `COMPUTE_WH`, Cortex Search Engine, Snowflake RBAC                                                          | Underlying serverless compute, role-based access control, and native infrastructure. |

---

## 3. Application Module Design

### 3.1 Directory Tree Structure

```text
cortex-hr-chatbot/
├── streamlit_app.py   # Presentation Layer: Header, sidebar controls, dual-mode chat interface, context inspector
├── core.py            # Business & RAG Logic: Active session management, search, prompt engineering, Cortex calls
├── setup_pipeline.sql # SQL Pipeline: Stage setup, stream, tables, stored procedure, task, Cortex Search Service
├── snowflake.yml      # Deployment Metadata: Definition of warehouse, runtime environment, and app dependencies
├── pyproject.toml     # Python dependencies (streamlit>=1.54.0, snowflake-snowpark-python)
└── .streamlit/
    └── config.toml    # UI layout configuration, theme settings, and runner options
```

### 3.2 Modular Separation of UI and Core RAG Logic

The application strictly decouples user presentation from database and RAG operations:
* **`streamlit_app.py`**: Manages UI state, renders Streamlit widgets (checkboxes, dropdowns, expanders), renders chat bubbles, and passes user interactions to `core.py`.
* **`core.py`**: Handles active Snowpark sessions, executes search service queries, formats system/user prompts, constructs JSON chat history, and calls `CORTEX.COMPLETE`.

*Benefits:* This separation allows the frontend UI to be updated or replaced without modifying underlying vector search mechanics or LLM prompt formatting logic.

---

## 4. Key Functions Specification (`core.py`)

| Function                                | SQL / Service Calls                                    | Implementation Notes |
| `load_documents()`                      | `SELECT DISTINCT RELATIVE_PATH FROM DOCS_CHUNKS_TABLE` | Cached via `@st.cache_data(ttl=300)`. Populates document inventory panel in UI. |
| `load_categories()`                     | `SELECT DISTINCT CATEGORY FROM DOCS_CHUNKS_TABLE`      | Cached via `@st.cache_data(ttl=300)`. Populates sidebar category filter. |
| `search_chunks(query, category, limit)` | `svc.search(query, COLUMNS, limit=limit, filter=filter_obj)` | Queries `HR_POLICY_SEARCH_SERVICE`. Applies `@eq` filter if category $\neq$ `'ALL'`. Returns JSON array of chunks. |
| `summarize_question_with_history()`     | `SNOWFLAKE.CORTEX.COMPLETE()`                          | Takes active chat history and rewrites ambiguous follow-up questions into standalone queries before retrieval. |
| `create_prompt(query, chunks)`          | *In-Memory Python logic*                               | Merges system guidelines, retrieved context chunks (JSON format), and user query into a structured instruction prompt. |
| `answer(query, category, model, use_rag)` | `search_chunks()` + `CORTEX.COMPLETE()`              | Executes full RAG pipeline when `use_rag=True`. Bypasses search service when `use_rag=False` to produce standard LLM response. |
| `submit(user_input)`                    | *State Management*                                     | Appends input to `st.session_state.messages`, triggers response generation, and handles error rollbacks. |

---

## 5. Data Model (`DOCS_CHUNKS_TABLE` & `RAW_HR_DOCUMENTS`)

### 5.1 `RAW_HR_DOCUMENTS` (Staging Table)

| Column Name     | Data Type      | Description / Example |
| `RELATIVE_PATH` | `VARCHAR(500)` | `docs/global_pto_policy.md` |
| `FILE_SIZE`     | `NUMBER`       | `14250` |
| `PARSED_TEXT`   | `VARCHAR`      | Raw parsed text produced by `AI_PARSE_DOCUMENT`. |
| `LOADED_AT`     | `TIMESTAMP_NTZ`| `2026-10-24 01:15:00.000` |

### 5.2 `DOCS_CHUNKS_TABLE` (Search Index Source)

| Column Name       | Data Type      | Description / Example |
| `RELATIVE_PATH`   | `VARCHAR(500)` | `docs/global_pto_policy.md` |
| `SIZE`            | `NUMBER`       | `1240` |
| `FILE_URL`        | `VARCHAR`      | `snowflake://stage/HR_DOCS_STAGE/docs/global_pto_policy.md` |
| `SCOPED_FILE_URL` | `VARCHAR`      | Presigned scoped URL generated via `GET_PRESIGNED_URL()`. |
| `CHUNK_INDEX`     | `INTEGER`      | `0` (Zero-indexed chunk position within file). |
| `CHUNK`           | `VARCHAR`      | Markdown text excerpt ($\le 1512$ characters). |
| `CATEGORY`        | `VARCHAR(100)` | `Paid Time Off & Leave`, `Remote Work & Equipment`, `Benefits & Health`. |
| `CREATED_AT`      | `TIMESTAMP_NTZ`| `2026-10-24 01:15:05.000` |

---

## 6. AI & Cortex Integration Details

```
[Uploaded HR Policies] --> Stage: @HR_DOCS_STAGE
                                |
       +------------------------+------------------------+
       |                                                 |
       v                                                 v
AI_PARSE_DOCUMENT()                      SPLIT_TEXT_RECURSIVE_CHARACTER()
(Mode: LAYOUT for PDFs/MD)               (Target Chunk Size: ~1000-1500 chars)
                                                         |
                                                         v
                                                 CLASSIFY_TEXT()
                                         (Taxonomy: PTO, Benefits, Ethics)
                                                         |
                                                         v
                                              DOCS_CHUNKS_TABLE
                                                         |
                                                         v
                                            HR_POLICY_SEARCH_SERVICE
                                            (Target Lag = '1 hour')
                                                         |
                                                         v
                                            Streamlit UI & Cortex Complete
```

1. **`SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT`**:
   * Utilizes `mode => 'LAYOUT'` to parse structural document hierarchies (headers, tables, paragraphs) from raw PDF/Markdown documents into structured text.
2. **`SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER`**:
   * Recursively breaks parsed text into clean, contextual passages (chunk size $\approx 1500$ chars, overlap $\approx 200$ chars), preserving paragraph boundaries.
3. **`SNOWFLAKE.CORTEX.CLASSIFY_TEXT`**:
   * Evaluates text chunks against predefined HR category taxonomy (`'Paid Time Off & Leave'`, `'Remote Work & Equipment'`, `'Compensation & Performance'`, `'Benefits & Health'`, `'Code of Conduct'`) to attach accurate metadata for downstream search filtering.
4. **Cortex Search Service (`HR_POLICY_SEARCH_SERVICE`)**:
   * Built directly on `DOCS_CHUNKS_TABLE` using `ON chunk` with `ATTRIBUTES category`. Continuously indexes vectors and lexical tokens with a defined `TARGET_LAG = '1 hour'`.
5. **Cortex Complete (`SNOWFLAKE.CORTEX.COMPLETE`)**:
   * Executes LLM inference using models such as `llama3-70b`, `mistral-large`, or `snowflake-arctic` to perform conversational query rewriting and context-grounded answer generation.

---

## 7. Security & Governance

* **Role-Based Access Control (RBAC):** Access to `HR_DOCS_STAGE`, tables, search services, and Cortex functions is strictly restricted via Snowflake security roles (`HR_RAG_ADMIN`, `HR_APP_USER`).
* **Embedded Session Identity:** The Streamlit application connects natively using `st.connection("snowflake")` under the app's executing user role—eliminating hardcoded passwords or API keys in repository code.
* **Document Security via Scoped URLs:** Original document files stored in stages are never directly exposed to users. Documents are accessed exclusively via temporary, encrypted 6-minute scoped URLs (`GET_PRESIGNED_URL`).
* **SQL Injection & Prompt Sanitization:** All queries to Cortex Search and Snowpark execute via parameterized bindings. User-submitted text rendered in the HTML UI is escaped to prevent cross-site scripting (XSS).

---

### Summary of Additions
* **Structure Alignment:** Cleanly mirrors the requested architectural format (System Objectives, Layers Matrix, Module Structure, Key Functions, Data Models, AI/Cortex Flow Diagram, Security, and Scalability).
* **Accurate Data Models:** Correctly maps `RAW_HR_DOCUMENTS` and `DOCS_CHUNKS_TABLE` schemas with their respective data types and metadata columns (`CATEGORY`, `SCOPED_FILE_URL`).
* **Specific AI Functions:** Details `AI_PARSE_DOCUMENT`, `SPLIT_TEXT_RECURSIVE_CHARACTER`, `CLASSIFY_TEXT`, `CORTEX SEARCH SERVICE`, and `CORTEX.COMPLETE`.
