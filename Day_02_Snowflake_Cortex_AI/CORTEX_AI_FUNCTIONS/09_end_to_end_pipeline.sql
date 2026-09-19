-- =====================================================================
-- 09_end_to_end_pipeline.sql
-- Customer Intelligence pipeline: raw text -> governed, AI-enriched tables
-- Prerequisite: run 01_setup_and_load.sql
--
-- Order matters. Redact before analysis, translate before classification,
-- materialise each stage so you pay for inference once.
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- ---------------------------------------------------------------------
-- Step 0. Size the workload before spending anything
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                            AS rows_to_process,
  SUM(AI_COUNT_TOKENS('ai_complete', review_text))    AS est_input_tokens,
  MAX(AI_COUNT_TOKENS('ai_complete', review_text))    AS largest_row_tokens
FROM customer_reviews;

-- ---------------------------------------------------------------------
-- Step 1. Normalise language (AI_TRANSLATE)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE reviews_normalised AS
SELECT
  review_id,
  product_id,
  review_date,
  rating,
  language,
  review_text                                                            AS original_text,
  IFF(language = 'en', review_text, AI_TRANSLATE(review_text, '', 'en')) AS text_en
FROM customer_reviews;

-- ---------------------------------------------------------------------
-- Step 2. Remove PII before anything is stored for analysis (AI_REDACT)
-- ---------------------------------------------------------------------
ALTER SESSION SET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR = FALSE;

CREATE OR REPLACE TABLE reviews_clean AS
SELECT
  review_id,
  product_id,
  review_date,
  rating,
  language,
  COALESCE(r:value::VARCHAR, text_en) AS text_clean,   -- fall back if redaction fails
  r:error::VARCHAR                    AS redact_error
FROM (
  SELECT review_id, product_id, review_date, rating, language, text_en,
         AI_REDACT(text_en, TRUE) AS r
  FROM reviews_normalised
);

-- ---------------------------------------------------------------------
-- Step 3. Keep only rows worth spending inference on (AI_FILTER)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE reviews_actionable AS
SELECT *
FROM reviews_clean
WHERE AI_FILTER(
        PROMPT('Does this review describe a specific problem that a business could act on, '
               || 'rather than only general praise? Review: {0}', text_clean)
      );

SELECT COUNT(*) AS actionable_rows FROM reviews_actionable;

-- ---------------------------------------------------------------------
-- Step 4. Classify and score (AI_CLASSIFY + AI_SENTIMENT)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE reviews_enriched AS
SELECT
  review_id,
  product_id,
  review_date,
  rating,
  text_clean,
  AI_CLASSIFY(
    text_clean,
    [
      {'label': 'product_defect',  'description': 'item broken, faulty or degraded quickly'},
      {'label': 'shipping_issue',  'description': 'late, damaged, missing or misdelivered'},
      {'label': 'support_failure', 'description': 'slow, unhelpful or refused service'},
      {'label': 'billing_issue',   'description': 'wrong charge, renewal or refund problem'}
    ],
    {'task_description': 'Categorise actionable problems in an e-commerce review.',
     'output_mode': 'multi'}
  ):labels                                     AS issue_labels,
  AI_SENTIMENT(text_clean,
    ['build quality', 'shipping', 'customer support', 'price'])  AS aspect_sentiment
FROM reviews_actionable;

-- ---------------------------------------------------------------------
-- Step 5. Extract structured facts (AI_EXTRACT)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE reviews_facts AS
SELECT
  review_id,
  product_id,
  e:response:failure_mode::VARCHAR   AS failure_mode,
  e:response:time_to_failure::VARCHAR AS time_to_failure,
  e:response:resolution_sought::VARCHAR AS resolution_sought
FROM (
  SELECT review_id, product_id,
         AI_EXTRACT(text_clean, {
           'failure_mode'      : 'What specifically went wrong, in five words or fewer?',
           'time_to_failure'   : 'How long after purchase did it fail? Return null if not stated.',
           'resolution_sought' : 'What does the customer want? Return null if not stated.'
         }) AS e
  FROM reviews_enriched
);

-- ---------------------------------------------------------------------
-- Step 6. Aggregate to an insight layer (AI_AGG)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE product_insights AS
SELECT
  e.product_id,
  p.product_name,
  p.category,
  COUNT(*)                                  AS actionable_reviews,
  ROUND(AVG(e.rating), 2)                   AS avg_rating,
  AI_AGG(
    e.text_clean,
    'Identify the single most important quality or service problem for this product. '
    || 'State it in one sentence, then give one concrete recommended action. '
    || 'Base this only on the reviews provided.'
  )                                         AS recommended_action
FROM reviews_enriched e
JOIN product_catalog  p USING (product_id)
GROUP BY e.product_id, p.product_name, p.category;

SELECT * FROM product_insights ORDER BY avg_rating;

-- ---------------------------------------------------------------------
-- Step 7. Final analytics view for BI
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_customer_intelligence AS
WITH labels AS (
  SELECT review_id, ARRAY_TO_STRING(issue_labels, ', ') AS issues
  FROM reviews_enriched
),
overall AS (
  SELECT
    review_id,
    MAX(IFF(c.value:name::VARCHAR = 'overall', c.value:sentiment::VARCHAR, NULL)) AS overall_sentiment
  FROM reviews_enriched, LATERAL FLATTEN(input => aspect_sentiment:categories) c
  GROUP BY review_id
)
SELECT
  e.review_id,
  e.product_id,
  p.product_name,
  p.category,
  e.review_date,
  e.rating,
  l.issues,
  o.overall_sentiment,
  f.failure_mode,
  f.resolution_sought,
  i.recommended_action
FROM reviews_enriched e
JOIN product_catalog  p USING (product_id)
LEFT JOIN labels          l USING (review_id)
LEFT JOIN overall         o USING (review_id)
LEFT JOIN reviews_facts   f USING (review_id)
LEFT JOIN product_insights i ON i.product_id = e.product_id;

SELECT * FROM v_customer_intelligence ORDER BY review_date, review_id;

ALTER SESSION UNSET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR;

-- ---------------------------------------------------------------------
-- Step 8. What did this cost?
-- ---------------------------------------------------------------------
-- Note: ACCOUNT_USAGE views have latency of up to a few hours.

SELECT
    query_id,
    function_name,
    model_name,
    metrics,
    credits,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE start_time >= DATEADD('hour', -2, CURRENT_TIMESTAMP())
ORDER BY start_time DESC
LIMIT 50;
