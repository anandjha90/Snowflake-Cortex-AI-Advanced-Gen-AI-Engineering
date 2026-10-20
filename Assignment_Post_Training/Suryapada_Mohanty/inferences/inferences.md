# 6. Inferences

1. **The whole pipeline runs inside Snowflake.** Parsing, chunking, classification, indexing, retrieval and generation are
   all native Cortex functions, with no external services or data movement.

2. **Retrieval quality drives answer quality.** The right document ranked first every time (MRR 1.0), and even the 8B model
   answered 12/12 correctly. On this corpus, search mattered more than model size.

3. **The reranker provides most of the precision.** Cosine similarity separated the top two documents by 0.28; the
   reranker separated them by about 11 points. Hybrid search plus reranking is a good default.

4. **Conversation history is needed for follow-ups, and it costs time.** Pronoun follow-ups ("it", "for how long") were
   resolved 6/6 times (UI + evaluation) because the question is rewritten into a standalone query. The extra LLM call made
   follow-ups the slowest turns (3.6 s in the UI and 7.7–9.3 s in evaluation run 2 with llama3.3-70b, compared with 2.2 s on llama3.1-8b). Rewrites also
   sometimes pull in earlier topics (e.g. "connection between the lubricant … and the world cup winner"), so the "Clear
   conversation" button and the memory toggle are useful.

5. **The grounding prompt prevents hallucination.** Every model declined out-of-scope questions ("I don't have the
   information") instead of answering from general knowledge.

6. **The source links show over-retrieval.** With passages = 3, the UI lists 3 documents even when only one is relevant.
   This shows what was retrieved, but users may read every link as a citation. Using fewer passages, or showing only sources
   above a score threshold, would make the links more precise.

7. **Category filters improve precision.** With "Search in = Snow", only ski documents were retrieved and shown.
   The automatic Bike/Snow classification was 5/5 correct.

8. **Model trade-off:**
   - `llama3.1-8b` – fastest and most stable (p90 1.7 s), and equally accurate here; a good choice for high-volume or cost-sensitive use.
   - `llama3.3-70b` – concise answers and stronger reasoning, but its latency varied most between runs (p90 2.0 s → 5.9 s).
   - `llama3.1-70b` – gives the most explanatory full-sentence answers, with stable latency of about 2 s.

9. **The event-driven design keeps costs low.** The conditional task skips runs with no changes; Cortex Search refreshes incrementally.

10. **Configuration caused the problems, not code.** The Streamlit version error, the missing PyPI integration, the unavailable
    default model and the missing `core.py` artifact were all platform settings (see `07_challenges`).

11. **Before production:** test on a realistic corpus (hundreds of multi-page manuals), tune chunk size and overlap, persist feedback
    from the Activity tab to a table, and add LLM-judged faithfulness and relevance metrics.
