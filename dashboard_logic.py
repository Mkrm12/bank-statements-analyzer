"""
Dashboard Section Builder & Integrity Engine (Phase 10 Enterprise).

Guarantees:
1. Every category with Outflows is included in the Spending grid (Major 6 + Other Spending).
2. Any category with BOTH Outflows and Inflows (or belonging to TWO_WAY_CATEGORIES)
   is flagged as a two-way flow, displaying Out: £X • In: £Y • Net: ±£Z,
   and providing access to all transactions across both directions.
3. The Inflows section ("Verified Inflows, Salaries & Deposits") contains ONLY pure inflows
   that have NOT already been rendered in spending.
4. ZERO DUPLICATION: No category is EVER rendered in both spending and inflows.
5. All categories outside the Top 6 ("Other Spending Areas") are rendered in the exact same
   2-column grid format, with as many categories as necessary (no arbitrary cap).
6. validate_categorisation verifies these integrity invariants.
"""
import pandas as pd

TWO_WAY_CATEGORIES = {
    "Transfers",
    "Peer-to-Peer",
    "Remittance",
    "Savings",
    "Investments",
    "Cash",
    "Credit Card",
    "Loans",
    "BNPL"
}

def build_dashboard_sections(cat_df, summary_df=None):
    """
    Builds structured display sections:
    1. major_spending: Top 2 spend + Top 4 frequency across spending categories
    2. other_spending: All remaining spending categories
    3. pure_inflows: Inflows from categories not already rendered in spending
    4. metrics: total_spend, total_income, net_savings
    """
    if cat_df.empty:
        return {
            "major_spending": pd.DataFrame(),
            "other_spending": pd.DataFrame(),
            "pure_inflows": pd.DataFrame(),
            "metrics": {"total_spend": 0.0, "total_income": 0.0, "net_savings": 0.0}
        }

    df = cat_df.copy()
    df['Amount_Numeric'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)

    # 1. Calculate Outflow Spending by Category
    out_df = df[df['Direction'] == 'Out']
    in_df = df[df['Direction'] == 'In']

    spending_rows = []
    if not out_df.empty:
        spending_summary_raw = out_df.groupby('Category', as_index=False).agg(
            Total_Spent=('Amount_Numeric', 'sum'),
            Tx_Count=('Amount_Numeric', 'count')
        )
        total_out = spending_summary_raw['Total_Spent'].sum()

        for _, row in spending_summary_raw.iterrows():
            cat = row['Category']
            spent = round(float(row['Total_Spent']), 2)
            out_cnt = int(row['Tx_Count'])
            pct = round((spent / total_out) * 100, 1) if total_out > 0 else 0.0

            # Check if this category also has inflows or belongs to TWO_WAY_CATEGORIES
            inflow_subset = in_df[in_df['Category'] == cat]
            received = round(float(inflow_subset['Amount_Numeric'].sum()), 2) if not inflow_subset.empty else 0.0
            in_cnt = int(len(inflow_subset))

            is_two_way = (cat in TWO_WAY_CATEGORIES) or (received > 0)
            net_flow = round(received - spent, 2)
            total_tx = out_cnt + in_cnt

            spending_rows.append({
                "Category": cat,
                "Total_Spent": spent,
                "Tx_Count": out_cnt,
                "Percentage": pct,
                "Total_Received": received,
                "Received_Count": in_cnt,
                "Net_Flow": net_flow,
                "Total_Tx": total_tx,
                "Is_Two_Way": is_two_way
            })

    spending_df = pd.DataFrame(spending_rows)

    # Dynamic Major 6 vs Other Spending
    if not spending_df.empty:
        sorted_by_spend = spending_df.sort_values(by='Total_Spent', ascending=False)
        top_2_spend = sorted_by_spend.head(2)
        remaining_spend = sorted_by_spend.iloc[2:]
        top_4_freq = remaining_spend.sort_values(by='Tx_Count', ascending=False).head(4)

        main_6_df = pd.concat([top_2_spend, top_4_freq]).drop_duplicates(subset=['Category'])
        other_cats_df = spending_df[~spending_df['Category'].isin(main_6_df['Category'])].sort_values(
            by=['Tx_Count', 'Total_Spent'],
            ascending=[False, False]
        )

    else:
        main_6_df = pd.DataFrame()
        other_cats_df = pd.DataFrame()

    rendered_spending_cats = set(spending_df['Category'].dropna().unique()) if not spending_df.empty else set()

    # Pure Inflows (ONLY categories NOT already rendered in spending!)
    pure_in_df = in_df[~in_df['Category'].isin(rendered_spending_cats)]
    pure_inflows_rows = []
    if not pure_in_df.empty:
        in_summary_raw = pure_in_df.groupby('Category', as_index=False).agg(
            Total_Inflow=('Amount_Numeric', 'sum'),
            Tx_Count=('Amount_Numeric', 'count')
        )
        total_pure_in = in_summary_raw['Total_Inflow'].sum()
        for _, row in in_summary_raw.iterrows():
            cat = row['Category']
            in_amt = round(float(row['Total_Inflow']), 2)
            in_cnt = int(row['Tx_Count'])
            pct = round((in_amt / total_pure_in) * 100, 1) if total_pure_in > 0 else 0.0
            pure_inflows_rows.append({
                "Category": cat,
                "Total_Inflow": in_amt,
                "Tx_Count": in_cnt,
                "Percentage": pct
            })

    pure_inflows_df = pd.DataFrame(pure_inflows_rows)
    if not pure_inflows_df.empty:
        pure_inflows_df = pure_inflows_df.sort_values(by='Total_Inflow', ascending=False).reset_index(drop=True)

    # Global Metrics
    all_out = df[df['Direction'] == 'Out']['Amount_Numeric'].sum()
    all_in = df[df['Direction'] == 'In']['Amount_Numeric'].sum()

    return {
        "major_spending": main_6_df,
        "other_spending": other_cats_df,
        "pure_inflows": pure_inflows_df,
        "metrics": {
            "total_spend": round(all_out, 2),
            "total_income": round(all_in, 2),
            "net_savings": round(all_in - all_out, 2)
        }
    }


def validate_categorisation(df, sections=None):
    """
    Integrity Audit Pass:
    1. Ensures no category is rendered simultaneously in spending and pure inflows.
    2. Ensures every category is non-empty and non-generic.
    3. Checks that inflow-only categories never have Direction == 'Out'.
    Returns (is_valid: bool, issues: list of str).
    """
    issues = []
    if df.empty:
        return True, issues

    # Check for empty/missing category
    missing_cat = df['Category'].isna() | (df['Category'].astype(str).str.strip() == '')
    if missing_cat.any():
        issues.append(f"{missing_cat.sum()} transaction(s) have missing Category")

    # Check for banned generic terms
    banned = ["misc", "miscellaneous", "general", "other", "unknown"]
    for idx, row in df.iterrows():
        cat = str(row.get('Category', '')).lower()
        sub = str(row.get('Subcategory', '')).lower()
        if any(b in cat for b in banned):
            issues.append(f"Row {idx} Category '{row.get('Category')}' contains banned term")
        if any(b in sub for b in banned):
            issues.append(f"Row {idx} Subcategory '{row.get('Subcategory')}' contains banned term")

    # Direction validity: Inflow-only categories cannot be Out
    inflow_only = {"Salary", "Pension", "Revenue", "Refunds", "Benefits", "Interest", "Rewards"}
    invalid_out = df[(df['Direction'] == 'Out') & (df['Category'].isin(inflow_only))]
    if not invalid_out.empty:
        cats = invalid_out['Category'].unique().tolist()
        issues.append(f"Inflow-only categories found with Direction='Out': {cats}")

    # No category rendered twice in both spending and pure inflows
    if sections:
        spend_cats = set()
        if not sections.get("major_spending", pd.DataFrame()).empty:
            spend_cats.update(sections["major_spending"]["Category"].dropna().unique())
        if not sections.get("other_spending", pd.DataFrame()).empty:
            spend_cats.update(sections["other_spending"]["Category"].dropna().unique())

        inflow_cats = set()
        if not sections.get("pure_inflows", pd.DataFrame()).empty:
            inflow_cats.update(sections["pure_inflows"]["Category"].dropna().unique())

        overlap = spend_cats.intersection(inflow_cats)
        if overlap:
            issues.append(f"Categories duplicated in both spending and inflows: {overlap}")

    return len(issues) == 0, issues

