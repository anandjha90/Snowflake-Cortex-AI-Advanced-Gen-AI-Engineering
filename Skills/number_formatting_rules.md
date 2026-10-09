---
name: number_formatting
description: Format all numeric values in responses — currency as $K/$M/$B, percentages, tariff rates, counts, deltas, and dates, all to 2 decimal places. Apply to markdown tables, text, chart data labels, axis labels, and tooltips.
---
# Number Formatting Rules
Apply to EVERY numeric value in the response — executive summary, tables, key findings, chart data labels, chart axis labels, and tooltips alike.
## Currency (STRICT)
All monetary values carry a `$` prefix and use abbreviated suffixes:
| Magnitude | Format | Example |
|---|---|---|
| ≥ 1,000,000,000 | `$X.XXB` | `$2.30B` |
| ≥ 1,000,000 | `$X.XXM` | `$1.25M` |
| ≥ 1,000 | `$X.XXK` | `$450.00K`, `$146.32K` |
| < 1,000 | `$X.XX` | `$850.75` |
- ALWAYS exactly 2 decimal places, including with a suffix.
- NEVER show raw unformatted values: `146319.4` → `$146.32K`; `373159.7` → `$373.16K`; `22389.58` → `$22.39K`.
- Negative currency carries the sign before the symbol: `-$12.40K`.
## Percentages
- Exactly 2 decimal places with a `%` sign: `25.50%`, `3.75%`, `100.00%`.
- Preserve the negative sign for decreases: `-12.40%`.
- Never `25.5%` or `0.1538492`.
## Tariff Rates
- Exactly 2 decimal places with `%`: `50.00%`, `15.00%`, `7.50%`.
- A rate stored as a fraction is converted before display: `0.15` → `15.00%`.
- Never display a rate as a bare decimal.
## Deltas and Changes
- Show an explicit sign on any change, difference, or variance: `+5.00%`, `-2.50%`, `+$12.40K`, `-$185.34K`.
- A zero change displays as `0.00%` or `$0.00`, never as blank or a dash.
## Counts and Integers
- No decimal places: `5`, `12`, `1,200`.
- Comma separators for counts ≥ 1,000.
- Counts of HTS codes, parts, documents, records, and rows are always whole numbers.
## Dates
- Readable form: `25 Aug 2026`, never `2026-08-25` or `08/25/26`.
- Month-level periods: `Aug 2026`.
- Timestamps where precision matters: `25 Aug 2026, 14:30`.
## Zero vs Missing (CRITICAL)
- A true zero displays as `$0.00`, `0.00%`, or `0` — a real value.
- A NULL or absent value is NEVER displayed as zero. State that the value is unavailable and name the field.
- In tables, an unavailable value shows as `Not available`, never `0.00`, `-`, or an empty cell.
## Tabular Output
- Present query results as a formatted markdown table.
- Apply the rules above to EVERY numeric cell.
- Right-align numeric columns; left-align text columns.
- Use business column headers: "Annual Spend" not `AI_SPEND`; "Country of Origin" not `COO_CLEAN`; "HTS Code" not `HTS_CODE`.
- Never expose internal or technical column names anywhere in the response.
## CHART RENDERING — MANDATORY
Number formatting must be applied to the actual chart specification and rendered visual, not only to the surrounding response text or markdown table.
For EVERY chart, apply these rules to:
- visible data labels
- axis tick labels
- axis values
- tooltips
- displayed measure values
Never rely on the chart renderer's default numeric formatting.
### Currency Chart Formatting
Currency values must dynamically use the correct scale based on the actual value:
- ≥ 1,000,000,000 → `$X.XXB`
- ≥ 1,000,000 → `$X.XXM`
- ≥ 1,000 → `$X.XXK`
- < 1,000 → `$X.XX`
Examples:
- `466515.95` → `$466.52K`
- `1418572.65` → `$1.42M`
- `470352.49` → `$470.35K`
- `2300000000` → `$2.30B`
- `850.75` → `$850.75`
Never render:
- `466515.95`
- `466515`
- `1.41857265e+06`
- `1.42e+06`
### Data Labels
Every chart data point must have a visible data label.
For currency measures, labels must display the abbreviated currency format:
`$466.52K`
not the raw underlying number:
`466515.95`
Data labels must not depend on hover or tooltip interaction.
### Axis Labels
For currency measures, explicitly format the value axis using the same `$K/$M/$B` convention.
Examples:
`$0.00`, `$100.00K`, `$200.00K`, `$1.00M`, `$2.00M`
Never display scientific notation or raw large numbers.
### Tooltips
Tooltips must use the same numeric formatting rules:
- Currency → `$X.XXK/$X.XXM/$X.XXB`
- Percentage → `X.XX%`
- Counts → whole numbers with comma separators
### Renderer Defaults
Do NOT rely on automatic/default chart formatting.
If the chart specification supports explicit axis, label, or tooltip formatting, configure it explicitly.
The rendered chart must visually reflect the formatting rules in this skill.
### Responsibility Boundary
- `number_formatting` owns numeric representation and formatting.
- `chart_styling` owns labels visibility, gridlines, legends, colors, titles, axes, and visual appearance.
- `chart_types` owns chart type selection.
Do not move chart type or visual styling rules into this skill.
