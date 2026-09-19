-- =====================================================================
-- 05_extract_translate_redact.sql
-- AI_EXTRACT, AI_TRANSLATE, AI_REDACT
-- Prerequisite: run 01_setup_and_load.sql
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- AI_EXTRACT
-- Signatures:
--   AI_EXTRACT( <text>, <responseFormat> )
--   AI_EXTRACT( text => <text>, responseFormat => <fmt>, [ scores => TRUE ] )
--   AI_EXTRACT( file => <file>, responseFormat => <fmt>,
--               [ config => <obj> ], [ scores => TRUE ] )
-- Results land under the 'response' key; scores under 'scoring'.
-- =====================================================================

-- 1. Entity extraction, simple object schema (label -> question).
SELECT
  ticket_id,
  AI_EXTRACT(
    ticket_text,
    {
      'order_reference' : 'What order, invoice or PO number is mentioned? Return null if none.',
      'amount'          : 'What monetary amount is in dispute, with currency? Return null if none.',
      'requested_action': 'What does the customer want us to do, in five words or fewer?'
    }
  ):response AS extracted
FROM support_tickets
ORDER BY ticket_id;

-- 2. Same extraction, flattened into typed columns.
WITH x AS (
  SELECT ticket_id,
         AI_EXTRACT(ticket_text, {
           'order_reference' : 'What order, invoice or PO number is mentioned?',
           'amount'          : 'What monetary amount is in dispute, with currency?',
           'requested_action': 'What does the customer want us to do, in five words or fewer?'
         }):response AS r
  FROM support_tickets
)
SELECT
  ticket_id,
  r:order_reference::VARCHAR  AS order_reference,
  r:amount::VARCHAR           AS disputed_amount,
  r:requested_action::VARCHAR AS requested_action
FROM x
ORDER BY ticket_id;

-- 3. Contract term extraction with confidence scores.
SELECT
  contract_id,
  counterparty,
  AI_EXTRACT(
    text => clause_text,
    responseFormat => [
      ['initial_term',     'What is the length of the initial term?'],
      ['notice_period',    'How much notice is required to terminate or stop renewal?'],
      ['liability_cap',    'How is the supplier liability capped?'],
      ['governing_law',    'Which law governs this agreement?'],
      ['auto_renewal',     'Does the agreement renew automatically? Answer yes or no.']
    ],
    scores => TRUE
  ) AS extraction
FROM contracts
ORDER BY contract_id;

-- 4. Route low-confidence extractions to human review.
WITH x AS (
  SELECT contract_id, counterparty,
         AI_EXTRACT(
           text => clause_text,
           responseFormat => [['governing_law', 'Which law governs this agreement?']],
           scores => TRUE
         ) AS e
  FROM contracts
)
SELECT
  contract_id,
  counterparty,
  e:response:governing_law::VARCHAR AS governing_law,
  e:scoring:governing_law::FLOAT    AS confidence,
  IFF(e:scoring:governing_law::FLOAT < 0.8, 'REVIEW', 'AUTO') AS disposition
FROM x
ORDER BY confidence;

-- 5. List extraction - an array of values from one document.
SELECT
  contract_id,
  AI_EXTRACT(
    clause_text,
    {
      'schema': {
        'type': 'object',
        'properties': {
          'obligations': {
            'description': 'What obligations does the processor or supplier have?',
            'type': 'array'
          }
        }
      }
    }
  ):response:obligations AS obligations
FROM contracts
WHERE contract_type = 'DPA';

-- =====================================================================
-- AI_TRANSLATE
-- Signature: AI_TRANSLATE( <text>, <source_language>, <target_language>
--                          [, <return_error_details> ] )
-- Pass '' as the source language to auto-detect. 23 supported languages.
-- =====================================================================

-- 1. Explicit source and target.
SELECT AI_TRANSLATE('The espresso machine arrived with a cracked water tank.', 'en', 'de') AS de;

-- 2. Auto-detect: normalise every non-English review to English.
SELECT
  review_id,
  language                                        AS source_language,
  review_text                                     AS original,
  AI_TRANSLATE(review_text, '', 'en')             AS english_text
FROM customer_reviews
WHERE language <> 'en'
ORDER BY review_id;

-- 3. Normalise first, then analyse - the recommended pipeline order.
WITH normalised AS (
  SELECT
    review_id,
    product_id,
    rating,
    IFF(language = 'en', review_text, AI_TRANSLATE(review_text, '', 'en')) AS text_en
  FROM customer_reviews
)
SELECT
  review_id,
  product_id,
  rating,
  AI_CLASSIFY(text_en,
    ['product_defect', 'shipping_issue', 'support_failure', 'billing_issue', 'praise']
  ):labels[0]::VARCHAR AS issue
FROM normalised
ORDER BY review_id;

-- 4. Outbound: reply to each customer in their own language.
SELECT
  review_id,
  language,
  AI_TRANSLATE(
    AI_COMPLETE('claude-sonnet-4-6',
      'Write a two sentence apology and next step for this customer complaint. '
      || 'Return only the reply text.\n\n' || review_text),
    'en', language
  ) AS localised_reply
FROM customer_reviews
WHERE rating <= 2 AND language <> 'en';

-- 5. Estimate translation cost before running the batch.
SELECT
  SUM(AI_COUNT_TOKENS('ai_translate', review_text, '', 'en')) AS est_input_tokens
FROM customer_reviews
WHERE language <> 'en';

-- =====================================================================
-- AI_REDACT
-- Signature: AI_REDACT( <input> [, <categories> ] [, <return_error_details> ]
--                       [, <mode> ] )
-- Modes: 'redact' (default) and 'detect'.
-- Limits: input + output together up to 4,096 tokens, output up to 1,024.
-- Coverage is US PII plus some UK and Canadian PII. Always review output.
-- =====================================================================

-- 1. Redact everything AI_REDACT supports.
SELECT
  note_id,
  note_text                AS original,
  AI_REDACT(note_text)     AS redacted
FROM customer_notes_pii
ORDER BY note_id;

-- 2. Redact only selected categories.
SELECT
  note_id,
  AI_REDACT(note_text, ['NAME', 'EMAIL', 'PHONE_NUMBER']) AS partially_redacted
FROM customer_notes_pii
ORDER BY note_id;
-- Supported categories: NAME, EMAIL, PHONE_NUMBER, DATE_OF_BIRTH, GENDER, AGE,
-- ADDRESS, NATIONAL_ID, PASSPORT, TAX_IDENTIFIER, PAYMENT_CARD_DATA,
-- DRIVERS_LICENSE, IP_ADDRESS. An unsupported value raises an error.

-- 3. detect mode - locate PII without changing the text.
SELECT
  note_id,
  AI_REDACT(input => note_text, return_error_details => FALSE, mode => 'detect') AS spans
FROM customer_notes_pii
WHERE note_id <= 9003;

-- 4. Flatten detect output into an auditable PII inventory.
SELECT
  n.note_id,
  s.value:category::VARCHAR AS pii_category,
  s.value:text::VARCHAR     AS matched_text,
  s.value:start::NUMBER     AS start_index,
  s.value:end::NUMBER       AS end_index
FROM customer_notes_pii n,
LATERAL FLATTEN(input => AI_REDACT(input => n.note_text, mode => 'detect'):spans) s
ORDER BY n.note_id, start_index;

-- 5. Which PII categories appear most often across the corpus?
SELECT
  s.value:category::VARCHAR AS pii_category,
  COUNT(*)                  AS occurrences
FROM customer_notes_pii n,
LATERAL FLATTEN(input => AI_REDACT(input => n.note_text, mode => 'detect'):spans) s
GROUP BY 1
ORDER BY occurrences DESC;

-- 6. Row-level error handling. AI_REDACT differs from the other functions:
--    it FAILS the whole query by default, so set this session parameter first.
ALTER SESSION SET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR = FALSE;

CREATE OR REPLACE TABLE customer_notes_redacted (note_id NUMBER, value VARCHAR, error VARCHAR);

INSERT INTO customer_notes_redacted
SELECT
  note_id,
  result:value::VARCHAR AS value,
  result:error::VARCHAR AS error
FROM (SELECT note_id, AI_REDACT(note_text, TRUE) AS result FROM customer_notes_pii);

SELECT * FROM customer_notes_redacted ORDER BY note_id;

-- 7. Redact first, then analyse. This is the correct order for PII-bearing text.
SELECT
  note_id,
  value AS redacted_text,
  AI_SENTIMENT(value):categories[0]:sentiment::VARCHAR AS sentiment
FROM customer_notes_redacted
WHERE error IS NULL
ORDER BY note_id;

-- 8. Chunking pattern for text beyond the 4,096 token limit.
WITH chunked AS (
  SELECT
    note_id,
    c.value   AS chunk_text,
    c.index   AS chunk_index
  FROM customer_notes_pii,
  LATERAL FLATTEN(
    input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(note_text, 'none', 1000)
  ) c
),
redacted AS (
  SELECT note_id, chunk_index, chunk_text,
         AI_REDACT(chunk_text, TRUE) AS res
  FROM chunked
)
SELECT
  note_id,
  LISTAGG(IFF(res:error IS NULL, res:value::VARCHAR, chunk_text), '')
    WITHIN GROUP (ORDER BY chunk_index) AS full_redacted_text
FROM redacted
GROUP BY note_id
ORDER BY note_id;

-- Reset the session parameter when you are done.
ALTER SESSION UNSET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR;
