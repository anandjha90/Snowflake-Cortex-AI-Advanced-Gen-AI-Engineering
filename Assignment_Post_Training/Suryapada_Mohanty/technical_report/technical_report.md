# 1. Technical Report – Document Q&A Chatbot with Snowflake Cortex Search

## 1.1 Objective
Build a Retrieval-Augmented Generation (RAG) assistant that answers natural-language questions about product manuals
stored as PDFs, entirely inside Snowflake. It follows the Snowflake guide *"Ask Questions to Your Own Documents with
Snowflake Cortex Search"*, including the *"ChatBot UI with Conversation History"* step. The data pipeline matches
the guide; the Streamlit UI is redesigned as a "Knowledge Hub" portal whose Ask tab is titled
**"Chat Document Assistant with Snowflake Cortex"**.

## 1.2 Scope
| In scope | Out of scope |
|---|---|
| PDF ingestion, parsing, chunking, classification | OCR of scanned or handwritten documents |
| Hybrid search over chunks with a category filter | LLM fine-tuning |
| Multi-turn chat with history-aware query rewriting | Authentication beyond Snowflake RBAC |
| Automatic processing of new and deleted files | Multi-tenant document isolation |
| Session activity log with feedback and CSV export | Persisting feedback to a table |

## 1.3 Technology stack
| Layer | Component |
|---|---|
| Storage | Internal stage `DOCS` (directory table with auto-refresh, `SNOWFLAKE_SSE` encryption) |
| Parsing | `SNOWFLAKE.CORTEX.PARSE_DOCUMENT` (mode `LAYOUT`, returns markdown) |
| Chunking | `SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER` (markdown, 1512 chars, 256 overlap) |
| Classification | `SNOWFLAKE.CORTEX.CLASSIFY_TEXT` → `Bike` / `Snow` |
| Retrieval | Cortex Search Service `CC_SEARCH_SERVICE_CS` (vector + keyword + reranker), `TARGET_LAG = 1 minute` |
| Generation | `SNOWFLAKE.CORTEX.COMPLETE` – `llama3.3-70b` (default), `llama3.1-70b`, `llama3.1-8b` |
| Orchestration | Stream `DOCS_STREAM` + task `PARSE_AND_INSERT_PDF_TASK` (1-minute schedule) + procedure `PROCESS_DOCS` |
| UI | Streamlit in Snowflake, container runtime (`SYSTEM_COMPUTE_POOL_CPU`); `streamlit_app.py` (UI) + `core.py` (logic) |
| Network | External access integration `PYPI_ACCESS_INTEGRATION` (runtime installs `streamlit[snowflake]>=1.54.0`) |

## 1.4 Snowflake objects (`CC_QUICKSTART_CORTEX_SEARCH_DOCS.DATA`)
| Object | Type | Purpose |
|---|---|---|
| `DOCS` | Stage | Raw PDFs |
| `DOCS_CHUNKS_TABLE` | Table | `RELATIVE_PATH, SIZE, FILE_URL, SCOPED_FILE_URL, CHUNK, CHUNK_INDEX, CATEGORY` |
| `PROCESS_DOCS()` | SQL procedure | Idempotent: removes chunks of deleted files, then parses, chunks and classifies new PDFs |
| `DOCS_STREAM` | Stream on stage | Captures file INSERT/DELETE events |
| `PARSE_AND_INSERT_PDF_TASK` | Task | Runs only when the stream has data; logs events and then calls `PROCESS_DOCS` |
| `DOCS_PROCESSING_LOG` | Table | Audit log of file events (also consumes the stream) |
| `CC_SEARCH_SERVICE_CS` | Cortex Search Service | Index on `CHUNK`; filterable attribute `CATEGORY` |

## 1.5 Implementation by guide section
1. **Organize Documents** – database, schema and stage with a directory table; 5 product manuals uploaded.
2. **Pre-process Documents** – parse → split → classify in one set-based `INSERT … SELECT` inside `PROCESS_DOCS`.
3. **Create Cortex Search Service** – searches `CHUNK`; returns `CHUNK_INDEX, RELATIVE_PATH, FILE_URL, CATEGORY`.
4. **Chat UI with retrieval and generation** – `core.search_chunks()` → prompt → `core.cortex_complete()`.
5. **Chatbot with conversation history** – a sliding window of 7 messages; follow-ups are rewritten by the LLM into a
   standalone search query before retrieval.
6. **Automatic processing** – stream + task + procedure; verified with a live upload.
7. **Cleanup** – `cortex-doc-chatbot/cleanup.sql` (not run).

## 1.6 UI features (Knowledge Hub)
- **Header:** live counts (documents · passages · categories).
- **Sidebar "Advanced options":** model, passages to retrieve (1–10), "Remember conversation" toggle, Clear conversation, Refresh documents.
- **Ask tab:** title "💬 Chat Document Assistant with Snowflake Cortex" with the caption "Answers grounded in your documents,
  with links to the sources they came from", a "Search in" category radio (ALL / Bike / Snow), starter questions and chat history.
  Each answer shows source-document links (presigned URLs), a meta line (model · latency · searched query) and thumbs feedback.
- **Browse documents tab:** document cards with category and passage-count tags, plus a "Summarize this document" action.
- **Activity tab:** per-question log (time, question, model, category, seconds, sources, feedback) with a CSV download.

## 1.7 Differences from the guide
| Area | Guide | This build | Reason |
|---|---|---|---|
| Default LLM | `mistral-large2` | `llama3.3-70b` | `mistral-large2`, `snowflake-arctic`, Claude and GPT models error in this region (8 of 11 tested) |
| Search API | `snowflake.core` Python SDK | `SNOWFLAKE.CORTEX.SEARCH_PREVIEW` via SQL | No extra package in the container runtime |
| Task body | Inline SQL | Procedure `PROCESS_DOCS` (idempotent, also handles deletes) | Same code for the initial load and incremental runs |
| Session | `get_active_session()` | `st.connection("snowflake")` | Required by the Workspace container runtime |
| SQL safety | f-strings with user input | Bound parameters for every user value | Prevents SQL injection |
| UI | Sidebar + chat | Knowledge Hub with the "Chat Document Assistant with Snowflake Cortex" Ask tab (tabs, document cards, activity log, feedback) | Requested redesign |
