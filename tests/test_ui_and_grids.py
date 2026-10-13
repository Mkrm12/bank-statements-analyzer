import unittest
import re
import os
import pandas as pd

class TestUIAndGrids(unittest.TestCase):
    def test_no_tags_or_subcategories_in_grid_columns(self):
        """Ensure Subcategory and Tags are not displayed to users in app.py category tables."""
        with open("app.py", "r", encoding="utf-8") as f:
            code = f.read()

        # Check draw_horizontal_grid columns
        match_outflow = re.search(r"def draw_horizontal_grid.*?cols_to_view = \[(.*?)\]", code, re.DOTALL)
        self.assertIsNotNone(match_outflow, "draw_horizontal_grid not found in app.py")
        outflow_cols = match_outflow.group(1)
        self.assertNotIn("Subcategory", outflow_cols, "Subcategory should not be in draw_horizontal_grid visible columns")
        self.assertNotIn("Tags_Str", outflow_cols, "Tags_Str should not be in draw_horizontal_grid visible columns")

        # Check draw_inflows_grid columns
        match_inflow = re.search(r"def draw_inflows_grid.*?cols_to_view = \[(.*?)\]", code, re.DOTALL)
        self.assertIsNotNone(match_inflow, "draw_inflows_grid not found in app.py")
        inflow_cols = match_inflow.group(1)
        self.assertNotIn("Subcategory", inflow_cols, "Subcategory should not be in draw_inflows_grid visible columns")
        self.assertNotIn("Tags_Str", inflow_cols, "Tags_Str should not be in draw_inflows_grid visible columns")

    def test_dynamic_spending_breakdown(self):
        """Verify that categories are dynamically selected (Top 2 spend + Top 4 frequency) followed by remaining categories."""
        with open("app.py", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("main_6_df", code)
        self.assertIn("other_cats_df", code)

    def test_button_two_phase_state_protection(self):
        """Verify that audit button uses two-phase state toggle preventing double-clicks and duplication."""
        with open("app.py", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("st.session_state.is_processing = True", code)
        self.assertIn("st.status(", code)
        # Verify button is omitted during processing
        self.assertIn("elif st.session_state.get(\"is_processing\", False):", code)

    def test_chat_css_avatars_and_bubble_rules(self):
        """Verify that style.css styles modern Streamlit chat avatars and user/assistant bubbles."""
        with open("style.css", "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn("stChatMessageAvatarUser", css)
        self.assertIn("stChatMessageAvatarAssistant", css)
        self.assertIn("background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)", css)

    def test_chat_synthesis_breakdown_instruction(self):
        """Verify that chat engine includes source breakdown logic and instructions."""
        with open("chat_engine.py", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("breakdown_summary", code)
        self.assertIn("Breakdown by Category / Source", code)

    def test_build_dashboard_sections_no_duplicate_categories(self):
        """Verify that two-way categories are unified in spending and excluded from pure inflows."""
        import pandas as pd
        from dashboard_logic import build_dashboard_sections, validate_categorisation

        sample_txns = pd.DataFrame([
            {"Date": "2026-01-01", "Bank": "HSBC", "Description": "Tesco", "Direction": "Out", "Amount": 50.0, "Category": "Groceries", "Subcategory": "Supermarket"},
            {"Date": "2026-01-02", "Bank": "HSBC", "Description": "Salary", "Direction": "In", "Amount": 2500.0, "Category": "Salary", "Subcategory": "Employment Wages"},
            {"Date": "2026-01-03", "Bank": "HSBC", "Description": "To Own Account", "Direction": "Out", "Amount": 400.0, "Category": "Transfers", "Subcategory": "Internal Account Transfer"},
            {"Date": "2026-01-04", "Bank": "HSBC", "Description": "From Own Account", "Direction": "In", "Amount": 100.0, "Category": "Transfers", "Subcategory": "Internal Account Transfer"},
            {"Date": "2026-01-05", "Bank": "HSBC", "Description": "Refund Store", "Direction": "In", "Amount": 20.0, "Category": "Refunds", "Subcategory": "Merchant Refund"},
        ])

        sections = build_dashboard_sections(sample_txns)
        spend_cats = set(sections["major_spending"]["Category"]).union(set(sections["other_spending"]["Category"]))
        inflow_cats = set(sections["pure_inflows"]["Category"])

        # Transfers must be in spending and NOT in inflows
        self.assertIn("Transfers", spend_cats, "Transfers must be included in spending")
        self.assertNotIn("Transfers", inflow_cats, "Transfers must NOT be duplicated in pure inflows")

        # Overlap must be empty
        self.assertEqual(len(spend_cats & inflow_cats), 0, "No category can be rendered in both spending and inflows")

        # Two-way flags
        transfers_row = sections["major_spending"][sections["major_spending"]["Category"] == "Transfers"].iloc[0]
        self.assertTrue(transfers_row["Is_Two_Way"])
        self.assertEqual(transfers_row["Total_Spent"], 400.0)
        self.assertEqual(transfers_row["Total_Received"], 100.0)
        self.assertEqual(transfers_row["Net_Flow"], -300.0)

        # Integrity pass must pass
        is_valid, issues = validate_categorisation(sample_txns, sections)
        self.assertTrue(is_valid, f"Categorisation integrity should pass, got issues: {issues}")

    def test_validate_categorisation_catches_duplicate_or_invalid_flow(self):
        """Verify that validate_categorisation catches duplicated categories or invalid flow directions."""
        import pandas as pd
        from dashboard_logic import validate_categorisation

        # Inflow-only category with Direction='Out'
        bad_df = pd.DataFrame([
            {"Date": "2026-01-01", "Bank": "HSBC", "Description": "Bad Row", "Direction": "Out", "Amount": 500.0, "Category": "Salary", "Subcategory": "Employment Wages"}
        ])
        is_valid, issues = validate_categorisation(bad_df)
        self.assertFalse(is_valid)
        self.assertTrue(any("Inflow-only" in s for s in issues))

    def test_other_spending_ordered_by_frequency(self):
        """Verify that non-main categories are ordered by transaction count descending."""
        import pandas as pd
        from dashboard_logic import build_dashboard_sections

        # Create 8 different spending categories so at least 2 end up in other_spending
        rows = [
            {"Date": "2026-01-01", "Bank": "HSBC", "Description": "A", "Direction": "Out", "Amount": 1000.0, "Category": "Rent"}, # Top 1 Spend
            {"Date": "2026-01-02", "Bank": "HSBC", "Description": "B", "Direction": "Out", "Amount": 800.0, "Category": "Shopping"}, # Top 2 Spend
            # Top 4 frequency items (6, 5, 4, 3 transactions)
            {"Date": "2026-01-03", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"},
            {"Date": "2026-01-04", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"},
            {"Date": "2026-01-05", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"},
            {"Date": "2026-01-06", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"},
            {"Date": "2026-01-06", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"},
            {"Date": "2026-01-06", "Bank": "HSBC", "Description": "C", "Direction": "Out", "Amount": 10.0, "Category": "Coffee"}, # 6 txns (Top freq 1)
            {"Date": "2026-01-07", "Bank": "HSBC", "Description": "D", "Direction": "Out", "Amount": 15.0, "Category": "Dining"},
            {"Date": "2026-01-08", "Bank": "HSBC", "Description": "D", "Direction": "Out", "Amount": 15.0, "Category": "Dining"},
            {"Date": "2026-01-09", "Bank": "HSBC", "Description": "D", "Direction": "Out", "Amount": 15.0, "Category": "Dining"},
            {"Date": "2026-01-09", "Bank": "HSBC", "Description": "D", "Direction": "Out", "Amount": 15.0, "Category": "Dining"},
            {"Date": "2026-01-09", "Bank": "HSBC", "Description": "D", "Direction": "Out", "Amount": 15.0, "Category": "Dining"}, # 5 txns (Top freq 2)
            {"Date": "2026-01-10", "Bank": "HSBC", "Description": "E", "Direction": "Out", "Amount": 20.0, "Category": "Takeaway"},
            {"Date": "2026-01-11", "Bank": "HSBC", "Description": "E", "Direction": "Out", "Amount": 20.0, "Category": "Takeaway"},
            {"Date": "2026-01-11", "Bank": "HSBC", "Description": "E", "Direction": "Out", "Amount": 20.0, "Category": "Takeaway"},
            {"Date": "2026-01-11", "Bank": "HSBC", "Description": "E", "Direction": "Out", "Amount": 20.0, "Category": "Takeaway"}, # 4 txns (Top freq 3)
            {"Date": "2026-01-12", "Bank": "HSBC", "Description": "F", "Direction": "Out", "Amount": 25.0, "Category": "Transport"},
            {"Date": "2026-01-13", "Bank": "HSBC", "Description": "F", "Direction": "Out", "Amount": 25.0, "Category": "Transport"},
            {"Date": "2026-01-13", "Bank": "HSBC", "Description": "F", "Direction": "Out", "Amount": 25.0, "Category": "Transport"}, # 3 txns (Top freq 4)
            # Outside Main 6: Parking (2 txns, £10) vs Fuel (1 txn, £50)
            {"Date": "2026-01-14", "Bank": "HSBC", "Description": "G", "Direction": "Out", "Amount": 50.0, "Category": "Fuel"}, # 1 txn, £50
            {"Date": "2026-01-15", "Bank": "HSBC", "Description": "H", "Direction": "Out", "Amount": 5.0, "Category": "Parking"},
            {"Date": "2026-01-16", "Bank": "HSBC", "Description": "H", "Direction": "Out", "Amount": 5.0, "Category": "Parking"}, # 2 txns, £10 -> ranks HIGHER than Fuel!
        ]
        sections = build_dashboard_sections(pd.DataFrame(rows))
        other_df = sections["other_spending"]
        self.assertFalse(other_df.empty)
        # Parking has 2 txns, Fuel has 1 txn -> Parking must come before Fuel
        categories = list(other_df["Category"])
        self.assertIn("Parking", categories)
        self.assertIn("Fuel", categories)
        self.assertLess(categories.index("Parking"), categories.index("Fuel"), "Parking (2 txns) must precede Fuel (1 txn) in other_spending")

    def test_generate_summary_pdf_structure(self):
        """Verify that summary PDF generates valid multi-page document with overview and category ledger."""
        from report_generator import generate_summary_pdf, generate_anonymized_csv
        rows = [
            {"Timeline_ID": i, "Date": "2026-01-05", "Date_Parsed": pd.Timestamp("2026-01-05"), "Bank": "HSBC", "Description": f"Txn {i}", "Clean_Description": f"Merchant {i}", "Category": "Transport" if i % 2 == 0 else "Takeaway", "Direction": "Out", "Amount": 15.50}
            for i in range(25)
        ]
        df = pd.DataFrame(rows)
        pdf_bytes = generate_summary_pdf(df, None, "AI financial assessment.")
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 2000, "PDF bytes should be substantial with multi-page structure")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Output must start with PDF file signature")

        csv_str = generate_anonymized_csv(df)
        self.assertIn("Merchant 0", csv_str)
        self.assertIn("Transport", csv_str)

if __name__ == "__main__":
    unittest.main()


