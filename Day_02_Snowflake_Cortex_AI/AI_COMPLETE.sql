CREATE OR REPLACE TABLE customer_feedback_final (
  customer_id STRING, feedback STRING, product STRING, region STRING, created_date DATE);
CREATE OR REPLACE TABLE support_tickets_final (
  ticket_id STRING, customer_id STRING, ticket_text STRING, priority STRING, created_date DATE);
CREATE OR REPLACE TABLE product_reviews_final (
  review_id STRING, product_id STRING, review_text STRING, rating NUMBER(1));
 
INSERT INTO customer_feedback_final VALUES
 ('C-2001', 'The product quality is good, but delivery was extremely late.',
  'Air Fryer X2', 'North', '2026-09-01'),
 ('C-2002', 'Support resolved my issue in minutes. Great service!',
  'Smart Kettle', 'South', '2026-09-02'),
 ('C-2003', 'Received wrong colour. Return process was painless though.',
  'Blender Pro', 'East', '2026-09-03'),
 ('C-2004', 'App keeps crashing when I try to set a timer.',
  'Smart Kettle', 'West', '2026-09-05'),
 ('C-2005', 'Best air fryer I have ever owned. Highly recommend!',
  'Air Fryer X2', 'North', '2026-09-07'),
 ('C-2006', 'Packaging was damaged on arrival but the product was fine.',
  'Blender Pro', 'South', '2026-09-10');

INSERT INTO support_tickets_final VALUES
 ('T-3001', 'C-2001', 'Order delayed by 5 days, no tracking update received.', 'High', '2026-09-02'),
 ('T-3002', 'C-2003', 'Received blue unit instead of red. Need exchange.', 'Medium', '2026-09-04'),
 ('T-3003', 'C-2004', 'App crashes on iOS 19 when setting timer above 30 min.', 'High', '2026-09-06'),
 ('T-3004', 'C-2002', 'Requesting invoice copy for warranty registration.', 'Low', '2026-09-08'),
 ('T-3005', 'C-2006', 'Outer box was crushed during shipping. Photos attached.', 'Medium', '2026-09-11'),
 ('T-3006', 'C-2005', 'How do I descale the air fryer basket?', 'Low', '2026-09-12');

INSERT INTO product_reviews_final VALUES
 ('R-4001', 'P-100', 'Heats up fast and cooks evenly. Love the digital display.', 5),
 ('R-4002', 'P-100', 'Good fryer but the basket coating started peeling after 2 months.', 2),
 ('R-4003', 'P-101', 'Boils water in under a minute. Sleek design.', 4),
 ('R-4004', 'P-101', 'Temperature control is inconsistent. Sometimes overheats.', 2),
 ('R-4005', 'P-102', 'Powerful motor, crushes ice easily. A bit noisy though.', 4),
 ('R-4006', 'P-102', 'Blade rusted after a few washes. Very disappointing.', 1),
 ('R-4007', 'P-100', 'Perfect size for a small kitchen. Easy to clean.', 5),
 ('R-4008', 'P-101', 'Stopped working after one week. Returned immediately.', 1);
 
-- Server-side encrypted internal stages with a directory table
CREATE OR REPLACE STAGE cx_docs
  DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
CREATE OR REPLACE STAGE cx_calls
  DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

SELECT * FROM customer_feedback_final;

SELECT
    ticket_id,
    AI_COMPLETE(
        model            => 'claude-sonnet-4-6',
        prompt           => CONCAT(
            'You are a tier-1 support analyst. Identify the probable root cause, ',
            'the next best action, and a priority (low, medium, high). ',
            '<ticket>', ticket_text, '</ticket>'),
        model_parameters => {'temperature': 0, 'max_tokens': 500},
        response_format  => TYPE OBJECT(root_cause STRING, next_action STRING, ai_priority STRING)
    ) AS triage,
    triage:root_cause::STRING AS root_cause,
    triage:next_action::STRING AS next_action,
    triage:ai_priority::STRING AS ai_priority,
    priority AS original_priority
FROM AI_SOLUTION_DESIGN_LAB.LAB.support_tickets_final
WHERE created_date >= DATEADD('day', -30, CURRENT_DATE())
  AND ticket_text IS NOT NULL;
