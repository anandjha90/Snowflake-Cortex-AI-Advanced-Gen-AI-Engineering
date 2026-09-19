-- =====================================================================
-- 08_custom_ai_functions.sql
-- Custom AI Functions: hand-authored SQL UDFs over AI_COMPLETE
-- Prerequisite: run 01_setup_and_load.sql
--
-- Snowflake also offers Cortex AI Function Studio (Public Preview), which
-- creates, evaluates, optimizes and deploys custom AI functions for you and
-- registers them as tagged SQL UDFs. The CREATE_AI_FUNCTION procedure
-- signature appears only in a documentation screenshot and so is marked
-- "Requires verification against current Snowflake documentation". The UDFs
-- below are the hand-written equivalent and run on any account today.
-- =====================================================================
USE DATABASE CORTEX_DB;
USE SCHEMA CORTEX_SC;

-- =====================================================================
-- 1. Ticket triage - one call returns category, severity, team and SLA risk
-- =====================================================================
CREATE OR REPLACE FUNCTION triage_ticket(ticket_text VARCHAR)
RETURNS VARIANT
AS
$$
  AI_COMPLETE(
    model  => 'claude-sonnet-4-6',
    prompt => 'You are a support triage system for a consumer hardware and software '
           || 'company. Classify the ticket below.\n\nTicket: ' || ticket_text,
    model_parameters => {'temperature': 0},
    response_format => {
      'type': 'json',
      'schema': {
        'type': 'object',
        'properties': {
          'category'    : {'type': 'string',
                           'enum': ['billing', 'technical', 'shipping', 'account', 'product']},
          'severity'    : {'type': 'string', 'enum': ['low', 'medium', 'high', 'critical']},
          'owning_team' : {'type': 'string',
                           'enum': ['finance', 'engineering', 'logistics', 'security', 'product']},
          'sla_risk'    : {'type': 'boolean'},
          'one_line'    : {'type': 'string'}
        },
        'required': ['category', 'severity', 'owning_team', 'sla_risk', 'one_line']
      }
    }
  )
$$;

-- Use it like any other SQL function.
SELECT
  ticket_id,
  priority AS human_priority,
  triage_ticket(ticket_text) AS triage
FROM support_tickets
ORDER BY ticket_id;

-- Flattened into columns.
SELECT
  ticket_id,
  t:category::VARCHAR    AS category,
  t:severity::VARCHAR    AS severity,
  t:owning_team::VARCHAR AS owning_team,
  t:sla_risk::BOOLEAN    AS sla_risk,
  t:one_line::VARCHAR    AS summary
FROM (SELECT ticket_id, triage_ticket(ticket_text) AS t FROM support_tickets)
ORDER BY severity DESC, ticket_id;

-- =====================================================================
-- 2. Review scorer - domain-specific rubric encoded once, reused everywhere
-- =====================================================================
CREATE OR REPLACE FUNCTION score_review(review_text VARCHAR)
RETURNS VARIANT
AS
$$
  AI_COMPLETE(
    model  => 'claude-sonnet-4-6',
    prompt => 'Score this product review against our quality rubric. '
           || 'defect_severity: 0 if no defect is described, 1 cosmetic, '
           || '2 functional but usable, 3 unusable or unsafe. '
           || 'churn_risk is TRUE only if the customer says or implies they will '
           || 'not buy from us again.\n\nReview: ' || review_text,
    model_parameters => {'temperature': 0},
    response_format => {
      'type': 'json',
      'schema': {
        'type': 'object',
        'properties': {
          'defect_severity'  : {'type': 'number'},
          'churn_risk'       : {'type': 'boolean'},
          'mentions_support' : {'type': 'boolean'},
          'headline'         : {'type': 'string'}
        },
        'required': ['defect_severity', 'churn_risk', 'mentions_support', 'headline']
      }
    }
  )
$$;

SELECT
  review_id,
  product_id,
  rating,
  s:defect_severity::NUMBER  AS defect_severity,
  s:churn_risk::BOOLEAN      AS churn_risk,
  s:headline::VARCHAR        AS headline
FROM (SELECT review_id, product_id, rating, score_review(review_text) AS s
      FROM customer_reviews)
WHERE defect_severity >= 2 OR churn_risk
ORDER BY defect_severity DESC, review_id;

-- =====================================================================
-- 3. Contract risk reviewer - a named function the legal team can call
-- =====================================================================
CREATE OR REPLACE FUNCTION review_clause(clause_text VARCHAR, our_position VARCHAR)
RETURNS VARIANT
AS
$$
  AI_COMPLETE(
    model  => 'claude-sonnet-4-6',
    prompt => 'You are reviewing a contract clause on behalf of ' || our_position
           || '. Identify the commercial risk. Do not give legal advice; describe '
           || 'what the clause says and what it exposes us to.\n\nClause: ' || clause_text,
    model_parameters => {'temperature': 0},
    response_format => {
      'type': 'json',
      'schema': {
        'type': 'object',
        'properties': {
          'risk_level'      : {'type': 'string', 'enum': ['low', 'medium', 'high']},
          'key_obligation'  : {'type': 'string'},
          'negotiation_note': {'type': 'string'}
        },
        'required': ['risk_level', 'key_obligation', 'negotiation_note']
      }
    }
  )
$$;

SELECT
  contract_id,
  counterparty,
  contract_type,
  r:risk_level::VARCHAR       AS risk_level,
  r:key_obligation::VARCHAR   AS key_obligation,
  r:negotiation_note::VARCHAR AS negotiation_note
FROM (SELECT contract_id, counterparty, contract_type,
             review_clause(clause_text, 'the customer') AS r
      FROM contracts)
ORDER BY CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;

-- =====================================================================
-- 4. A scalar-returning UDF, for use in WHERE clauses and joins
-- =====================================================================
CREATE OR REPLACE FUNCTION is_urgent(ticket_text VARCHAR)
RETURNS BOOLEAN
AS
$$
  AI_FILTER(
    PROMPT('Does this support ticket describe an active outage, a security incident, '
           || 'or an imminent contractual deadline? Ticket: {0}', ticket_text)
  )
$$;

SELECT ticket_id, priority, LEFT(ticket_text, 70) || '...' AS snippet
FROM support_tickets
WHERE is_urgent(ticket_text);

-- =====================================================================
-- 5. Governance: grant, tag and monitor your custom functions
-- =====================================================================
-- GRANT USAGE ON FUNCTION triage_ticket(VARCHAR) TO ROLE support_analyst;
-- GRANT USAGE ON FUNCTION review_clause(VARCHAR, VARCHAR) TO ROLE legal_analyst;

SHOW USER FUNCTIONS IN SCHEMA CORTEX_DB.CORTEX_SC;

-- Spend attributable to AI functions (requires access to the SNOWFLAKE database).
-- Inspect the view first - column names differ between the usage views and
-- between releases.
DESC VIEW SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY;

SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY start_time DESC
LIMIT 50;

-- Per-query token totals, including for your UDF calls:
SELECT
  u.function_name,
  u.model_name,
  COUNT(*)              AS calls,
  SUM(u.token_credits)  AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_QUERY_USAGE_HISTORY u
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q
  ON u.query_id = q.query_id
WHERE q.start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY credits DESC;
