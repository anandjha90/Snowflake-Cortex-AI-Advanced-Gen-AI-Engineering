---
name: weekly_business_report
description: >
  Generate a weekly e-commerce business summary report covering key KPIs:
  total revenue, order count, average order value, return rate, refund totals,
  top-selling products, delivery performance, and channel breakdown.
  Use this skill when the user asks for a weekly report, weekly summary,
  business review, or KPI overview for the past week.
---
# Weekly Business Summary Report
## Instructions
When the user requests a weekly business summary, weekly report, or weekly KPI overview, follow these steps:
### Step 1: Determine the reporting week
- If the user specifies a date range, use it.
- Otherwise, default to the last complete 7-day period ending yesterday.
- Confirm the date range with the user before proceeding.
### Step 2: Retrieve KPI data
Use the ECOM_CORTEX_ANALYST tool to query each of the following metrics for the reporting period:
1. **Revenue & Orders**: Total sales revenue, total order count, and average order value.
2. **Order Status Breakdown**: Count of orders by status (Delivered, Shipped, Pending, Cancelled, Returned).
3. **Top 5 Products**: By revenue.
4. **Top 5 Categories**: By revenue.
5. **Channel Performance**: Revenue and order count by sales channel (Online, Retail, Marketplace), including commission rates.
6. **Return Metrics**: Total returns, return rate (returns / orders), total refund amount, top 3 return reasons.
7. **Delivery Performance**: Average delivery days, percentage of orders delivered within 3 days.
8. **Geographic Highlights**: Top 5 states by revenue.
### Step 3: Compute week-over-week changes
Query the same metrics for the prior week and calculate percentage changes for:
- Total revenue
- Total orders
- Average order value
- Return rate
### Step 4: Generate the report
Use the code_execution tool to compile the data into a well-formatted summary report with:
- **Header**: "Weekly Business Summary — [Start Date] to [End Date]"
- **Executive Summary**: 2-3 sentence overview highlighting the most notable changes.
- **KPI Dashboard**: A table with current week values, prior week values, and % change (with directional arrows ▲/▼).
- **Top Products & Categories**: Ranked tables.
- **Channel Breakdown**: Table with revenue, orders, and commission cost per channel.
- **Returns & Refunds**: Summary with top reasons.
- **Delivery Performance**: Average days and on-time rate.
- **Geographic Highlights**: Top states table.
### Formatting guidelines
- Use clean markdown tables.
- Include currency formatting ($X,XXX) and percentage formatting (X.X%).
- Highlight positive trends in the executive summary.
- Flag any concerning metrics (e.g., return rate above 10%, delivery average above 5 days).