-- =====================================================================
-- 07_files_and_multimodal.sql
-- TO_FILE, AI_PARSE_DOCUMENT, AI_TRANSCRIBE, AI_SUMMARIZE / AI_CLASSIFY /
-- AI_EXTRACT on files, multimodal AI_COMPLETE
-- Prerequisite: run 01_setup_and_load.sql
-- Upload pdf, images, audio files from sample_files in github
-- These examples need your own files. The CSVs in this bundle are text,
-- so upload a few PDFs, images or audio files to the stage below first.
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- 1. A stage the AI file functions can actually read
-- AI functions do NOT work on: internal stages with TYPE='SNOWFLAKE_FULL',
-- external stages with AWS_CSE or AZURE_CSE, user stages, table stages, or
-- stages with double-quoted names.
-- =====================================================================
CREATE OR REPLACE STAGE media_stage
  DIRECTORY  = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');


SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED FROM DIRECTORY(@media_stage);

-- =====================================================================
-- 2. TO_FILE - turn a staged path into a FILE value
-- =====================================================================
CREATE OR REPLACE TABLE stage_files AS
SELECT
  RELATIVE_PATH                        AS file_path,
  TO_FILE('@media_stage', RELATIVE_PATH) AS f
FROM DIRECTORY(@media_stage);

-- File metadata helpers.
SELECT
  FL_GET_RELATIVE_PATH(f) AS file_name,
  FL_GET_CONTENT_TYPE(f)  AS content_type,
  FL_GET_SIZE(f)          AS size_bytes,
  FL_GET_STAGE(f)         AS stage_name,
  FL_GET_LAST_MODIFIED(f) AS last_modified
FROM stage_files;

-- =====================================================================
-- AI_PARSE_DOCUMENT
-- Signature: AI_PARSE_DOCUMENT( <file> [, <options> ] [, <return_error_details> ] )
-- options: mode ('OCR' default | 'LAYOUT'), page_split, page_filter, extract_images
-- =====================================================================

-- 1. OCR mode - plain text.
SELECT
  file_path,
  PARSE_JSON(TO_VARCHAR(AI_PARSE_DOCUMENT(f))):content::VARCHAR AS text_content
FROM stage_files
WHERE file_path ILIKE '%.pdf';

-- 2. LAYOUT mode - Markdown with tables preserved. Use this when structure matters.
SELECT
  file_path,
  PARSE_JSON(TO_VARCHAR(
    AI_PARSE_DOCUMENT(f, {'mode': 'LAYOUT'})
  )):content::VARCHAR AS markdown_content
FROM stage_files
WHERE file_path ILIKE '%.pdf';

-- 3. page_split - one row per page. Required for long documents that would
--    otherwise exceed the token limit.
SELECT
  file_path,
  p.value:index::NUMBER   AS page_index,
  p.value:content::VARCHAR AS page_content
FROM stage_files,
LATERAL FLATTEN(
  input => PARSE_JSON(TO_VARCHAR(
    AI_PARSE_DOCUMENT(f, {'mode': 'LAYOUT', 'page_split': TRUE})
  )):pages
) p
WHERE file_path ILIKE '%.pdf'
ORDER BY file_path, page_index;

-- 4. page_filter - process only a page range. Indexes start at 0 and 'end' is exclusive.
SELECT
  file_path,
  AI_PARSE_DOCUMENT(f, {'mode': 'LAYOUT',
                        'page_filter': [{'start': 0, 'end': 3}]}) AS first_three_pages
FROM stage_files
WHERE file_path ILIKE '%.pdf';

-- 5. return_error_details TRUE also surfaces metadata such as pageCount.
SELECT
  file_path,
  r:metadata:pageCount::NUMBER AS page_count,
  r:error::VARCHAR             AS error_message
FROM (
  SELECT file_path, AI_PARSE_DOCUMENT(f, {'mode': 'LAYOUT'}, TRUE) AS r
  FROM stage_files
  WHERE file_path ILIKE '%.pdf'
);

-- 6. Full document pipeline: parse, persist, then extract structured fields.
CREATE OR REPLACE TABLE parsed_documents AS
SELECT
  file_path,
  PARSE_JSON(TO_VARCHAR(AI_PARSE_DOCUMENT(f, {'mode': 'LAYOUT'}))):content::VARCHAR AS doc_text
FROM stage_files
WHERE file_path ILIKE '%.pdf';

SELECT
  file_path,
  AI_CLASSIFY(doc_text, ['invoice', 'contract', 'report', 'letter']):labels[0]::VARCHAR AS doc_type,
  AI_EXTRACT(doc_text, {
    'counterparty' : 'Which company or person is the counterparty?',
    'effective_date': 'What is the effective or issue date?',
    'total_amount' : 'What is the total amount, with currency? Return null if none.'
  }):response AS fields
FROM parsed_documents;

-- 7. AI functions that take a FILE directly - no parsing step needed.
SELECT file_path, AI_SUMMARIZE(f) AS summary
FROM stage_files
WHERE file_path ILIKE ANY ('%.pdf', '%.png', '%.jpg');

SELECT file_path,
       AI_EXTRACT(file => f,
                  responseFormat => [['total', 'What is the invoice total?'],
                                     ['due_date', 'What is the payment due date?']],
                  scores => TRUE) AS extraction
FROM stage_files
WHERE file_path ILIKE '%.pdf';

-- =====================================================================
-- AI_TRANSCRIBE
-- Signature: AI_TRANSCRIBE( <audio_file> [, <options> ] [, <return_error_details> ] )
-- options: timestamp_granularity 'word' | 'speaker'
-- Limits: 700 MB; 120 minutes without timestamps, 60 minutes with them.
-- Billing: 50 tokens per audio second, minimum 10 seconds per file.
-- =====================================================================

-- 1. Plain transcript.
SELECT
  file_path,
  PARSE_JSON(TO_VARCHAR(AI_TRANSCRIBE(f))):text::VARCHAR           AS transcript,
  PARSE_JSON(TO_VARCHAR(AI_TRANSCRIBE(f))):audio_duration::FLOAT   AS duration_seconds
FROM stage_files
WHERE file_path ILIKE ANY ('%.mp3', '%.wav', '%.m4a', '%.mp4');

-- 2. Speaker diarisation - who said what, and when.
SELECT
  file_path,
  s.value:speaker_label::VARCHAR AS speaker,
  s.value:start::FLOAT           AS start_sec,
  s.value:end::FLOAT             AS end_sec,
  s.value:text::VARCHAR          AS utterance
FROM stage_files,
LATERAL FLATTEN(
  input => PARSE_JSON(TO_VARCHAR(
    AI_TRANSCRIBE(f, {'timestamp_granularity': 'speaker'})
  )):segments
) s
WHERE file_path ILIKE '%.mp3'
ORDER BY file_path, start_sec;

-- 3. Word-level timestamps - for subtitles or click-to-seek transcripts.
SELECT
  file_path,
  w.value:text::VARCHAR AS word,
  w.value:start::FLOAT  AS start_sec
FROM stage_files,
LATERAL FLATTEN(
  input => PARSE_JSON(TO_VARCHAR(
    AI_TRANSCRIBE(f, {'timestamp_granularity': 'word'})
  )):segments
) w
WHERE file_path ILIKE '%.mp3'
ORDER BY start_sec
LIMIT 50;

-- 4. Transcribe, then chain into other AI functions. This is the standard
--    call-centre pattern: audio in, structured quality scores out.
WITH transcriptions AS (
  SELECT
    file_path,
    TO_VARCHAR(AI_TRANSCRIBE(f)) AS raw,
    PARSE_JSON(TO_VARCHAR(AI_TRANSCRIBE(f))):text::VARCHAR AS transcript
  FROM stage_files
  WHERE file_path ILIKE '%.mp3'
)
SELECT
  file_path,
  AI_SENTIMENT(transcript,
    ['professionalism', 'resolution', 'wait time']) AS call_sentiment,
  AI_CLASSIFY(transcript,
    ['billing', 'technical', 'shipping', 'account']):labels[0]::VARCHAR AS call_topic,
  AI_COMPLETE('claude-sonnet-4-6',
    'In 40 words or fewer, state what the agent should have done differently. '
    || 'If the agent handled it well, say so.\n\n' || transcript) AS coaching_note
FROM transcriptions;

-- =====================================================================
-- Multimodal AI_COMPLETE (image input)
-- Signature: AI_COMPLETE( <model>, <prompt_string>, <file> ) via the single
-- image form, or through a PROMPT() object for multiple files.
-- =====================================================================

-- 1. Describe or assess an image.
SELECT
  file_path,
  AI_COMPLETE('claude-sonnet-4-6',
              'Describe any visible damage to the product in this image. '
              || 'If there is none, say "no visible damage".',
              f) AS damage_assessment
FROM stage_files
WHERE file_path ILIKE ANY ('%.jpg', '%.png');

-- 2. PROMPT() with an image placeholder.
SELECT
  file_path,
  AI_COMPLETE('claude-sonnet-4-6',
    PROMPT('Look at this product photo {0} and write a 25 word catalogue description.', f)
  ) AS catalogue_copy
FROM stage_files
WHERE file_path ILIKE ANY ('%.jpg', '%.png');

-- 3. Classify and filter images directly.
SELECT file_path,
       AI_CLASSIFY(f, ['damaged_product', 'undamaged_product', 'packaging_only', 'document']
       ):labels[0]::VARCHAR AS image_class
FROM stage_files
WHERE file_path ILIKE ANY ('%.jpg', '%.png');

SELECT file_path
FROM stage_files
WHERE file_path ILIKE ANY ('%.jpg', '%.png')
  AND AI_FILTER('Does this image show a damaged or broken item?', f);

-- Note: the AI_COMPLETE single-file page states that audio and video are not supported
-- while the multimodal guide shows audio and video in Public
-- Preview with additional positional arguments. 
-- Requires verification against current Snowflake documentation for your region and release.
