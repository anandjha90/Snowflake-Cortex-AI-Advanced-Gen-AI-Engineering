---
name: chart_types
description: Select the appropriate chart type from the user's question and retrieved data. Use bar charts for rankings and categorical comparisons, line charts for time-series trends, pie or donut charts for share/composition, and grouped bars for before-vs-after comparisons. Chart appearance is controlled by chart_styling and numeric formatting by number_formatting.
---
# Chart Type Selection
This skill determines ONLY the chart type and basic data structure.
Do NOT control:
- colors
- gridlines
- data-label appearance
- label positioning
- legends
- chart styling
- currency formatting
- percentage formatting
- decimal formatting
Those responsibilities belong to:
- `chart_styling`
- `number_formatting`
---
# 1. CHART TYPE DECISION
Select the chart type based on the user's analytical intent.
Apply the rules below in priority order.
## RULE 1 — BEFORE / AFTER COMPARISON
Use a **Grouped Bar Chart** when the user asks for:
- before vs after
- old vs new
- previous vs updated
- current vs new
- legacy vs current
- existing vs new
- pre-tariff vs post-tariff
- matched vs unmatched
- two values that must be compared side-by-side
Use no more than 2 series.
---
## RULE 2 — TIME SERIES / TREND
Use a **Line Chart** when the user asks for:
- trend
- over time
- monthly trend
- by month
- month-over-month
- quarterly trend
- by quarter
- year-over-year
- historical trend
- history
- change over time
The X-axis must represent a chronological time dimension.
If fewer than 3 time periods are available, use a Bar Chart instead.
---
## RULE 3 — RANKING / TOP N / BOTTOM N
Use a **Bar Chart** when the user asks for:
- top suppliers
- top countries
- top HTS codes
- highest
- lowest
- largest
- smallest
- ranking
- ranked by
- top N
- bottom N
- most affected
- least affected
- highest tariff impact
- highest spend
- supplier comparison
- country comparison
- product comparison
- HTS comparison
For ranking charts:
- Sort descending for Top N / highest / largest / most affected.
- Sort ascending for Bottom N / lowest / smallest / least affected.
- Prefer horizontal bars when category names are long.
---
## RULE 4 — CATEGORICAL BREAKDOWN
Use a **Bar Chart** when the user asks for a metric:
- by supplier
- by country
- by country of origin
- by product
- by part
- by HTS code
- by tariff category
- by customer
- by business unit
- by region
- by any categorical dimension
Examples:
"Annual tariff impact by supplier"
→ Bar Chart
"Annual spend by country of origin"
→ Bar Chart
"Tariff impact by HTS code"
→ Bar Chart
"Spend by supplier"
→ Bar Chart
Do NOT use a Pie Chart simply because the question contains the word "breakdown".
---
## RULE 5 — SHARE / COMPOSITION / PORTION OF TOTAL
Use a **Pie or Donut Chart** only when the user explicitly asks for:
- share of total
- percentage of total
- proportion
- portion of total
- composition
- contribution to total
- what percentage does each category represent
- how is the total distributed
Use Pie/Donut only when the number of categories is appropriate.
Maximum:
- 8 categories.
If more than 8 categories exist:
- Keep the top 7 categories.
- Group the remainder as "Other".
For share questions, the chart should represent percentages or contribution to total, not merely raw values.
---
# 2. IMPORTANT DISTINCTION: BREAKDOWN VS SHARE
Do NOT confuse these two question types.
### Breakdown
"What is annual tariff impact by supplier?"
→ Bar Chart
The user wants the actual tariff impact for each supplier.
### Share
"What percentage of total annual tariff impact comes from each supplier?"
→ Pie/Donut Chart
The user wants each supplier's contribution to the total.
### Ranking
"Which suppliers have the highest annual tariff impact?"
→ Bar Chart
### Trend
"How has annual tariff impact changed over the last 12 months?"
→ Line Chart
---
# 3. DEFAULT CHART FOR TARIFF ANALYSIS
When the user asks for a tariff metric grouped by a business dimension and does not explicitly request a chart type:
Use a **horizontal Bar Chart**.
Examples:
- Annual tariff impact by supplier → Horizontal Bar
- Annual spend by country → Horizontal Bar
- Tariff impact by HTS code → Horizontal Bar
- Tariff exposure by product → Horizontal Bar
This is preferred because tariff analysis frequently contains long supplier, product, and HTS labels.
---
# 4. BAR CHART STRUCTURE
Use a Bar Chart for categorical rankings and comparisons.
Basic structure:
- Category → categorical dimension
- Value → requested measure
- One series → single metric
Examples:
Supplier + Annual Tariff Impact
Country of Origin + Annual Spend
HTS Code + Annual Tariff Impact
For ranking questions:
- Sort by the requested metric.
- Top N → descending.
- Bottom N → ascending.
---
# 5. GROUPED BAR STRUCTURE
Use Grouped Bar only when the user explicitly compares two related measures or states.
Examples:
Previous Tariff vs Updated Tariff
Existing Tariff Impact vs New Tariff Impact
Legacy Rate vs Current Rate
Matched vs Unmatched
Maximum:
- 2 series.
Do not use grouped bars merely because multiple numeric columns are available.
Only chart the measures relevant to the user's question.
---
# 6. LINE CHART STRUCTURE
Use Line Chart only when the X-axis is temporal.
Examples:
Month → Annual Tariff Impact
Month → Tariff Spend
Quarter → Tariff Exposure
Year → Tariff Impact
Requirements:
- Sort time chronologically ascending.
- Do not sort time-series data by measure.
- Minimum 3 time periods.
If only 1–2 time periods exist, use a Bar Chart.
---
# 7. PIE / DONUT STRUCTURE
Use Pie/Donut only for explicit share or composition questions.
Requirements:
- 2–8 categories.
- Sort slices by share descending.
- Group categories beyond the top 7 into "Other".
- Do not use Pie/Donut for rankings.
- Do not use Pie/Donut for time series.
- Do not use Pie/Donut for before/after comparisons.
---
# 8. SINGLE VALUE
If the query produces only one scalar value:
Do NOT generate a chart.
Examples:
"What is the total annual tariff impact?"
"What is the average tariff rate?"
"How many HTS codes are affected?"
Return the scalar value only, subject to the number_formatting skill.
---
# 9. DATA DENSITY
Before rendering, check the number of categories.
### Bar Chart
- Preferred: 3–20 categories.
- If more than 20 categories:
  - use Top N if appropriate,
  - aggregate where analytically meaningful,
  - or follow the user's requested number.
### Pie / Donut
- 2–8 categories.
- More than 8 → top 7 + Other.
### Line
- Minimum 3 time periods.
### Grouped Bar
- Maximum 2 series.
- Prefer no more than 12 categories.
Do not remove categories merely to make the chart visually convenient when the user explicitly requested all categories.
---
# 10. CHART COUNT
Maximum 2 charts per response.
If multiple charts are possible, select the charts that best answer the user's question.
Do not generate multiple charts showing the same metric and dimension.
---
# 11. NO STYLING OR NUMBER FORMATTING HERE
Do not define:
- colors
- gridlines
- label styles
- label positions
- legend positions
- axis styling
- `$K/$M/$B` formatting
- decimal formatting
- percentage formatting
These are controlled by:
`chart_styling`
and
`number_formatting`.
---
# 12. FINAL DECISION CHECK
Before generating a chart, classify the user's intent:
1. Single value?
   → No chart.
2. Explicit before/after or previous/updated?
   → Grouped Bar.
3. Time-based trend?
   → Line.
4. Explicit share / percentage of total / composition?
   → Pie/Donut.
5. Ranking / Top N / Bottom N / highest / lowest?
   → Bar.
6. Metric "by supplier/country/product/HTS/category"?
   → Bar.
7. Otherwise:
   → Bar as the fallback.
The phrase "breakdown by" alone MUST NOT cause a Pie Chart.
Always prioritize the user's analytical intent over the presence of individual keywords.
