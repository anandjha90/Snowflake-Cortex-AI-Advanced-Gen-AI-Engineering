# 4. Output – UI Interface, Inputs and Outputs

**How these were captured:** the actual `streamlit_app.py` + `core.py` were run with Streamlit 1.66 and driven
with headless Chromium (Playwright) on 2026-10-15. They were connected to the live Snowflake objects
(`CC_SEARCH_SERVICE_CS`, `DOCS_CHUNKS_TABLE`, `CORTEX.COMPLETE`), so every answer on screen is a real model response.
They are not from Snowsight's hosted preview, so the frame around the app (e.g. the "Deploy" menu) differs slightly from Snowsight.

---

## 4.1 UI interface – landing page
![Landing page](screenshots/01_landing_page.png)

| Area | Shows |
|---|---|
| Header | "Knowledge Hub" · 5 documents · 5 passages · 2 categories |
| Sidebar | Advanced options: Model `llama3.3-70b`, Passages to retrieve = 3, Remember conversation = on, Clear conversation, Refresh documents |
| Ask tab | Title "💬 Chat Document Assistant with Snowflake Cortex", caption "Answers grounded in your documents, with links to the sources they came from.", Search in = ALL / Bike / Snow, two starter-question buttons, chat input |

## 4.2 Input – question typed
![Input](screenshots/02_input_question.png)

**Input:** `Is there any special lubricant to be used with the premium bike?` (Search in = ALL)

## 4.3 Output – answer with sources
![Answer](screenshots/03_output_answer_with_sources.png)

| Field | Value |
|---|---|
| Answer | Yes, the Premium Bike Chain Lube LX-7, a synthetic wax-based lubricant, should be used on the chain. |
| Sources | Mondracer_Infant_Bike.pdf · **Premium_Bicycle_User_Guide.pdf** · The_Ultimate_Downhill_Bike.pdf |
| Meta | llama3.3-70b · 2.7 s · searched: the question as asked (no history yet) |

## 4.4 Input / output – follow-up using conversation history
![Follow-up](screenshots/04_followup_with_history.png)

| Field | Value |
|---|---|
| Input | `What should I avoid using on it?` |
| Rewritten search query | "What types of lubricants should I avoid using on my premium bike chain to prevent damage, now that I know to use the Premium Bike Chain Lube LX-7?" |
| Answer | You should avoid using WD-40 or motor oil on the chain because they attract grit and damage the drivetrain. Also, never use DOT fluid on the hydraulic brakes. |
| Meta | llama3.3-70b · 3.6 s (two LLM calls: rewrite + answer) |

## 4.5 Input / output – out-of-scope question
![Out of scope](screenshots/05_out_of_scope_question.png)

| Field | Value |
|---|---|
| Input | `Who won the 2022 football world cup?` |
| Answer | I don't have the information. |
| Meta | llama3.3-70b · 1.9 s |
| Behaviour | The model declines to answer instead of using general knowledge |

## 4.6 Input / output – category filter (Snow)
| Input | Output |
|---|---|
| ![Filter input](screenshots/06a_category_filter_input.png) | ![Filter output](screenshots/06b_category_filter_output.png) |

| Field | Value |
|---|---|
| Search in | **Snow** |
| Input | `How often should I wax Carver skis?` |
| Answer | Every 5 ski days. |
| Sources | Only Snow documents: **Carver_Skis_Specification_Guide.pdf**, Ski_Boots_TDBootz_Special.pdf |
| Meta | llama3.3-70b · 1.8 s |

## 4.7 Browse documents tab
![Browse documents](screenshots/07_browse_documents.png)

5 document cards, each with a category tag and a passage count, plus a "Summarize this document" button that sends a summary question to the Ask tab.

## 4.8 Activity tab
![Activity](screenshots/08_activity_log.png)

| Time | Question | Model | Category | Seconds | Sources |
|---|---|---|---|---|---|
| 06:36:54 | Is there any special lubricant to be used with the premium bike? | llama3.3-70b | ALL | 2.7 | 3 |
| 06:37:00 | What should I avoid using on it? | llama3.3-70b | ALL | 3.6 | 3 |

Includes a "Download activity (CSV)" button.

---

## 4.9 Pipeline output
`CALL PROCESS_DOCS()` (initial 4 PDFs): `Chunks added: 4, chunks removed: 0`

| RELATIVE_PATH | CATEGORY | CHUNKS |
|---|---|---|
| Carver_Skis_Specification_Guide.pdf | Snow | 1 |
| Mondracer_Infant_Bike.pdf | Bike | 1 |
| Premium_Bicycle_User_Guide.pdf | Bike | 1 |
| Ski_Boots_TDBootz_Special.pdf | Snow | 1 |
| The_Ultimate_Downhill_Bike.pdf | Bike | 1 |

Task history: **SUCCEEDED** in 10 s for the 5th upload (Carver Skis, event `INSERT`); later runs **SKIPPED** ("Conditional expression for task evaluated to false").

Search scores for "special lubricant for premium bike chain" (filter Bike):

| Rank | Document | cosine | text_match | reranker |
|---|---|---|---|---|
| 1 | Premium_Bicycle_User_Guide.pdf | 0.657 | 0.443 | **0.256** |
| 2 | The_Ultimate_Downhill_Bike.pdf | 0.379 | 0.114 | -10.94 |
