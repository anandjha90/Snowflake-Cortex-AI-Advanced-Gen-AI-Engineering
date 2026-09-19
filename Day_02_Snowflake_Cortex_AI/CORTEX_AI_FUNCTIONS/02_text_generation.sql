-- =====================================================================
-- 02_text_generation.sql
-- AI_COMPLETE, PROMPT, structured output
-- Prerequisite: run 01_setup_and_load.sql
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- AI_COMPLETE - single string form
-- Signature: AI_COMPLETE(<model>, <prompt>)
-- =====================================================================
SELECT AI_COMPLETE(
         'claude-sonnet-4-6',
         'In one sentence, explain what a dual boiler espresso machine is.'
       ) AS answer;

-- Applied to a column: one model call per row.
SELECT
  review_id,
  rating,
  LEFT(review_text, 60) || '...' AS review_snippet,
  AI_COMPLETE(
    'claude-sonnet-4-6',
    'Rewrite this customer review as a single neutral sentence for an internal '
    || 'quality report. Return only the sentence, no preamble.\n\nReview: ' || review_text
  ) AS internal_note
FROM customer_reviews
WHERE review_id <= 5;

-- =====================================================================
-- AI_COMPLETE - named arguments with model parameters
-- =====================================================================
SELECT
  ticket_id,
  priority,
  AI_COMPLETE(
    model  => 'claude-sonnet-4-6',
    prompt => 'Write a two sentence acknowledgement reply to this support ticket. '
           || 'Be specific about what was reported. Do not promise a resolution time.\n\n'
           || ticket_text,
    model_parameters => {'temperature': 0.2, 'max_tokens': 200}
  ) AS draft_reply
FROM support_tickets
WHERE priority IN ('critical', 'high')
ORDER BY ticket_id;

-- =====================================================================
-- PROMPT helper - positional placeholders, keeps text and data separate
-- =====================================================================
SELECT
  product_id,
  AI_COMPLETE(
    'claude-sonnet-4-6',
    PROMPT(
      'Write a 20 word marketing tagline for a product in the {0} category called {1}. '
      || 'Product details: {2}. Return only the tagline.',
      category, product_name, description
    )
  ) AS tagline
FROM product_catalog
WHERE category IN ('audio', 'kitchen');

-- =====================================================================
-- Structured output - JSON schema via response_format
-- =====================================================================
SELECT
  review_id,
  AI_COMPLETE(
    model  => 'claude-sonnet-4-6',
    prompt => 'Extract structured quality data from this customer review:\n\n' || review_text,
    response_format => {
      'type': 'json',
      'schema': {
        'type': 'object',
        'properties': {
          'primary_complaint'  : {'type': 'string'},
          'product_defect'     : {'type': 'boolean'},
          'shipping_problem'   : {'type': 'boolean'},
          'support_problem'    : {'type': 'boolean'},
          'severity'           : {'type': 'string', 'enum': ['none', 'low', 'medium', 'high']}
        },
        'required': ['primary_complaint', 'product_defect', 'shipping_problem',
                     'support_problem', 'severity']
      }
    }
  ) AS structured
FROM customer_reviews
WHERE rating <= 2;

-- Flatten the structured output into typed columns.
WITH scored AS (
  SELECT
    review_id,
    product_id,
    PARSE_JSON(TO_VARCHAR(AI_COMPLETE(
      model  => 'claude-sonnet-4-6',
      prompt => 'Extract structured quality data from this customer review:\n\n' || review_text,
      response_format => {
        'type': 'json',
        'schema': {
          'type': 'object',
          'properties': {
            'primary_complaint': {'type': 'string'},
            'product_defect'   : {'type': 'boolean'},
            'shipping_problem' : {'type': 'boolean'},
            'support_problem'  : {'type': 'boolean'},
            'severity'         : {'type': 'string', 'enum': ['none','low','medium','high']}
          },
          'required': ['primary_complaint','product_defect','shipping_problem',
                       'support_problem','severity']
        }
      }
    ))) AS j
  FROM customer_reviews
  WHERE rating <= 2
)
SELECT
  review_id,
  product_id,
  j:primary_complaint::VARCHAR AS primary_complaint,
  j:product_defect::BOOLEAN    AS product_defect,
  j:shipping_problem::BOOLEAN  AS shipping_problem,
  j:support_problem::BOOLEAN   AS support_problem,
  j:severity::VARCHAR          AS severity
FROM scored
ORDER BY review_id;

-- =====================================================================




