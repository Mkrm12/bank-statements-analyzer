"""
Pulse AI - Report & Artifact Generator
Provides high-fidelity, exportable audit artifacts:
1. Cleaned & Anonymised Transactions CSV
2. Executive Financial Audit PDF Summary
3. Conversational AI Chat Transcript PDF
"""
import io
import re
from datetime import datetime
import pandas as pd
from fpdf import FPDF


def sanitize_pdf_text(text: str) -> str:
    """Sanitizes text for core PDF fonts (Latin-1 safe, strips unsupported emojis)."""
    if not text:
        return ""
    s = str(text)
    # Normalize typography
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "--")
    s = s.replace("\u2022", "*").replace("\u2026", "...")
    # Filter non-latin1 characters
    out = []
    for ch in s:
        if ord(ch) < 256:
            out.append(ch)
        else:
            out.append(" ")
    res = "".join(out)
    return re.sub(r"[ \t]+", " ", res).strip()


class PulsePDF(FPDF):
    def __init__(self, title_text="Financial Audit Report"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.doc_title = title_text
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_fill_color(30, 41, 59)  # Deep slate navy
        self.rect(0, 0, 210, 20, "F")
        self.set_xy(10, 5)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, sanitize_pdf_text(f"Pulse AI | {self.doc_title}"), ln=True)
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        page_str = f"Page {self.page_no()} | Generated securely by Pulse AI"
        self.cell(0, 8, sanitize_pdf_text(page_str), align="C")


def generate_summary_pdf(master_df: pd.DataFrame, summary_df: pd.DataFrame = None, roast_text: str = None) -> bytes:
    """
    Builds an executive-grade Financial Audit PDF Report:
    - Page 1: Executive Overview Front Page (Metadata, KPI Cards, Category Breakdown, AI Assessment)
    - Page 2+: Detailed Itemized Transaction Ledger grouped by Category with dates, merchants, banks, directions, and amounts.
    """
    pdf = PulsePDF("Financial Audit Report")
    pdf.set_margins(12, 16, 12)
    pdf.add_page()

    # ----------------------------------------------------
    # PAGE 1: EXECUTIVE OVERVIEW FRONT PAGE
    # ----------------------------------------------------
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(15, 23, 42)  # Slate 900
    pdf.cell(0, 8, "Executive Financial Audit Overview", ln=True)

    # Metadata subtitle
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    banks = sorted([str(b) for b in master_df["Bank"].dropna().unique()]) if "Bank" in master_df.columns else []
    banks_str = ", ".join(banks) if banks else "Standard Accounts"
    
    period_str = ""
    if "Date_Parsed" in master_df.columns and not master_df["Date_Parsed"].dropna().empty:
        try:
            min_d = master_df["Date_Parsed"].dropna().min()
            max_d = master_df["Date_Parsed"].dropna().max()
            period_str = f"{min_d.strftime('%d %b %Y')} - {max_d.strftime('%d %b %Y')}"
        except Exception:
            pass
    if not period_str and "Date" in master_df.columns:
        period_str = f"{len(master_df)} Records"

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)  # Slate 500
    meta_line = f"Audit Date: {now_str}  |  Period: {period_str}  |  Institutions: {banks_str}"
    pdf.cell(0, 5, sanitize_pdf_text(meta_line), ln=True)
    pdf.ln(3)

    # Core Calculations
    out_df = master_df[master_df.get("Direction", "Out") == "Out"] if "Direction" in master_df.columns else master_df
    in_df = master_df[master_df.get("Direction", "") == "In"] if "Direction" in master_df.columns else pd.DataFrame()
    
    total_spent = float(out_df["Amount"].sum()) if not out_df.empty and "Amount" in out_df.columns else 0.0
    total_in = float(in_df["Amount"].sum()) if not in_df.empty and "Amount" in in_df.columns else 0.0
    net_flow = total_in - total_spent
    count_out = len(out_df)
    count_in = len(in_df)

    # 3 Column KPI Summary Cards
    col_w = 58
    card_h = 19
    gap = 6
    y_card = pdf.get_y()

    # Card 1: Total Spent (Expenses)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(12, y_card, col_w, card_h, "DF")
    pdf.set_xy(15, y_card + 2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w - 6, 4, "TOTAL SPENT (OUTFLOWS)", ln=True)
    pdf.set_xy(15, y_card + 6.5)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(239, 68, 68)  # Red
    pdf.cell(col_w - 6, 7, sanitize_pdf_text(f"\xa3{total_spent:,.2f}"), ln=True)
    pdf.set_xy(15, y_card + 13.5)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(col_w - 6, 3.5, f"{count_out} expense transactions", ln=True)

    # Card 2: Total Received (Income / Inflows)
    c2_x = 12 + col_w + gap
    pdf.rect(c2_x, y_card, col_w, card_h, "DF")
    pdf.set_xy(c2_x + 3, y_card + 2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w - 6, 4, "TOTAL RECEIVED (INFLOWS)", ln=True)
    pdf.set_xy(c2_x + 3, y_card + 6.5)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(16, 185, 129)  # Green
    pdf.cell(col_w - 6, 7, sanitize_pdf_text(f"\xa3{total_in:,.2f}"), ln=True)
    pdf.set_xy(c2_x + 3, y_card + 13.5)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(col_w - 6, 3.5, f"{count_in} inflow transactions", ln=True)

    # Card 3: Net Cash Flow
    c3_x = 12 + (col_w + gap) * 2
    net_color = (16, 185, 129) if net_flow >= 0 else (239, 68, 68)
    net_sign = "+" if net_flow >= 0 else ""
    pdf.rect(c3_x, y_card, col_w, card_h, "DF")
    pdf.set_xy(c3_x + 3, y_card + 2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w - 6, 4, "NET CASH FLOW", ln=True)
    pdf.set_xy(c3_x + 3, y_card + 6.5)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*net_color)
    pdf.cell(col_w - 6, 7, sanitize_pdf_text(f"{net_sign}\xa3{net_flow:,.2f}"), ln=True)
    pdf.set_xy(c3_x + 3, y_card + 13.5)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(148, 163, 184)
    sav_rate = (net_flow / total_in * 100) if total_in > 0 else 0.0
    pdf.cell(col_w - 6, 3.5, f"Net Rate: {sav_rate:+.1f}%", ln=True)

    pdf.set_y(y_card + card_h + 6)

    # Prepare Category Summary if missing
    if summary_df is None or summary_df.empty:
        if not out_df.empty and "Category" in out_df.columns:
            grp = out_df.groupby("Category")["Amount"].agg(Total_Spent="sum", Tx_Count="count").reset_index()
            t_out = grp["Total_Spent"].sum()
            grp["Percentage"] = (grp["Total_Spent"] / t_out * 100).round(1) if t_out > 0 else 0.0
            summary_df = grp.sort_values(by="Total_Spent", ascending=False)
        else:
            summary_df = pd.DataFrame()

    # Section: Category Spending Breakdown Table (Front Page)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 6, "Spending & Category Breakdown", ln=True)
    pdf.ln(1)

    t_cols = [74, 32, 44, 36]
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(t_cols[0], 6.5, "Category", 1, 0, "L", True)
    pdf.cell(t_cols[1], 6.5, "Transactions", 1, 0, "C", True)
    pdf.cell(t_cols[2], 6.5, "Total Spend", 1, 0, "R", True)
    pdf.cell(t_cols[3], 6.5, "Share of Spend", 1, 1, "R", True)

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    
    if not summary_df.empty:
        for idx, (_, row) in enumerate(summary_df.head(10).iterrows()):
            cat = str(row.get("Category", "Other"))
            cnt = int(row.get("Tx_Count", row.get("Count", 1)))
            spent = float(row.get("Total_Spent", row.get("Amount", 0.0)))
            pct = float(row.get("Percentage", 0.0))
            is_alt = (idx % 2 == 1)
            pdf.set_fill_color(248, 250, 252) if is_alt else pdf.set_fill_color(255, 255, 255)

            pdf.cell(t_cols[0], 5.8, sanitize_pdf_text(cat), 1, 0, "L", is_alt)
            pdf.cell(t_cols[1], 5.8, str(cnt), 1, 0, "C", is_alt)
            pdf.cell(t_cols[2], 5.8, sanitize_pdf_text(f"\xa3{spent:,.2f}"), 1, 0, "R", is_alt)
            pdf.cell(t_cols[3], 5.8, f"{pct:.1f}%", 1, 1, "R", is_alt)

    pdf.ln(5)

    # Section: AI Financial Evaluation / Reality Check (Front Page)
    if roast_text:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 6, "AI Financial Audit Assessment", ln=True)
        pdf.ln(1)

        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        clean_roast = sanitize_pdf_text(roast_text)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(186, 4.8, clean_roast, border=1, fill=True)

    # ----------------------------------------------------
    # PAGE 2+: DETAILED TRANSACTION LEDGER BY CATEGORY
    # ----------------------------------------------------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, "Detailed Transaction Ledger (By Category)", ln=True)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5, "Complete itemized ledger grouped by spending and income categories.", ln=True)
    pdf.ln(3)

    # Determine Category Ordering (Outflows sorted by spend desc, then Inflows, then remaining)
    cat_order = []
    if "Category" in master_df.columns:
        if not out_df.empty:
            cat_order = out_df.groupby("Category")["Amount"].sum().sort_values(ascending=False).index.tolist()
        all_unique = list(master_df["Category"].dropna().unique())
        for c in all_unique:
            if c not in cat_order:
                cat_order.append(c)
    else:
        cat_order = ["All Transactions"]

    # Table Column Specifications: Total width = 186 mm
    l_cols = [26, 82, 26, 22, 30]

    def render_ledger_header():
        pdf.set_fill_color(241, 245, 249)
        pdf.set_draw_color(203, 213, 225)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(l_cols[0], 5.8, "Date", 1, 0, "L", True)
        pdf.cell(l_cols[1], 5.8, "Merchant / Description", 1, 0, "L", True)
        pdf.cell(l_cols[2], 5.8, "Bank", 1, 0, "L", True)
        pdf.cell(l_cols[3], 5.8, "Direction", 1, 0, "C", True)
        pdf.cell(l_cols[4], 5.8, "Amount", 1, 1, "R", True)

    for cat in cat_order:
        cat_subset = master_df[master_df["Category"] == cat].copy() if "Category" in master_df.columns else master_df.copy()
        if cat_subset.empty:
            continue

        # Sort transactions
        if "Date_Parsed" in cat_subset.columns:
            cat_subset.sort_values(by="Date_Parsed", ascending=False, inplace=True)
        elif "Timeline_ID" in cat_subset.columns:
            cat_subset.sort_values(by="Timeline_ID", ascending=False, inplace=True)

        cat_total = float(cat_subset["Amount"].sum()) if "Amount" in cat_subset.columns else 0.0
        cat_count = len(cat_subset)

        # Check page break before starting category
        if pdf.get_y() > 248:
            pdf.add_page()

        # Category Banner Bar
        pdf.set_fill_color(226, 232, 240)  # Slate 200
        pdf.set_draw_color(203, 213, 225)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(15, 23, 42)
        banner_lbl = f"  {cat}   --   Total: \xa3{cat_total:,.2f}  ({cat_count} transaction{'s' if cat_count != 1 else ''})"
        pdf.cell(186, 6.5, sanitize_pdf_text(banner_lbl), 1, 1, "L", True)
        
        # Render Column Headers
        render_ledger_header()

        # Render Rows
        for r_idx, (_, r) in enumerate(cat_subset.iterrows()):
            if pdf.get_y() > 270:
                pdf.add_page()
                pdf.set_fill_color(241, 245, 249)
                pdf.set_draw_color(203, 213, 225)
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(186, 5, sanitize_pdf_text(f"  {cat} (Continued)"), 1, 1, "L", True)
                render_ledger_header()

            d_val = str(r.get("Date", ""))[:12]
            desc_val = str(r.get("Clean_Description") or r.get("Description") or "")
            if len(desc_val) > 42:
                desc_val = desc_val[:39] + "..."
            bank_val = str(r.get("Bank", ""))[:14]
            dir_val = str(r.get("Direction", "Out"))
            amt_val = float(r.get("Amount", 0.0))

            is_alt = (r_idx % 2 == 1)
            pdf.set_fill_color(248, 250, 252) if is_alt else pdf.set_fill_color(255, 255, 255)
            pdf.set_draw_color(226, 232, 240)

            # Date
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(51, 65, 85)
            pdf.cell(l_cols[0], 5.2, sanitize_pdf_text(d_val), 1, 0, "L", is_alt)

            # Description
            pdf.cell(l_cols[1], 5.2, sanitize_pdf_text(desc_val), 1, 0, "L", is_alt)

            # Bank
            pdf.cell(l_cols[2], 5.2, sanitize_pdf_text(bank_val), 1, 0, "L", is_alt)

            # Direction
            if dir_val.lower() == "in":
                pdf.set_text_color(16, 185, 129)
            else:
                pdf.set_text_color(100, 116, 139)
            pdf.cell(l_cols[3], 5.2, sanitize_pdf_text(dir_val), 1, 0, "C", is_alt)

            # Amount
            pdf.set_font("Helvetica", "B", 8)
            if dir_val.lower() == "in":
                pdf.set_text_color(16, 185, 129)
                amt_str = f"+\xa3{amt_val:,.2f}"
            else:
                pdf.set_text_color(15, 23, 42)
                amt_str = f"\xa3{amt_val:,.2f}"
            pdf.cell(l_cols[4], 5.2, sanitize_pdf_text(amt_str), 1, 1, "R", is_alt)

        pdf.ln(3)

    return bytes(pdf.output())


def generate_chat_pdf(chat_history: list) -> bytes:
    """Builds a formatted AI Chat Q&A Transcript PDF."""
    pdf = PulsePDF("Financial Chat Transcript")
    pdf.add_page()

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    pdf.cell(0, 6, sanitize_pdf_text(f"Session Timestamp: {now_str}"), ln=True)
    pdf.ln(4)

    if not chat_history:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "No conversational inquiries recorded in this session.", ln=True)
        return bytes(pdf.output())

    for idx, msg in enumerate(chat_history, start=1):
        role = msg.get("role", "user")
        content = sanitize_pdf_text(msg.get("content", msg.get("text", "")))

        if role == "user":
            pdf.set_fill_color(241, 245, 249)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(0, 7, f"Q{idx//2 + 1}: {content}", ln=True, fill=True)
            pdf.ln(1)
        else:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(51, 65, 85)
            pdf.multi_cell(0, 5, content)
            pdf.ln(4)

    return bytes(pdf.output())


def generate_anonymized_csv(master_df: pd.DataFrame) -> str:
    """Exports cleaned, standardized transactions dataframe as CSV string."""
    cols_to_export = [c for c in ["Date", "Bank", "Clean_Description", "Category", "Subcategory", "Direction", "Amount"] if c in master_df.columns]
    export_df = master_df[cols_to_export].copy() if cols_to_export else master_df.copy()
    if "Clean_Description" in export_df.columns:
        export_df.rename(columns={"Clean_Description": "Description"}, inplace=True)
    return export_df.to_csv(index=False)

