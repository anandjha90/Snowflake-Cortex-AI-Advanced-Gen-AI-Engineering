-- =====================================================================
-- 04_classify_filter_sentiment.sql
-- AI_CLASSIFY, AI_FILTER, AI_SENTIMENT
-- Prerequisite: run 01_setup_and_load.sql
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- AI_CLASSIFY
-- Signature: AI_CLASSIFY( <input>, <list_of_categories>
--                        [, <config_object> ] [, <return_error_details> ] )
-- Returns an OBJECT whose labels field is an array.
-- =====================================================================

-- 1. Simplest form - single label.
SELECT
  ticket_id,
  priority,
  AI_CLASSIFY(ticket_text,
              ['billing', 'technical', 'shipping', 'account', 'product']
  ):labels[0]::VARCHAR AS predicted_category
FROM support_tickets
ORDER BY ticket_id;

-- 2. Compare the model against the human-assigned category.

-- Label-only classification shows ambiguity, resulting in 75% agreement.
SELECT
  ticket_id,
  category                AS human_category,
  predicted_category,
FROM (
  SELECT ticket_id,
         category,
         AI_CLASSIFY(ticket_text,
           ['billing', 'technical', 'shipping', 'account', 'product']
         ):labels[0]::VARCHAR AS predicted_category
  FROM support_tickets
)
ORDER BY ticket_id;

-- Adding label descriptions and a task description resolves the ambiguity, resulting in 100% agreement for this dataset.
SELECT
  ticket_id,
  category AS human_category,
  AI_CLASSIFY(
    ticket_text,
    [
      {'label': 'billing',   'description': 'charges, invoices, refunds, pricing or payment terms'},
      {'label': 'technical', 'description': 'something is broken, erroring or not working as built'},
      {'label': 'shipping',  'description': 'physical delivery of a parcel'},
      {'label': 'account',   'description': 'users, seats, access, permissions or plan changes'},
      {'label': 'product',   'description': 'a request for functionality that does not exist yet'}
    ],
    {'task_description': 'Route an inbound support ticket to the team that owns it.'}
  ):labels[0]::VARCHAR AS predicted_category
FROM support_tickets
ORDER BY ticket_id;

-- 3. Label descriptions, task description and few-shot examples.
-- Enriched classification provides additional context to reduce ambiguity and supports multi-label classification when a review contains multiple issues.
SELECT
  review_id,
  AI_CLASSIFY(
    review_text,
    [
      {'label': 'product_defect',  'description': 'the item arrived broken, faulty or wore out quickly'},
      {'label': 'shipping_issue',  'description': 'late, damaged, missing or wrongly delivered parcel'},
      {'label': 'support_failure', 'description': 'slow, unhelpful or refused customer service'},
      {'label': 'billing_issue',   'description': 'wrong charge, surprise renewal or refund problem'},
      {'label': 'praise',          'description': 'clearly positive feedback with no complaint'}
    ],
    {
      'task_description': 'Categorise the problems raised in an e-commerce product review.',
      'output_mode': 'multi',
      'examples': [
        {
          'input': 'It turned up two weeks late and then the screen was cracked.',
          'labels': ['shipping_issue', 'product_defect'],
          'explanation': 'the review mentions both a late delivery and physical damage'
        }
      ]
    }
  ):labels AS issue_labels
FROM customer_reviews
ORDER BY review_id;

-- 4. Flatten multi-label output into one row per label.
SELECT
  r.review_id,
  r.product_id,
  f.value::VARCHAR AS issue_label
FROM customer_reviews r,
LATERAL FLATTEN(input => AI_CLASSIFY(
    r.review_text,
    ['product_defect', 'shipping_issue', 'support_failure', 'billing_issue', 'praise'],
    {'output_mode': 'multi'}
  ):labels) f
ORDER BY r.review_id;

-- =====================================================================
-- AI_FILTER
-- Signature: AI_FILTER( <input> [, <return_error_details> ] )
--            AI_FILTER( <predicate>, <file> [, ... ] )
--            AI_FILTER( PROMPT('<template>', <col>, ...) [, ... ] )
-- Returns BOOLEAN. Phrase the predicate as a full, specific statement or
-- question, not a fragment.
-- =====================================================================

-- 1. Scalar sanity check.
SELECT AI_FILTER('Is Bengaluru in India?') AS check_1;

-- 2. In a WHERE clause: find reviews that describe a safety or damage risk.
SELECT review_id, product_id, rating, review_text
FROM customer_reviews
WHERE AI_FILTER(
        PROMPT('In the following product review, does the customer describe the item '
               || 'arriving physically damaged or broken? Review: {0}', review_text)
      );

-- 3. As a SELECT expression: three independent flags in one pass.
-- Each AI_FILTER independently evaluates the ticket against a specific condition:
-- refund request, escalation/SLA concern, or feature request.
-- This allows multiple signals to be TRUE for the same ticket.
SELECT
  ticket_id,
  priority,
  AI_FILTER(PROMPT('In this support ticket, is the customer asking for money back '
                   || 'or disputing a charge? Ticket: {0}', ticket_text)) AS is_refund_request,
  AI_FILTER(PROMPT('In this support ticket, does the customer mention an SLA breach, '
                   || 'an outage, or a security or access problem? Ticket: {0}',
                   ticket_text))                                          AS is_escalation,
  AI_FILTER(PROMPT('In this support ticket, is the customer requesting a new feature '
                   || 'rather than reporting a problem? Ticket: {0}', ticket_text)) AS is_feature_request
FROM support_tickets
ORDER BY ticket_id;

-- 4. Semantic JOIN: match each ticket to the product it is most likely about.
--    AI_FILTER in the ON clause evaluates the pair with natural language.
SELECT
  t.ticket_id,
  p.product_id,
  p.product_name
FROM support_tickets t
JOIN product_catalog p
  ON AI_FILTER(
       PROMPT('Could this support ticket plausibly be about this product? '
              || 'Answer TRUE only if the ticket clearly relates to it. '
              || 'Ticket: {0}  Product: {1} - {2}',
              t.ticket_text, p.product_name, p.description)
     )
ORDER BY t.ticket_id;

-- =====================================================================
-- AI_SENTIMENT
-- Signature: AI_SENTIMENT( <text> [, <categories> ] [, <return_error_details> ] )
-- Up to 10 categories, 30 characters each. Always returns an 'overall'
-- record. Values: positive, negative, neutral, mixed, unknown.
-- =====================================================================

-- 1. Overall sentiment only.
SELECT
  review_id,
  rating,
  AI_SENTIMENT(review_text):categories[0]:sentiment::VARCHAR AS overall_sentiment
FROM customer_reviews
ORDER BY review_id;

-- 2. Aspect-based sentiment, then pivoted into columns.
WITH scored AS (
  SELECT
    review_id,
    product_id,
    rating,
    AI_SENTIMENT(
      review_text,
      ['build quality', 'shipping', 'customer support', 'price', 'ease of use']
    ) AS s
  FROM customer_reviews
)
SELECT
  review_id,
  product_id,
  rating,
  MAX(IFF(c.value:name::VARCHAR = 'overall',          c.value:sentiment::VARCHAR, NULL)) AS overall,
  MAX(IFF(c.value:name::VARCHAR = 'build quality',    c.value:sentiment::VARCHAR, NULL)) AS build_quality,
  MAX(IFF(c.value:name::VARCHAR = 'shipping',         c.value:sentiment::VARCHAR, NULL)) AS shipping,
  MAX(IFF(c.value:name::VARCHAR = 'customer support', c.value:sentiment::VARCHAR, NULL)) AS support,
  MAX(IFF(c.value:name::VARCHAR = 'price',            c.value:sentiment::VARCHAR, NULL)) AS price,
  MAX(IFF(c.value:name::VARCHAR = 'ease of use',      c.value:sentiment::VARCHAR, NULL)) AS ease_of_use
FROM scored, LATERAL FLATTEN(input => s:categories) c
GROUP BY review_id, product_id, rating
ORDER BY review_id;

-- 3. Where does each product hurt most? Count negative aspects per product.
WITH scored AS (
  SELECT product_id,
         AI_SENTIMENT(review_text,
           ['build quality', 'shipping', 'customer support', 'price']) AS s
  FROM customer_reviews
)
SELECT
  product_id,
  c.value:name::VARCHAR AS aspect,
  COUNT(*)              AS negative_mentions
FROM scored, LATERAL FLATTEN(input => s:categories) c
WHERE c.value:sentiment::VARCHAR = 'negative'
  AND c.value:name::VARCHAR <> 'overall'
GROUP BY 1, 2
ORDER BY negative_mentions DESC, product_id;

-- 4. Sentiment on call transcripts (text only - tone of voice is not considered).
SELECT
  call_id,
  customer_id,
  AI_SENTIMENT(transcript_text,
    ['professionalism', 'resolution', 'wait time']) AS call_sentiment
FROM call_transcripts
ORDER BY call_id;
