# Sample files for `07_files_and_multimodal.sql`

Eight files that exercise every file-based path in the demo. All content is fabricated and
cross-references the tables from `01_setup_and_load.sql`, so the file results join back to the
review and ticket data.

| File | Type | Size | What it's for | Ties back to |
| --- | --- | --- | --- | --- |
| `invoice_INV-2026-0442.pdf` | PDF, 1 page | 4 KB | `AI_PARSE_DOCUMENT` LAYOUT vs OCR on a real line-item table; `AI_EXTRACT` of invoice fields | Ticket 5006 — the missing PO number |
| `msa_acme_logistics.pdf` | PDF, 2 pages | 5 KB | `page_split`, `page_filter`, table extraction, clause risk review | Contract 8001 in `contracts` |
| `incident_report_INC-2026-0117.pdf` | PDF, 1 page | 4 KB | `AI_SUMMARIZE` on a file; extracting an impact table | Ticket 5008 — the 503 outage |
| `damaged_parcel.jpg` | JPEG, 1100×800 | 96 KB | `AI_CLASSIFY` and `AI_FILTER` on images; multimodal `AI_COMPLETE` damage assessment | Ticket 5009; label reads ORDER 88241 |
| `product_intact.jpg` | JPEG, 1100×800 | 77 KB | Negative case — the filter should *not* return it | Product P-101 |
| `receipt_scan.png` | PNG, 760×1180 | 470 KB | OCR on a rotated, grainy scan | Store 118 |
| `whiteboard_returns_process.png` | PNG, 1200×820 | 436 KB | Image-to-structure: turn a diagram into numbered steps | Returns process |
| `support_call_missing_items.mp3` | MP3, 127s, 16 kHz mono | 990 KB | `AI_TRANSCRIBE` with `timestamp_granularity: 'speaker'` — two distinct voices | Ticket 5009 |
| `voicemail_warranty_complaint.mp3` | MP3, 42s | 325 KB | Single-speaker transcription, then `AI_REDACT` on the result | Review 4, Tom Whitfield |

The audio is espeak-ng synthesis. It sounds synthetic, but the two voices are acoustically
distinct, so diarisation has a genuine signal to separate. Language detection needs speech in the
first five seconds, which both files have.

## Uploading

`PUT` needs SnowSQL or the Snowflake CLI; it does not run in a Snowsight worksheet.

```bash
snowsql -a <account> -u <user> -d CORTEX_DEMO -s DEMO -q "
  CREATE STAGE IF NOT EXISTS media_stage
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');"

cd sample_files
snowsql -a <account> -u <user> -d CORTEX_DEMO -s DEMO -q "
  PUT file://$(pwd)/*.pdf @media_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
  PUT file://$(pwd)/*.jpg @media_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
  PUT file://$(pwd)/*.png @media_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
  PUT file://$(pwd)/*.mp3 @media_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
  ALTER STAGE media_stage REFRESH;"
```

`AUTO_COMPRESS=FALSE` matters — a gzipped PDF is not a PDF as far as the AI functions are
concerned.

No CLI? In Snowsight go to **Data → Databases → CORTEX_DEMO → DEMO → Stages → MEDIA_STAGE** and
use the **+ Files** button, then run `ALTER STAGE media_stage REFRESH;` in a worksheet.

Confirm all eight arrived:

```sql
SELECT RELATIVE_PATH, SIZE FROM DIRECTORY(@media_stage) ORDER BY RELATIVE_PATH;
```

Then run `11_sample_file_queries.sql`, which is written against these exact filenames.

## If your database is named differently

The screenshot you shared used `CORTEX_DB` / `CORTEX_SC` rather than `CORTEX_DEMO` / `DEMO`.
Adjust the `USE DATABASE` and `USE SCHEMA` lines at the top of the SQL file to match.

## What to look for

- **LAYOUT vs OCR** on the invoice. OCR flattens the line-item table into unaligned text; LAYOUT
  returns Markdown with the columns intact. This is the clearest demonstration of why the mode
  matters.
- **The missing PO number.** The invoice says `NOT SUPPLIED` in red. A model that invents a PO
  number here is one you should not trust on your own documents.
- **Confidence scores.** The receipt is deliberately rotated and noisy, so its extraction scores
  should sit lower than the clean invoice's. That gap is what a review threshold keys off.
- **Diarisation quality.** Check whether speaker turns are attributed consistently, and whether
  the model splits the 17 turns cleanly or merges some.
- **Redaction on speech.** The voicemail transcript contains a name, an order reference and a
  phone number spoken as digits. `AI_REDACT` handles written phone formats well; spoken-digit
  numbers are a harder case and worth inspecting.
