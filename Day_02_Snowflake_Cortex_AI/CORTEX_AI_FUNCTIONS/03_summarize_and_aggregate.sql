-- =====================================================================
-- 03_summarize_and_aggregate.sql
-- AI_SUMMARIZE (Preview), AI_SUMMARIZE_AGG, AI_AGG
-- Prerequisite: run 01_setup_and_load.sql
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- AI_SUMMARIZE - one row in, one summary out
-- Signature: AI_SUMMARIZE( <text> [, return_error_details => TRUE|FALSE ] )
-- Note: returns the input unchanged when the input is 110 characters or
-- fewer. All tokens processed are still billed.
-- =====================================================================
SELECT
  call_id,
  duration_seconds,
  AI_SUMMARIZE(transcript_text) AS call_summary
FROM call_transcripts
ORDER BY call_id;

-- Summarise a long contract clause.
SELECT
  contract_id,
  counterparty,
  contract_type,
  AI_SUMMARIZE(clause_text) AS clause_summary
FROM contracts
WHERE contract_type = 'MSA';

-- With row-level error reporting.
SELECT
  contract_id,
  AI_SUMMARIZE(clause_text, return_error_details => TRUE) AS result
FROM contracts
WHERE contract_id <= 8003;

-- =====================================================================
-- AI_SUMMARIZE_AGG - aggregate across rows, generic summary
-- Signature: AI_SUMMARIZE_AGG( <expr> )
-- Use this INSTEAD of LISTAGG + AI_SUMMARIZE. It handles datasets larger
-- than the model context window.
-- =====================================================================
SELECT
  product_id,
  COUNT(*)                          AS review_count,
  ROUND(AVG(rating), 2)             AS avg_rating,
  AI_SUMMARIZE_AGG(review_text)     AS what_customers_say
FROM customer_reviews
GROUP BY product_id
ORDER BY avg_rating;

-- =====================================================================
-- AI_AGG - aggregate across rows with YOUR instruction
-- Signature: AI_AGG( <expr>, <instruction> )
-- Choose AI_AGG over AI_SUMMARIZE_AGG when you need a specific answer
-- rather than a generic summary.
-- =====================================================================
SELECT
  product_id,
  AI_AGG(
    review_text,
    'List the top three recurring product defects mentioned across these reviews. '
    || 'Return them as a numbered list of short phrases, no commentary.'
  ) AS top_defects
FROM customer_reviews
GROUP BY product_id
ORDER BY product_id;

-- Per-category executive view, joining catalog metadata.
SELECT
  p.category,
  COUNT(*) AS reviews,
  AI_AGG(
    r.review_text,
    'You are writing for a weekly quality meeting. In at most 60 words, state the single '
    || 'biggest theme in these reviews and whether it is a product, shipping or support issue.'
  ) AS category_readout
FROM customer_reviews r
JOIN product_catalog  p USING (product_id)
GROUP BY p.category
ORDER BY reviews DESC;

-- Support view: what is driving critical and high priority tickets.
SELECT
  category,
  COUNT(*) AS ticket_count,
  AI_AGG(
    ticket_text,
    'Summarise the common root cause behind these tickets in two sentences, '
    || 'then name the team that should own the fix.'
  ) AS root_cause_readout
FROM support_tickets
WHERE priority IN ('critical', 'high')
GROUP BY category;

-- Whole-table summary (no GROUP BY) - single narrative for the period.
SELECT AI_AGG(
         review_text,
         'Write a five bullet executive summary of customer feedback for this period. '
         || 'Quantify where possible. Do not invent numbers that are not supported by the text.'
       ) AS period_summary
FROM customer_reviews;
