-- =====================================================================
-- 06_embeddings_and_similarity.sql
-- AI_EMBED, AI_SIMILARITY, AI_MULTI_EMBED, vector search
-- Prerequisite: run 01_setup_and_load.sql
-- Privilege: SNOWFLAKE.CORTEX_EMBED_USER
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- AI_EMBED
-- Signature: AI_EMBED( <model>, <input> )
-- Text models include snowflake-arctic-embed-l-v2.0 (1024 dims),
-- snowflake-arctic-embed-l-v2.0-8k, nv-embed-qa-4, multilingual-e5-large,
-- voyage-multilingual-2. voyage-multimodal-3 also accepts images.
-- Check regional availability for the model you pick.
-- =====================================================================

-- 1. One embedding.
SELECT AI_EMBED('snowflake-arctic-embed-l-v2.0', 'standing desk wobbles at full height') AS v;

-- 2. Materialise embeddings once. Never re-embed a static corpus per query.
CREATE OR REPLACE TABLE review_embeddings AS
SELECT
  review_id,
  product_id,
  rating,
  review_text,
  AI_EMBED('snowflake-arctic-embed-l-v2.0', review_text) AS embedding
FROM customer_reviews;

SELECT review_id, product_id, ARRAY_SIZE(embedding::ARRAY) AS dimensions
FROM review_embeddings
LIMIT 3;

-- 3. Semantic search: embed the query with the SAME model, then rank.
SET search_query = 'the item was physically broken when it arrived';

SELECT
  review_id,
  product_id,
  rating,
  LEFT(review_text, 90) || '...' AS snippet,
  ROUND(VECTOR_COSINE_SIMILARITY(
    embedding,
    AI_EMBED('snowflake-arctic-embed-l-v2.0', $search_query)
  ), 4) AS similarity
FROM review_embeddings
ORDER BY similarity DESC
LIMIT 5;

-- 4. Nearest-neighbour search against the product catalogue.
CREATE OR REPLACE TABLE product_embeddings AS
SELECT
  product_id,
  product_name,
  category,
  AI_EMBED('snowflake-arctic-embed-l-v2.0', product_name || '. ' || description) AS embedding
FROM product_catalog;

-- Match each support ticket to the three most semantically similar products.
WITH t AS (
  SELECT ticket_id, ticket_text,
         AI_EMBED('snowflake-arctic-embed-l-v2.0', ticket_text) AS embedding
  FROM support_tickets
)
SELECT
  ticket_id,
  product_id,
  product_name,
  ROUND(VECTOR_COSINE_SIMILARITY(t.embedding, p.embedding), 4) AS similarity
FROM t
CROSS JOIN product_embeddings p
QUALIFY ROW_NUMBER() OVER (PARTITION BY ticket_id ORDER BY similarity DESC) <= 3
ORDER BY ticket_id, similarity DESC;

-- 5. Near-duplicate detection inside one table.
SELECT
  a.review_id AS review_a,
  b.review_id AS review_b,
  ROUND(VECTOR_COSINE_SIMILARITY(a.embedding, b.embedding), 4) AS similarity
FROM review_embeddings a
JOIN review_embeddings b
  ON a.review_id < b.review_id
--WHERE VECTOR_COSINE_SIMILARITY(a.embedding, b.embedding) > 0.60
ORDER BY similarity DESC
LIMIT 20;

-- 6. Cluster-style grouping: which reviews sit closest to a theme sentence?
WITH themes AS (
            SELECT 'delivery and logistics problems'      AS theme
  UNION ALL SELECT 'hardware build quality and defects'
  UNION ALL SELECT 'billing, pricing and subscriptions'
  UNION ALL SELECT 'positive experience, would recommend'
),
theme_vec AS (
  SELECT theme, AI_EMBED('snowflake-arctic-embed-l-v2.0', theme) AS embedding FROM themes
)
SELECT
  r.review_id,
  t.theme                                                        AS closest_theme,
  ROUND(VECTOR_COSINE_SIMILARITY(r.embedding, t.embedding), 4)   AS similarity
FROM review_embeddings r
CROSS JOIN theme_vec t
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.review_id ORDER BY similarity DESC) = 1
ORDER BY closest_theme, similarity DESC;

-- 7. Token estimate for an embedding batch.
SELECT
  SUM(AI_COUNT_TOKENS('ai_embed', 'snowflake-arctic-embed-l-v2.0', review_text)) AS est_tokens
FROM customer_reviews;

-- =====================================================================
-- AI_SIMILARITY
-- Signature: AI_SIMILARITY( <input1>, <input2> [, <config_object> ] )
-- Convenient for ad-hoc pairs. It embeds BOTH sides on every call, so for
-- repeated search use AI_EMBED + VECTOR_COSINE_SIMILARITY instead.
-- Billed under AI_EMBED.
-- =====================================================================

SELECT AI_SIMILARITY(
  'The parcel arrived empty and the seal was cut.',
  'The box was delivered with nothing inside, tape had been opened.'
) AS score_similar;

SELECT AI_SIMILARITY(
  'The parcel arrived empty and the seal was cut.',
  'Battery life is excellent, easily two full working days.'
) AS score_unrelated;

-- With an explicit model.
SELECT AI_SIMILARITY(
  'standing desk wobbles at full height',
  'the desk is unstable when raised',
  {'model': 'snowflake-arctic-embed-l-v2.0'}
) AS score;

-- Pairwise comparison across two small tables.
SELECT
  t.ticket_id,
  p.product_id,
  ROUND(AI_SIMILARITY(t.ticket_text, p.description), 4) AS score
FROM support_tickets t
CROSS JOIN product_catalog p
WHERE t.ticket_id IN (5002, 5005)
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.ticket_id ORDER BY score DESC) <= 3
ORDER BY t.ticket_id, score DESC;

-- Token estimate for a similarity call.
SELECT AI_COUNT_TOKENS('ai_similarity',
  'standing desk wobbles at full height',
  'the desk is unstable when raised') AS est_tokens;

-- =====================================================================
-- AI_MULTI_EMBED (video, audio, image, text)
-- Signature: AI_MULTI_EMBED( <model>, <input> [, <options> ] )
-- Model: twelvelabs-marengo-embed-3-0. Documented for AWS US East 1 only;
-- confirm availability in your region before relying on it.
-- Returns an OBJECT of segment vectors, so FLATTEN and cast to VECTOR.
-- =====================================================================

-- Requires media files on an SSE-encrypted stage - see 07_files_and_multimodal.sql.

CREATE OR REPLACE TABLE media_embeddings AS
SELECT
  RELATIVE_PATH                                AS file_path,
  seg.index                                    AS segment_index,
  seg.value:embedding_option::VARCHAR          AS modality,
  seg.value:start_sec::FLOAT                   AS start_sec,
  seg.value:end_sec::FLOAT                     AS end_sec,
  seg.value:embedding::VECTOR(FLOAT, 512)      AS embedding
FROM DIRECTORY(@media_stage),
LATERAL FLATTEN(
  input => AI_MULTI_EMBED('twelvelabs-marengo-embed-3-0',
                          TO_FILE('@media_stage', RELATIVE_PATH)):value
) seg
WHERE RELATIVE_PATH ILIKE ANY ('%.mp3', '%.jpg', '%.png');

SELECT file_path, segment_index, modality, start_sec, end_sec FROM media_embeddings
ORDER BY file_path, segment_index;

-- Cross-modal search: find video segments matching a text description.
SELECT file_path, segment_index, modality, start_sec, end_sec,
       ROUND(VECTOR_COSINE_SIMILARITY(
         embedding,
         AI_MULTI_EMBED('twelvelabs-marengo-embed-3-0',
                        'a customer reporting a parcel arrived empty'
         ):value[0]:embedding::VECTOR(FLOAT, 512)
       ), 4) AS similarity
FROM media_embeddings
ORDER BY similarity DESC
LIMIT 10;

