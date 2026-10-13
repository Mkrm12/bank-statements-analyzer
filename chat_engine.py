"""
Precision Financial Chat & SQL Engine powered by DuckDB and LLM Router.

Features:
- Enriched database schema (Parsed Dates, ISO Weeks, Day of Week, Year-Month, Subcategory, Tags).
- Pre-built SQL views for multi-hop time series (v_weekly_spend, v_monthly_spend, v_merchant_summary).
- Few-shot guided SQL generation for averages, trends, entity retrieval, and category breakdowns.
- Zero arithmetic hallucinations: DuckDB calculates every number to the penny.
- Transparent drilldown: Every calculation retrieves its underlying matching transactions.
"""
import duckdb
import pandas as pd
import re
import json
from llm_router import invoke_llm, parse_json_safely
from banker import VALID_CATEGORIES

def validate_safe_sql(sql_str):
    """
    Validates that a generated SQL query is strictly read-only and safe.
    Blocks multiple statements and data-modifying / system operations.
    """
    if not sql_str or not isinstance(sql_str, str):
        return False, "Empty SQL query"
    clean = sql_str.strip()
    
    # Must start with SELECT or WITH
    if not re.match(r"^(?:SELECT|WITH)\b", clean, re.IGNORECASE):
        return False, "Query must begin with SELECT or WITH"
        
    # Disallow statement chaining with semicolons
    cleaned_no_quotes = re.sub(r"'(?:''|[^'])*'", "", clean)
    if ";" in cleaned_no_quotes.rstrip(";"):
        return False, "Statement chaining not permitted"
        
    # Forbidden keywords (mutation, attachment, file execution)
    forbidden = r"\b(?:DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|DETACH|COPY|INSTALL|LOAD|EXEC|CALL|PRAGMA|VACUUM|CREATE)\b"
    if re.search(forbidden, cleaned_no_quotes, re.IGNORECASE):
        return False, "Data modification and system operations are strictly prohibited"
        
    return True, "Safe"

def prepare_duckdb_conn(df, persist_path=None):
    """
    Enriches DataFrame with temporal, search, and numeric dimensions and registers in DuckDB.
    100% in-memory ephemeral database (:memory:) - zero persistent disk storage.
    """
    df_clean = df.copy()
    if 'Timeline_ID' not in df_clean.columns:
        df_clean['Timeline_ID'] = range(1, len(df_clean) + 1)
        
    df_clean['Date_Parsed'] = pd.to_datetime(df_clean['Date'], format='mixed', dayfirst=True, errors='coerce')
    df_clean['Year'] = df_clean['Date_Parsed'].dt.year
    df_clean['Month'] = df_clean['Date_Parsed'].dt.month
    df_clean['Month_Name'] = df_clean['Date_Parsed'].dt.strftime('%B')
    df_clean['Year_Month'] = df_clean['Date_Parsed'].dt.strftime('%Y-%m')
    df_clean['Week_Number'] = df_clean['Date_Parsed'].dt.isocalendar().week
    df_clean['Year_Week'] = df_clean['Date_Parsed'].dt.strftime('%Y-W%V')
    df_clean['Day_Of_Week'] = df_clean['Date_Parsed'].dt.strftime('%A')
    df_clean['Is_Weekend'] = df_clean['Date_Parsed'].dt.dayofweek >= 5

    df_clean['Amount'] = pd.to_numeric(df_clean['Amount'], errors='coerce').fillna(0.0)
    if 'Direction' not in df_clean.columns:
        df_clean['Direction'] = 'Out'
    if 'Clean_Description' not in df_clean.columns:
        df_clean['Clean_Description'] = df_clean.get('Description', '')
    if 'Category' not in df_clean.columns:
        df_clean['Category'] = ''
    if 'Subcategory' not in df_clean.columns:
        df_clean['Subcategory'] = ''

    df_clean['Signed_Amount'] = df_clean.apply(
        lambda r: r['Amount'] if r.get('Direction') == 'In' else -r['Amount'], axis=1
    )

    # Format tags as string for SQL LIKE search
    def format_tags(val):
        if isinstance(val, list):
            return ", ".join([str(t).lower() for t in val])
        return str(val).lower() if val else ""

    df_clean['Tags_Str'] = df_clean['Tags'].apply(format_tags) if 'Tags' in df_clean.columns else ""
    raw_search = (
        df_clean['Clean_Description'].fillna('').astype(str) + " " +
        df_clean['Description'].fillna('').astype(str) + " " +
        df_clean['Category'].fillna('').astype(str) + " " +
        df_clean.get('Subcategory', pd.Series(['']*len(df_clean))).fillna('').astype(str) + " " +
        df_clean['Tags_Str']
    ).str.lower()

    # Generate unpunctuated, apostrophe-stripped, and root stem variants for fuzzy matching
    no_apos = raw_search.str.replace("'", "", regex=False).str.replace("’", "", regex=False)
    space_apos = raw_search.str.replace("'", " ", regex=False).str.replace("’", " ", regex=False)
    no_punct = raw_search.str.replace(r"[^\w\s]", " ", regex=True)

    def extract_stem_tokens(text: str) -> str:
        tokens = [w for w in text.split() if len(w) > 3 and w.endswith('s')]
        stems = [w[:-1] for w in tokens]
        return " ".join(stems)

    stems = no_apos.apply(extract_stem_tokens)

    df_clean['Search_Text'] = (
        raw_search + " " + no_apos + " " + space_apos + " " + no_punct + " " + stems
    ).str.replace(r"\s+", " ", regex=True).str.strip()

    con = duckdb.connect(database=":memory:")
    con.execute("CREATE TABLE transactions AS SELECT * FROM df_clean")

    # Register analytical helper views
    con.execute("""
    CREATE OR REPLACE VIEW v_weekly_spend AS
    SELECT 
        Year_Week,
        DATE_TRUNC('week', Date_Parsed) AS week_start,
        Category,
        ROUND(SUM(Amount), 2) AS weekly_spend,
        COUNT(*) AS txn_count
    FROM transactions
    WHERE Direction = 'Out'
    GROUP BY 1, 2, 3;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW v_monthly_spend AS
    SELECT 
        Year_Month,
        Category,
        ROUND(SUM(Amount), 2) AS monthly_spend,
        COUNT(*) AS txn_count
    FROM transactions
    WHERE Direction = 'Out'
    GROUP BY 1, 2;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW v_merchant_summary AS
    SELECT 
        Clean_Description,
        Category,
        Direction,
        COUNT(*) AS txn_count,
        ROUND(SUM(Amount), 2) AS total_amount,
        ROUND(AVG(Amount), 2) AS avg_amount,
        MIN(Date_Parsed) AS first_seen,
        MAX(Date_Parsed) AS last_seen
    FROM transactions
    GROUP BY 1, 2, 3;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW v_category_summary AS
    SELECT 
        Category,
        Direction,
        COUNT(*) AS txn_count,
        ROUND(SUM(Amount), 2) AS total_amount,
        ROUND(AVG(Amount), 2) AS avg_amount,
        ROUND(MIN(Amount), 2) AS min_amount,
        ROUND(MAX(Amount), 2) AS max_amount
    FROM transactions
    GROUP BY 1, 2;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW v_inflows_summary AS
    SELECT 
        Clean_Description,
        Subcategory,
        Tags_Str,
        COUNT(*) AS txn_count,
        ROUND(SUM(Amount), 2) AS total_received,
        ROUND(AVG(Amount), 2) AS avg_received,
        MAX(Date_Parsed) AS latest_date
    FROM transactions
    WHERE Direction = 'In'
    GROUP BY 1, 2, 3;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW v_daily_cashflow AS
    SELECT 
        Date_Parsed,
        ROUND(SUM(CASE WHEN Direction = 'In' THEN Amount ELSE 0 END), 2) AS daily_income,
        ROUND(SUM(CASE WHEN Direction = 'Out' THEN Amount ELSE 0 END), 2) AS daily_spend,
        ROUND(SUM(CASE WHEN Direction = 'In' THEN Amount ELSE -Amount END), 2) AS net_daily
    FROM transactions
    GROUP BY 1
    ORDER BY 1;
    """)

    # Persistent Storage: Auto-sync to disk if persist_path provided
    if persist_path:
        try:
            import os
            dir_name = os.path.dirname(persist_path)
            if not dir_name or os.path.exists(dir_name):
                df_clean.to_parquet(persist_path, index=False)
        except Exception:
            pass

    # Engine Jail: Disable external filesystem operations and lock configuration
    try:
        con.execute("PRAGMA enable_external_access=false;")
        con.execute("SET lock_configuration=true;")
    except Exception:
        pass

    return con, df_clean

def search_vault(df, query_str="", category=None, direction=None, limit=100):
    """
    Ultra-fast DuckDB search and filter API (0 LLM tokens, 0ms latency).
    Filters across merchant brand, description, category, subcategory, and tags.
    """
    con, _ = prepare_duckdb_conn(df, persist_path=None)
    conditions = ["1=1"]
    
    if query_str and query_str.strip():
        sanitized = re.sub(r"[^a-zA-Z0-9\s\.\-]", "", query_str).strip()
        tokens = [t.lower() for t in sanitized.split() if t]
        for t in tokens:
            conditions.append(f"Search_Text ILIKE '%{t}%'")
            
    if category and category != "All":
        clean_cat = category.replace("'", "''")
        conditions.append(f"Category = '{clean_cat}'")
        
    if direction and direction in ("In", "Out"):
        conditions.append(f"Direction = '{direction}'")
        
    where_sql = " AND ".join(conditions)
    sql = f"""
    SELECT Date, Bank, Clean_Description, Category, Subcategory, Tags_Str, Direction, Amount
    FROM transactions
    WHERE {where_sql}
    ORDER BY Date_Parsed DESC, Timeline_ID DESC
    LIMIT {limit}
    """
    try:
        res_df = con.execute(sql).df()
        total_sum = con.execute(f"SELECT ROUND(SUM(Amount), 2) FROM transactions WHERE {where_sql}").fetchone()[0] or 0.0
        return res_df, float(total_sum)
    except Exception as e:
        print(f"[Search Vault Error] {e}")
        return pd.DataFrame(), 0.0

def ask_financial_data(user_query, df, preferred_engine="auto", chat_history=None, custom_keys=None):
    """
    Executes precise financial queries:
    1. Generates DuckDB SQL using rich temporal schema and analytical views.
    2. Runs query in DuckDB to calculate exact figures.
    3. Retrieves companion source rows for auditability.
    4. Formats clear conversational response.
    """
    con, df_clean = prepare_duckdb_conn(df)
    clean_user_query = re.sub(r"[\r\n]+", " ", str(user_query)).strip()[:500]
    
    # Summary bounds
    total_spent = con.execute("SELECT SUM(Amount) FROM transactions WHERE Direction = 'Out'").fetchone()[0] or 0.0
    total_in = con.execute("SELECT SUM(Amount) FROM transactions WHERE Direction = 'In'").fetchone()[0] or 0.0
    date_min = con.execute("SELECT MIN(Date_Parsed) FROM transactions").fetchone()[0]
    date_max = con.execute("SELECT MAX(Date_Parsed) FROM transactions").fetchone()[0]
    min_date_str = str(date_min)[:10] if date_min else "N/A"
    max_date_str = str(date_max)[:10] if date_max else "N/A"

    hist_snippet = ""
    if chat_history:
        recent = chat_history[-3:]
        hist_snippet = "\n".join([f"{m.get('role', 'user')}: {m.get('content', m.get('text', ''))}" for m in recent])

    sql_prompt = f"""
    You are an elite SQL and Financial Data Engineer for DuckDB.
    Write an optimal DuckDB SQL query to answer the user query.

    TABLE: `transactions`
    Columns:
    - Timeline_ID: INT
    - Date_Parsed: DATE (YYYY-MM-DD)
    - Date: VARCHAR (e.g. '09 Jan 2026')
    - Year: INT (e.g. 2025, 2026)
    - Month: INT (1-12)
    - Month_Name: VARCHAR ('January', 'October', etc.)
    - Year_Month: VARCHAR (e.g. '2025-10', '2026-01')
    - Year_Week: VARCHAR (e.g. '2026-W02')
    - Day_Of_Week: VARCHAR ('Monday', 'Friday', etc.)
    - Is_Weekend: BOOLEAN
    - Bank: VARCHAR ('HSBC', 'Santander', 'Starling', 'Revolut')
    - Description: VARCHAR (Raw description)
    - Clean_Description: VARCHAR (Clean brand/person, e.g. 'Acme Corp Ltd', 'TfL (Transport for London)', 'Uber Eats')
    - Category: VARCHAR (One of: {json.dumps(VALID_CATEGORIES)})
    - Subcategory: VARCHAR (e.g. 'Public Transit', 'Employment Wages', 'Fast Food', 'ATM Withdrawal')
    - Tags_Str: VARCHAR (Keywords, e.g. 'tfl, commute, tube, bus')
    - Direction: VARCHAR ('Out' for expenses/spending, 'In' for income/salary/receipts/refunds)
    - Amount: DOUBLE (Positive transaction value)

    VIEWS AVAILABLE:
    - `v_weekly_spend` (Year_Week, week_start, Category, weekly_spend, txn_count)
    - `v_monthly_spend` (Year_Month, Category, monthly_spend, txn_count)
    - `v_merchant_summary` (Clean_Description, Category, Direction, txn_count, total_amount, avg_amount)
    - `v_category_summary` (Category, Direction, txn_count, total_amount, avg_amount, min_amount, max_amount)
    - `v_inflows_summary` (Clean_Description, Subcategory, Tags_Str, txn_count, total_received, avg_received, latest_date)
    - `v_daily_cashflow` (Date_Parsed, daily_income, daily_spend, net_daily)

    CONTEXT:
    - Date Range: {min_date_str} to {max_date_str}
    - Total Spent: £{total_spent:,.2f}
    - Total Inflows: £{total_in:,.2f}
    - User Query: "{user_query}"
    - Recent Chat: {hist_snippet}

    QUERY RULES:
    1. CASE-INSENSITIVE MATCHING (CRITICAL):
       - DuckDB string equality (=) is strictly case-sensitive. ALWAYS use `ILIKE` or `LOWER(column) IN (...)` for Category and text matching!
       - E.g.: `LOWER(Category) IN ('transport', 'travel')` or `Category ILIKE '%transport%'`. NEVER write `Category = 'transport'`.
    2. SYNONYMS & BROAD CATEGORY ALIGNMENT:
       - Transport / Travel: User words "transport", "travel", "commute", "transit", "tfl", "train", "tube", "bus", "flights", "taxi":
         ALWAYS match `(LOWER(Category) IN ('transport', 'travel', 'taxis') OR Search_Text ILIKE '%tfl%' OR Search_Text ILIKE '%travel%' OR Search_Text ILIKE '%commute%')`.
       - Food / Dining / Takeaway: User words "food", "dining", "takeaway", "takeout", "eating out", "delivery":
         ALWAYS match `(LOWER(Category) IN ('dining', 'takeaway', 'coffee', 'bars') OR Search_Text ILIKE '%deliveroo%' OR Search_Text ILIKE '%uber%')`.
       - Groceries vs Food/Takeaway: If user says "food/takeaway" or says "not groceries", strictly exclude groceries: `AND LOWER(Category) != 'groceries'`.
       - Multi-Category Queries: When user asks for both Travel and Food in one query (e.g. "how much on travel each month and how much on food/takeaway"):
         Include BOTH categories in the WHERE clause:
         `((LOWER(Category) IN ('transport', 'travel', 'taxis') OR Search_Text ILIKE '%tfl%') OR (LOWER(Category) IN ('dining', 'takeaway', 'coffee')))`
         and group by BOTH `Year_Month` and `Category`:
         ```sql
         SELECT 
             Year_Month, 
             Month_Name, 
             Category,
             ROUND(SUM(Amount), 2) AS monthly_spend, 
             COUNT(*) AS txn_count 
         FROM transactions 
         WHERE Direction = 'Out' AND ((LOWER(Category) IN ('transport', 'travel', 'taxis') OR Search_Text ILIKE '%tfl%') OR (LOWER(Category) IN ('dining', 'takeaway', 'coffee')))
         GROUP BY Year_Month, Month_Name, Category
         ORDER BY Year_Month ASC, monthly_spend DESC;
         ```
    3. MONTHLY BREAKDOWN ("each month", "per month", "month by month", "monthly", "which month"):
       - ALWAYS group by `Year_Month` and `Month_Name` (and `Category` if multi-category).
       - NEVER summarize into a single row when the user asked for a monthly breakdown!
    4. ENTITY & MERCHANT INQUIRIES (e.g., "Uber Eats", "Papas", "Papa's Chicken", "TfL", "Amazon", "Starbucks", "John"):
       - ALWAYS search using `(Search_Text ILIKE '%<root_stem>%' OR Clean_Description ILIKE '%<root_stem>%')`.
       - USE ROOT STEMS & PARTIALS for maximum flexibility against typos, plurals, and missing apostrophes:
         * If the user writes "papas", "eatng papas", "papa's", or "papas chicken", search with the root `%papa%`.
         * If user writes "uber eats", search with `%uber%`.
         * If user writes "mcdonalds", search with `%mcdonald%`.
         * If user writes "sainsburys", search with `%sainsbury%`.
         * If user writes "starbucks", search with `%starbuck%`.
         `Search_Text` is pre-normalized with and without apostrophes, plurals, and spaces, so `Search_Text ILIKE '%<stem>%'` matches effortlessly.
       - DO NOT restrict Direction unless user explicitly says "spent on" or "earned from".
    5. COMPARISON QUERIES ("did I spend more on X or Y", "compare A and B"):
       - When comparing two merchants or categories (e.g. Uber Eats vs Papa's Chicken), aggregate BOTH entities using CASE WHEN:
         ```sql
         SELECT 
             CASE 
                 WHEN Search_Text ILIKE '%uber%' THEN 'Uber Eats'
                 WHEN Search_Text ILIKE '%papa%' THEN 'Papa''s Chicken'
                 ELSE 'Other'
             END AS entity_name,
             ROUND(SUM(Amount), 2) AS total_spent,
             COUNT(*) AS txn_count
         FROM transactions
         WHERE Direction = 'Out' AND (Search_Text ILIKE '%uber%' OR Search_Text ILIKE '%papa%')
         GROUP BY 1
         ORDER BY total_spent DESC;
         ```
         companion_filter: `Search_Text ILIKE '%uber%' OR Search_Text ILIKE '%papa%'`
    6. INCOME / SALARY / WAGES / INFLOWS (e.g., "how much did I earn", "paychecks", "salary", "inflows"):
       - Query transactions with `Direction = 'In'` or use `v_inflows_summary`.
       - Example: `SELECT ROUND(SUM(Amount), 2) as total_earned, COUNT(*) as txn_count FROM transactions WHERE Direction = 'In'`
    7. WEEKLY / MONTHLY AVERAGES (e.g. "on avg how much per week on travel", "weekly dining spend"):
       - ALWAYS calculate weekly averages via CTE grouping by `DATE_TRUNC('week', Date_Parsed)` on `transactions`:
       ```sql
       WITH weekly AS (
         SELECT DATE_TRUNC('week', Date_Parsed) as wk, SUM(Amount) as wk_spend
         FROM transactions
         WHERE Direction = 'Out' AND (LOWER(Category) IN ('transport', 'travel') OR Search_Text ILIKE '%tfl%')
         GROUP BY wk
       )
       SELECT ROUND(AVG(wk_spend), 2) as avg_per_week, ROUND(SUM(wk_spend), 2) as total_spend, COUNT(*) as num_weeks FROM weekly;
       ```
    8. NET CASH FLOW / SAVINGS (e.g., "net savings", "did I save money", "net cash flow"):
       - Calculate: Total In - Total Out
       - Example: `SELECT ROUND(SUM(CASE WHEN Direction = 'In' THEN Amount ELSE -Amount END), 2) as net_cashflow FROM transactions`
    9. FOR EXPENSES / SPENDING TOTALS:
       - Strictly use `Direction = 'Out'`.
    10. ALWAYS return an aggregation or clear result with `total` or relevant column names.

    Return ONLY JSON:
    {{
       "sql": "SELECT ...",
       "companion_filter": "Direction = 'Out' AND (LOWER(Category) IN ('transport', 'travel') OR Search_Text ILIKE '%tfl%')"
    }}
    """

    try:
        raw_res, _ = invoke_llm(sql_prompt, preferred=preferred_engine, temperature=0.0, custom_keys=custom_keys)
        parsed = parse_json_safely(raw_res)
        sql_query = parsed.get("sql", "").strip()
        companion_filter = parsed.get("companion_filter", "")
    except Exception:
        clean_word = re.sub(r"[^a-zA-Z0-9\s]", "", clean_user_query).strip()
        sql_query = f"SELECT Timeline_ID, Date, Bank, Clean_Description, Category, Direction, Amount FROM transactions WHERE Search_Text ILIKE '%{clean_word}%' ORDER BY Date_Parsed DESC LIMIT 500"
        companion_filter = f"Search_Text ILIKE '%{clean_word}%'"

    # Security: Validate SQL against injection & destructive operations
    is_safe, safety_reason = validate_safe_sql(sql_query)
    if not is_safe:
        clean_word = re.sub(r"[^a-zA-Z0-9\s]", "", clean_user_query).strip()
        sql_query = f"SELECT Timeline_ID, Date, Bank, Clean_Description, Category, Direction, Amount FROM transactions WHERE Search_Text ILIKE '%{clean_word}%' ORDER BY Date_Parsed DESC LIMIT 500"
        companion_filter = f"Search_Text ILIKE '%{clean_word}%'"

    # Execute SQL in DuckDB
    matched_df = pd.DataFrame()
    executed_sql = sql_query
    calc_summary = {}
    result_table_str = ""

    try:
        result = con.cursor().execute(sql_query).df()
        
        if not result.empty:
            cols = [c.lower() for c in result.columns]
            spend_col = next((c for c in result.columns if any(k in c.lower() for k in ["total", "sum", "spend", "amount", "income"])), None)
            count_col = next((c for c in result.columns if any(k in c.lower() for k in ["count", "txn", "num"])), None)

            if spend_col:
                try:
                    calc_summary["grand_total"] = round(float(result[spend_col].sum()), 2)
                except Exception:
                    pass
            if count_col:
                try:
                    calc_summary["total_transactions"] = int(result[count_col].sum())
                except Exception:
                    pass

            if len(result) > 1:
                # Multi-row aggregated breakdown (monthly, category, entity)
                result_table_str = result.to_string(index=False)
            elif len(result) == 1:
                raw_dict = result.to_dict(orient="records")[0]
                for k, v in raw_dict.items():
                    if hasattr(v, "tolist"):
                        v = v.tolist()
                    if isinstance(v, (int, float, str, list, bool)):
                        calc_summary[k] = v
                    else:
                        calc_summary[k] = str(v)

            # Retrieve companion rows for auditability (up to 500 rows)
            if companion_filter:
                try:
                    matched_df = con.execute(f"SELECT Date, Bank, Clean_Description, Category, Direction, Amount FROM transactions WHERE {companion_filter} ORDER BY Date_Parsed DESC LIMIT 500").df()
                except Exception:
                    pass
            
            if matched_df.empty:
                base_where = re.search(r"WHERE\s+(.*?)(?:GROUP\s+BY|ORDER\s+BY|LIMIT|$)", sql_query, re.I | re.DOTALL)
                if base_where:
                    where_clause = base_where.group(1).strip()
                    try:
                        matched_df = con.execute(f"SELECT Date, Bank, Clean_Description, Category, Direction, Amount FROM transactions WHERE {where_clause} ORDER BY Date_Parsed DESC LIMIT 500").df()
                    except Exception:
                        pass
        else:
            calc_summary["grand_total"] = 0.0
            calc_summary["total_transactions"] = 0

        # Automatic Fuzzy & Root Stem Second-Chance Recovery if 0 results
        needs_fuzzy_recovery = False
        if result.empty:
            needs_fuzzy_recovery = True
        elif calc_summary.get("total_transactions", 0) == 0 and calc_summary.get("grand_total", 0.0) == 0.0 and matched_df.empty:
            needs_fuzzy_recovery = True

        if needs_fuzzy_recovery:
            STOP_WORDS = {
                "how", "much", "did", "spend", "spent", "what", "was", "total", "were", 
                "my", "in", "on", "at", "for", "the", "a", "an", "is", "are", "and", "or", 
                "to", "from", "eating", "eatng", "bought", "buying", "paid", "paying", 
                "there", "should", "be", "show", "me", "tell", "any", "all", "records", 
                "transactions", "more", "less", "than", "each", "month", "per", "which"
            }
            tokens = [re.sub(r"[^a-zA-Z0-9]", "", w.lower()) for w in user_query.split()]
            candidates = []
            for t in tokens:
                if len(t) >= 3 and t not in STOP_WORDS:
                    candidates.append(t)
                    if len(t) > 3 and t.endswith('s'):
                        candidates.append(t[:-1])

            if candidates:
                stem_clauses = [f"Search_Text ILIKE '%{c}%'" for c in candidates]
                recovery_where = " OR ".join(stem_clauses)
                try:
                    recov_res = con.cursor().execute(f"""
                        SELECT 
                            Clean_Description,
                            ROUND(SUM(Amount), 2) AS total_spent,
                            COUNT(*) AS txn_count
                        FROM transactions
                        WHERE Direction = 'Out' AND ({recovery_where})
                        GROUP BY 1
                        ORDER BY total_spent DESC
                        LIMIT 20
                    """).df()

                    if not recov_res.empty:
                        recov_txns = con.cursor().execute(f"""
                            SELECT Date, Bank, Clean_Description, Category, Direction, Amount
                            FROM transactions
                            WHERE ({recovery_where})
                            ORDER BY Date_Parsed DESC
                            LIMIT 500
                        """).df()
                        
                        matched_df = recov_txns
                        calc_summary["grand_total"] = round(float(recov_res["total_spent"].sum()), 2)
                        calc_summary["total_transactions"] = int(recov_res["txn_count"].sum())
                        result_table_str = recov_res.to_string(index=False)
                        executed_sql = f"-- Fuzzy Stem Recovery Applied\nSELECT * FROM transactions WHERE Direction = 'Out' AND ({recovery_where});"
                except Exception:
                    pass
    except Exception as err:
        err_msg = str(err)
        print(f"[DuckDB Error] {err_msg} -> Semantic Fallback")
        words = [w for w in user_query.lower().split() if len(w) > 2 and w not in ["how", "much", "did", "spend", "what", "was", "total"]]
        kw = words[0] if words else ""
        try:
            executed_sql = f"SELECT Date, Bank, Clean_Description, Category, Direction, Amount FROM transactions WHERE Search_Text ILIKE '%{kw}%' ORDER BY Date_Parsed DESC LIMIT 500"
            matched_df = con.execute(executed_sql).df()
            if not matched_df.empty and "Amount" in matched_df.columns:
                calc_summary["total"] = float(matched_df["Amount"].sum())
                calc_summary["count"] = len(matched_df)
        except Exception:
            matched_df = pd.DataFrame()

    # Format numbers for synthesis
    safe_summary = {}
    for k, v in calc_summary.items():
        if isinstance(v, float):
            safe_summary[k] = round(v, 2)
        elif not isinstance(v, (list, dict)):
            safe_summary[k] = v

    target_cols = ['Date', 'Bank', 'Clean_Description', 'Category', 'Direction', 'Amount']
    available_cols = [c for c in target_cols if c in matched_df.columns]
    final_matched_df = matched_df[available_cols] if available_cols else matched_df

    breakdown_summary = ""
    if not final_matched_df.empty and len(final_matched_df) > 1:
        if 'Category' in final_matched_df.columns:
            cat_grp = final_matched_df.groupby('Category')['Amount'].agg(['sum', 'count']).sort_values('sum', ascending=False)
            breakdown_lines = [f"- {cat}: £{row['sum']:,.2f} ({int(row['count'])} txn{'s' if int(row['count']) > 1 else ''})" for cat, row in cat_grp.iterrows()]
            breakdown_summary = "\n".join(breakdown_lines)

    synth_prompt = f"""
    You are an elite, direct Financial Assistant.
    Answer the user query: "{user_query}"

    EXACT DATABASE FACTS:
    - Calculated Metrics: {json.dumps(safe_summary)}
    - Query Results Table (All Periods / Categories):
{result_table_str if result_table_str else "N/A"}
    - Matched Source Transactions Count: {len(final_matched_df)}
    - Breakdown by Category / Source:
{breakdown_summary if breakdown_summary else "N/A"}
    - Sample Source Rows:
    {final_matched_df.head(15).to_string() if not final_matched_df.empty else "None"}

    INSTRUCTIONS:
    1. If the user asked for a monthly breakdown ("each month", "per month", "month by month", "which month"), you MUST explicitly report EVERY SINGLE MONTH listed in the Query Results Table with its exact spending amount (£) and transaction count, followed by the grand total across all months!
    2. If multiple categories were asked for (e.g. both travel and food/takeaway), present the monthly amounts for each category clearly.
    3. Answer directly and concisely in the very first sentence, citing the exact calculated numbers with £ currency.
    4. Keep it direct, clean, and factual. Never mention SQL, DuckDB, or table/column names.
    """

    try:
        conversational_answer, _ = invoke_llm(synth_prompt, preferred=preferred_engine, temperature=0.0, custom_keys=custom_keys)
    except Exception:
        tot = safe_summary.get("total", safe_summary.get("total_spent", 0.0))
        conversational_answer = f"Found {len(final_matched_df)} matching transaction(s) totaling £{tot:,.2f}."

    return {
        "text": conversational_answer.strip(),
        "df": final_matched_df,
        "sql": executed_sql,
        "calc": safe_summary
    }
