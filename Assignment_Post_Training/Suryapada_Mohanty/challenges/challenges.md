# 7. Challenges and Resolutions

| # | Challenge | Symptom | Root cause | Resolution |
|---|---|---|---|---|
| 1 | Streamlit version error | `Failed to get the version of the Streamlit library … ">=1.48.0"` | The container runtime could not install Streamlit: no PyPI access, and a stale `uv.lock` listed no packages | Removed the stale lock, used the default `pyproject.toml` (`streamlit[snowflake]>=1.54.0`), created `PYPI_ACCESS_INTEGRATION` |
| 2 | Integration not attached | Same error after the integration was created | Creating an integration doesn't attach it (`external_access_integrations = []`) | `ALTER STREAMLIT … SET EXTERNAL_ACCESS_INTEGRATIONS`, plus a `snowflake.yml` entry so it persists on redeploy |
| 3 | Placeholder in a GRANT | `syntax error … unexpected '<'` | `<app_role>` was run literally | Explained that the grant is optional for the owner role; use a real role name |
| 4 | Guide's model unavailable | `COMPLETE` 400 errors | `mistral-large2`, `snowflake-arctic`, Claude and GPT models are not available in this region | Tested 11 models; the selector offers the 3 that work. Enabling cross-region inference would add more |
| 5 | Missing search service / empty table | The app could not answer | The original setup never created `CC_SEARCH_SERVICE_CS` or loaded documents | Rebuilt everything from scratch following the guide |
| 6 | No internet egress for the guide's PDFs | `egress to this host is not allowed` (GitHub) | Sandbox network policy | Generated 5 sample manuals and uploaded them with `PUT`; real PDFs can replace them |
| 7 | `GET_PRESIGNED_URL` with a bound path | `Argument 2 … cannot be null or empty` | The path can't be a bind variable at compile time | Select the URL from `DIRECTORY(@DOCS)` with `WHERE RELATIVE_PATH = ?` |
| 8 | SQL injection risk | Original code built SQL with f-strings | Tutorial pattern | All user values are bound parameters; HTML output is escaped |
| 9 | `get_active_session` / `snowflake.core` | Not suited to the Workspace container runtime | Older warehouse-runtime pattern | `st.connection("snowflake")`; `SEARCH_PREVIEW` through SQL |
| 10 | Stream never consumed | The task would fire every minute indefinitely | The procedure reads `DIRECTORY()`, not the stream | The task inserts stream rows into `DOCS_PROCESSING_LOG`, which advances the offset |
| 11 | Deleted files stayed searchable | Stale answers citing removed PDFs | Insert-only logic in the guide | `PROCESS_DOCS` deletes chunks whose file is gone |
| 12 | `core.py` not deployed | Would fail with `ImportError: core` | The UI split into two files, but `artifacts` listed only `streamlit_app.py` | Added `core.py` to `artifacts` |
| 13 | Query-rewrite drift | A rewritten query mixed an unrelated earlier topic into a new question | The history window includes unrelated turns | Memory toggle, Clear conversation, 7-message window |
| 14 | Latency variance on `llama3.3-70b` | p90 went from 2.0 s to 5.9 s between runs; follow-ups took 7.7–9.3 s in evaluation run 2 | Shared serverless inference load, plus the extra rewrite call | Documented; `llama3.1-8b` is the low-latency option |
| 15 | Over-retrieved source links | 3 source links shown when only 1 is relevant | Fixed top-k with a tiny corpus | Recommended a score threshold or fewer passages |
| 16 | Capturing real UI screenshots | Snowsight's hosted preview can't be automated from the sandbox | No browser access to Snowsight | Ran the same app locally (Streamlit 1.66) against the live Snowflake objects and captured it with headless Chromium; the token was kept only in a temporary `/tmp` file that was deleted afterwards |
| 17 | Small evaluation corpus | Perfect scores that won't hold at scale | Sample data only | Documented as a caveat; proposed a larger benchmark |

## Lessons learned
- In Workspace Streamlit apps, check **runtime configuration** first: `pyproject.toml`, the lock file, external access integrations and `artifacts`.
- Check **model availability per region** before hard-coding model names.
- Make ingestion **idempotent** (handle new and deleted files) so the initial load and incremental runs share one code path.
- Keep **UI and logic in separate files** (`streamlit_app.py` / `core.py`) so the UI can be redesigned without touching RAG behaviour.
