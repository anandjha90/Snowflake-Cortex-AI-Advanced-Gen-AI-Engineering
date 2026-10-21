import json
import re
import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

# ============================================================
# Employee Leave Chatbot - Snowflake Streamlit
# Database: RAG_PROJECT_DB | Schema: DOCUMENTS
# Tables: EMPLOYEES, LEAVE_REQUESTS
# Cortex Search service: LEAVE_POLICY_SEARCH
# ============================================================

st.set_page_config(page_title="Employee Leave Chatbot", page_icon="📅", layout="wide")

DB = "RAG_PROJECT_DB"
SCHEMA = "DOCUMENTS"
EMPLOYEES_TABLE = f"{DB}.{SCHEMA}.EMPLOYEES"
LEAVES_TABLE = f"{DB}.{SCHEMA}.LEAVE_REQUESTS"
SEARCH_SERVICE = f"{DB}.{SCHEMA}.LEAVE_POLICY_SEARCH"
COMPANY_EMAIL_DOMAIN = "@abc.com"  # Change to your approved company domain.
DEFAULT_ENTITLEMENT = 24
# Three selectable Snowflake Cortex model options. Availability can vary by region/account.
# Avoid mistral-large2: Snowflake may reject it as legacy in some accounts.
# Availability varies by Snowflake region/account; policy generation tries fallbacks.
CORTEX_MODELS = ["llama3.1-8b", "llama3.3-70b", "openai-gpt-5-mini"]

session = get_active_session()


def sql_string(value: str) -> str:
    """Escape a value for a SQL string literal."""
    return str(value).replace("'", "''")


def run_query(query: str) -> pd.DataFrame:
    return session.sql(query).to_pandas()


def get_employee_by_email(email: str):
    email_sql = sql_string(email.strip().lower())
    df = run_query(f"""
        SELECT EMPLOYEE_ID, EMPLOYEE_NAME, EMAIL, DATE_OF_BIRTH,
               JOINING_DATE, MANAGER_ID, MANAGER_NAME, DEPARTMENT
        FROM {EMPLOYEES_TABLE}
        WHERE LOWER(EMAIL) = '{email_sql}'
        LIMIT 1
    """)
    return None if df.empty else df.iloc[0].to_dict()


def get_leave_summary(employee_id: str) -> pd.DataFrame:
    employee_id_sql = sql_string(employee_id)
    return run_query(f"""
        SELECT UPPER(STATUS) AS STATUS,
               COUNT(*) AS REQUEST_COUNT,
               COALESCE(SUM(DAYS), 0) AS TOTAL_DAYS
        FROM {LEAVES_TABLE}
        WHERE EMPLOYEE_ID = '{employee_id_sql}'
        GROUP BY UPPER(STATUS)
    """)


def get_leave_requests(employee_id: str) -> pd.DataFrame:
    employee_id_sql = sql_string(employee_id)
    return run_query(f"""
        SELECT REQUEST_ID, LEAVE_TYPE, START_DATE, END_DATE, DAYS,
               UPPER(STATUS) AS STATUS, REASON
        FROM {LEAVES_TABLE}
        WHERE EMPLOYEE_ID = '{employee_id_sql}'
        ORDER BY START_DATE DESC
    """)


def status_days(summary: pd.DataFrame, status: str) -> float:
    if summary.empty or "STATUS" not in summary.columns:
        return 0.0
    rows = summary[summary["STATUS"].astype(str).str.upper() == status.upper()]
    if rows.empty:
        return 0.0
    return float(pd.to_numeric(rows["TOTAL_DAYS"], errors="coerce").fillna(0).sum())


def detect_intent(question: str) -> str:
    q = question.lower().strip()
    q = re.sub(r"[^a-z0-9\s@.-]", " ", q)
    q = re.sub(r"\s+", " ", q)

    # Reject non-leave topics before matching general terms.
    off_topic_terms = [
        "salary", "pay slip", "payslip", "payroll", "compensation", "bonus",
        "health benefit", "health benefits", "medical insurance", "insurance coverage",
        "insurance benefits", "performance review", "promotion", "reimbursement",
        "tax deduction", "taxes", "loan", "company policy outside leave"
    ]
    if any(term in q for term in off_topic_terms):
        return "OFF_TOPIC"

    if q in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]:
        return "GREETING"

    # Summary is shown only when explicitly requested.
    if any(term in q for term in [
        "summary of leave", "leave summary", "summarize my leave", "summary of my leave",
        "give me a summary", "show my leave summary", "summary of leave details",
        "overview of my leave", "summarise my leave"
    ]):
        return "SUMMARY"

    # Leave request eligibility, including questions such as "Can I take 22 days?"
    if any(term in q for term in [
        "can i take", "can i apply", "can i request", "am i eligible", "eligibility",
        "eligible to take", "planned leave", "days off", "would i be able to take",
        "can i go on leave", "request for", "apply for leave"
    ]):
        return "ELIGIBILITY"

    if any(term in q for term in [
        "available", "remaining balance", "leave balance", "leaves left", "leave left",
        "balance left", "remaining leave", "how many left", "how much leave do i have"
    ]):
        return "AVAILABLE"

    if any(term in q for term in ["pending", "awaiting approval", "waiting for approval"]):
        return "PENDING"

    if any(term in q for term in ["rejected", "declined"]):
        return "REJECTED"

    if any(term in q for term in [
        "request history", "leave requests", "show my requests", "list my leaves",
        "which dates", "what dates", "when did i", "start date", "end date",
        "reason for leave", "request id", "my leave history", "show my leave applications"
    ]):
        return "REQUESTS"

    if any(term in q for term in [
        "how many leaves have i taken", "how many days have i taken", "how many leave days have i taken",
        "how many leaves did i take", "how many days did i take", "how many leave days are approved",
        "how many approved leaves", "how many days are approved", "how many days have been approved",
        "how much leave have i used", "how many leaves have i used", "how many days have i used"
    ]):
        return "COUNTED"

    if any(term in q for term in [
        "who am i", "my profile", "my details", "my manager", "my department",
        "my joining date", "my email", "my name"
    ]):
        return "PROFILE"

    # Public-holiday list requests should be answered directly in chat.
    if any(term in q for term in [
        "public holiday", "public holidays", "holiday list", "holidays list",
        "list of holidays", "list all holidays", "all holidays",
        "company holidays", "holiday calendar", "list holidays"
    ]):
        return "HOLIDAYS"

    if any(term in q for term in [
        "policy", "carry forward", "carryover", "sick leave", "casual leave",
        "annual leave", "maternity", "paternity", "holiday", "weekend",
        "document", "proof", "rules", "leave process", "leave approval"
    ]):
        return "POLICY"

    # Explicit leave vocabulary that did not match another intent.
    if any(term in q for term in ["leave", "vacation", "pto", "time off", "day off"]):
        return "HELP"
    return "OFF_TOPIC"


def requested_days(question: str):
    """Extract a day count from common natural-language leave requests."""
    q = question.lower()
    patterns = [
        r"\b(?:take|apply for|request|need|want|book)\s+(\d+(?:\.\d+)?)\s*(?:days?|working days?)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:days?|working days?)\s+(?:of leave|leave|off)\b",
        r"\bcan i\s+(?:take|apply for|request)\s+(\d+(?:\.\d+)?)\b"
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


def get_search_column():
    try:
        services = session.sql(f"SHOW CORTEX SEARCH SERVICES IN SCHEMA {DB}.{SCHEMA}").collect()
        for row in services:
            info = {str(k).lower(): v for k, v in row.as_dict().items()}
            if str(info.get("name", "")).upper() == "LEAVE_POLICY_SEARCH":
                col = info.get("search_column")
                if col:
                    return str(col)
    except Exception:
        pass
    return None


def retrieve_policy(question: str) -> str:
    """Retrieve policy passages through Cortex Search; return evidence for the LLM."""
    search_col = get_search_column()
    payload = {"query": question, "limit": 5}
    if search_col:
        payload["columns"] = [search_col]
    payload_sql = sql_string(json.dumps(payload))
    service_sql = sql_string(SEARCH_SERVICE)
    result = session.sql(f"""
        SELECT PARSE_JSON(
            SNOWFLAKE.CORTEX.SEARCH_PREVIEW('{service_sql}', '{payload_sql}')
        ) AS SEARCH_RESULT
    """).collect()
    if not result or result[0]["SEARCH_RESULT"] is None:
        return "No relevant leave-policy passage was found."
    raw = result[0]["SEARCH_RESULT"]
    parsed = raw if isinstance(raw, (dict, list)) else json.loads(str(raw))
    items = parsed.get("results", []) if isinstance(parsed, dict) else parsed
    passages = []
    for item in items[:5]:
        if isinstance(item, dict):
            vals = [f"{k}: {v}" for k, v in item.items() if v is not None and str(v).strip()]
            if vals:
                passages.append(" | ".join(vals))
    return "\n\n".join(passages) if passages else "No relevant leave-policy passage was found."


def generate_with_cortex(question: str, context: str, model_name: str) -> str:
    """Generate a concise answer grounded in retrieved leave-policy text."""
    is_holiday_list = any(term in question.lower() for term in [
        "public holiday", "public holidays", "holiday list", "holidays list",
        "list of holidays", "list all holidays", "all holidays",
        "company holidays", "holiday calendar", "list holidays"
    ])
    holiday_instruction = ""
    if is_holiday_list:
        holiday_instruction = (
            "\nFor a public-holiday-list question, show the holiday names and dates directly in this chat "
            "as a Markdown bullet list or table. Do NOT create, attach, link to, or offer a downloadable file. "
            "Only include names and dates present in the retrieved policy context. If the context has no holiday "
            "calendar or dates, clearly say the indexed documents do not contain the list and advise contacting HR."
        )

    prompt = f"""You are an employee leave-policy assistant. Answer only about employee leave.
Use only the retrieved policy context below. Do not invent rules. If the context does not answer the question, say the policy document does not specify it and advise contacting HR. Do not state that a leave request is approved; approval must follow the company process.
{holiday_instruction}

Question: {question}
Retrieved leave-policy context:
{context}

Answer concisely in plain language."""
    prompt_sql = sql_string(prompt)
    model_sql = sql_string(model_name)
    rows = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model_sql}', '{prompt_sql}') AS ANSWER"
    ).collect()
    if not rows or rows[0]["ANSWER"] is None:
        raise RuntimeError("Cortex COMPLETE returned no answer.")
    answer = str(rows[0]["ANSWER"]).strip()
    # COMPLETE may return JSON-formatted text in some configurations.
    try:
        parsed = json.loads(answer)
        if isinstance(parsed, dict) and "choices" in parsed:
            answer = str(parsed["choices"][0].get("messages", answer))
    except Exception:
        pass
    return answer


def search_policy(question: str, model_name: str) -> str:
    """Retrieve policy context once, then try the selected model and safe fallbacks."""
    try:
        context = retrieve_policy(question)
    except Exception as exc:
        return (
            "I couldn't retrieve the leave policy. Please verify that "
            "LEAVE_POLICY_SEARCH exists and that your active Snowflake role has permission to use it. "
            "Technical detail: " + str(exc)
        )

    if context == "No relevant leave-policy passage was found.":
        return "I couldn't find a matching leave-policy passage. Please check the policy document or contact HR."

    # Use the selected model first, then try other configured models if it is unavailable/legacy.
    candidates = [model_name] + [name for name in CORTEX_MODELS if name != model_name]
    errors = []
    for candidate in candidates:
        try:
            return generate_with_cortex(question, context, candidate)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    return (
        "I retrieved the relevant leave-policy text, but none of the configured Cortex models could generate an answer. "
        "Check model availability for your Snowflake region/account and try a supported model. Details: "
        + " | ".join(errors)
    )


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    """Render a small Markdown table without the optional 'tabulate' dependency."""
    if df.empty:
        return "No records found."
    columns = [str(col) for col in df.columns]
    def cell(value):
        if pd.isna(value):
            return "—"
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    header = "| " + " | ".join(cell(col) for col in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(cell(value) for value in row) + " |" for row in df.itertuples(index=False, name=None)]
    return "\n".join([header, divider] + rows)


def get_holiday_list(question: str) -> str:
    """Read holiday records directly from the HOLIDAYS table and format them in chat."""
    holidays_table = f"{DB}.{SCHEMA}.HOLIDAYS"
    try:
        df = run_query(f"SELECT * FROM {holidays_table}")
    except Exception as exc:
        return (
            "I couldn't retrieve the holiday calendar from " + holidays_table + ". "
            "Please verify the table name, schema, and access permissions. "
            "Technical detail: " + str(exc)
        )

    if df.empty:
        return "The HOLIDAYS table exists but contains no holiday records. Please check the holiday data or contact HR."

    # Identify common holiday-name and date column names without assuming an exact schema.
    column_lookup = {str(col).upper(): col for col in df.columns}
    name_candidates = ["HOLIDAY_NAME", "HOLIDAY", "NAME", "EVENT_NAME", "TITLE"]
    date_candidates = ["HOLIDAY_DATE", "DATE", "HOLIDAY_DT", "EVENT_DATE", "START_DATE"]
    name_col = next((column_lookup[c] for c in name_candidates if c in column_lookup), None)
    date_col = next((column_lookup[c] for c in date_candidates if c in column_lookup), None)

    # If the question specifies a year and a date column is available, return only that year.
    year_match = re.search(r"\b(20\d{2})\b", question)
    if year_match and date_col:
        requested_year = int(year_match.group(1))
        parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
        df = df.loc[parsed_dates.dt.year == requested_year].copy()
        if df.empty:
            return f"No holidays were found for {requested_year} in the HOLIDAYS table."

    # Prefer a clean holiday-name/date table; fall back to all columns if names differ.
    if name_col and date_col:
        display = df[[name_col, date_col]].copy()
        display.columns = ["Holiday", "Date"]
        display["Date"] = pd.to_datetime(display["Date"], errors="ignore").astype(str)
    else:
        display = df.copy()

    heading = "**Public Holidays**"
    if year_match:
        heading += f" ({year_match.group(1)})"
    return heading + "\n\n" + dataframe_to_markdown(display)


def answer_question(question: str, employee: dict, model_name: str) -> str:
    intent = detect_intent(question)

    if intent == "OFF_TOPIC":
        return ("This chatbot is designed for leave-related questions only. "
                "For salary, health benefits, or other HR-related assistance, please contact your HR team.")

    if intent == "GREETING":
        return f"Hello {employee['EMPLOYEE_NAME']}! You can ask me about your leave balance, leave requests, leave eligibility, or leave policy."

    if intent == "PROFILE":
        return (
            f"**Employee:** {employee['EMPLOYEE_NAME']}\n\n"
            f"**Employee ID:** {employee['EMPLOYEE_ID']}\n\n"
            f"**Email:** {employee['EMAIL']}\n\n"
            f"**Department:** {employee['DEPARTMENT']}\n\n"
            f"**Manager:** {employee['MANAGER_NAME']}\n\n"
            f"**Joining date:** {employee['JOINING_DATE']}"
        )

    if intent == "HOLIDAYS":
        # Holiday records are structured data, so query HOLIDAYS directly instead of RAG search.
        return get_holiday_list(question)

    # Read the leave table only after an explicit leave-related request.
    summary = get_leave_summary(str(employee["EMPLOYEE_ID"]))
    approved_days = status_days(summary, "APPROVED")
    taken_days = status_days(summary, "TAKEN")
    pending_days = status_days(summary, "PENDING")
    rejected_days = status_days(summary, "REJECTED")
    counted_days = approved_days + taken_days
    allocation = float(employee.get("ANNUAL_LEAVE_ALLOCATION", DEFAULT_ENTITLEMENT) or DEFAULT_ENTITLEMENT)
    available_days = max(0.0, allocation - counted_days)

    if intent == "COUNTED":
        return (f"You have **{counted_days:g} counted leave days** so far "
                f"({approved_days:g} approved + {taken_days:g} already taken). "
                f"Your remaining eligible balance is **{available_days:g} days**.")

    if intent == "SUMMARY":
        return (
            f"**Your leave summary**\n\n"
            f"- Annual entitlement: **{allocation:g} days**\n"
            f"- Approved leave: **{approved_days:g} days**\n"
            f"- Total Leave Availed: **{counted_days:g} days**\n"
            f"- Remaining eligible balance: **{available_days:g} days**\n"
            f"- Pending: **{pending_days:g} days**\n"
            f"- Rejected: **{rejected_days:g} days**"
        )

    if intent == "AVAILABLE":
        return (f"You have **{available_days:g} leave days remaining** out of your "
                f"{allocation:g}-day entitlement. Approved leave ({approved_days:g} days) and "
                f"already-taken leave ({taken_days:g} days) count against this balance.")

    if intent == "ELIGIBILITY":
        days = requested_days(question)
        if days is None:
            return (f"You currently have **{available_days:g} eligible leave days remaining** out of "
                    f"{allocation:g} days. Tell me how many days you want to take, and I can compare "
                    "that request with your available balance. Final approval depends on your manager and company process.")
        if days <= available_days:
            return (f"**Yes, your request is within your current leave balance.** You have {available_days:g} days available, "
                    f"and you are asking for {days:g} days. If taken, you would have {available_days - days:g} days remaining. "
                    "This is an eligibility check only; your manager must still approve the request.")
        return (f"**No, this request exceeds your current leave balance.** Your annual entitlement is {allocation:g} days, "
                f"and {counted_days:g} days have already been counted ({approved_days:g} approved + {taken_days:g} taken), "
                f"leaving {available_days:g} days available. You asked for {days:g} days, which is {days - available_days:g} days "
                "more than your balance. Contact HR if you believe an exception or another leave category applies.")

    if intent == "PENDING":
        return f"You have **{pending_days:g} pending leave days** awaiting approval."

    if intent == "REJECTED":
        return f"You have **{rejected_days:g} rejected leave days**."

    if intent == "REQUESTS":
        requests = get_leave_requests(str(employee["EMPLOYEE_ID"]))
        if requests.empty:
            return "I couldn't find any leave requests for your account."
        requests.columns = [str(c).replace("_", " ").title() for c in requests.columns]
        return "Here are your leave requests:\n\n" + dataframe_to_markdown(requests)

    if intent == "POLICY":
        return search_policy(question, model_name)

    return (
        "I can help with leave-related questions such as:\n"
        "- **Leave balance:** How many leave days do I have left?\n"
        "- **Eligibility:** Can I take 10 days of leave?\n"
        "- **Summary:** Give me a summary of my leave details.\n"
        "- **Requests:** Show my leave requests.\n"
        "- **Policy:** What is the annual leave policy?"
    )


st.title("📅 Employee Leave Chatbot")
st.caption("Ask about your leave balance, eligibility, requests, or leave policy.")

if "employee" not in st.session_state:
    st.session_state.employee = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if st.session_state.get("cortex_model") not in CORTEX_MODELS:
    # Reset stale session selections, including previously configured legacy models.
    st.session_state.cortex_model = CORTEX_MODELS[0]

if st.session_state.employee is None:
    st.subheader("Employee login")
    st.info("Prototype login: this email lookup is not secure authentication. Use your organization's approved SSO/authentication before production.")
    email = st.text_input("Enter your company email", placeholder="name@abc.com")
    if st.button("Continue", type="primary"):
        clean_email = email.strip().lower()
        if not clean_email:
            st.error("Please enter your company email.")
        elif not clean_email.endswith(COMPANY_EMAIL_DOMAIN):
            st.error(f"Access is limited to company email addresses ending in {COMPANY_EMAIL_DOMAIN}.")
        else:
            try:
                employee = get_employee_by_email(clean_email)
                if employee is None:
                    st.error("This email was not found in the EMPLOYEES table. Check the email or contact HR.")
                else:
                    st.session_state.employee = employee
                    st.session_state.messages = []
                    st.rerun()
            except Exception as exc:
                st.error("Unable to read employee data. Verify table names and permissions.")
                st.code(str(exc))
else:
    employee = st.session_state.employee
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(f"Welcome, {employee['EMPLOYEE_NAME']}")
        st.caption(f"{employee['EMAIL']} · {employee['DEPARTMENT']} · Manager: {employee['MANAGER_NAME']}")
    with col2:
        if st.button("Log out"):
            st.session_state.employee = None
            st.session_state.messages = []
            st.rerun()

    # No leave summary or leave details are shown automatically after login.
    st.caption("Your leave details will appear only when you ask a leave-related question.")
    st.session_state.cortex_model = st.selectbox(
        "Cortex model for leave-policy answers",
        options=CORTEX_MODELS,
        index=CORTEX_MODELS.index(st.session_state.cortex_model),
        help="Model access depends on the Snowflake region, account, and role. This selection is used for policy-answer generation."
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask a leave-related question...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Checking your question..."):
                try:
                    response = answer_question(prompt, employee, st.session_state.cortex_model)
                except Exception as exc:
                    response = ("I couldn't process that question. Verify the table columns and permissions, "
                                "then try again. Technical detail: " + str(exc))
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
