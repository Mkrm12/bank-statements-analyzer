"""
Unit and integration tests for chat_engine.py.
Validates DuckDB view creation, analytical SQL views, instant search_vault, and calculations.
"""
import unittest
import pandas as pd
from chat_engine import prepare_duckdb_conn, search_vault

class TestChatEngine(unittest.TestCase):

    def setUp(self):
        self.sample_df = pd.DataFrame([
            {
                "Timeline_ID": 1,
                "Date": "2026-01-05",
                "Bank": "HSBC",
                "Description": "TFL TRAVEL CHG",
                "Clean_Description": "TfL (Transport for London)",
                "Category": "Transport",
                "Subcategory": "Public Transit (TfL, Metro, Bus)",
                "Tags": ["tfl", "commute", "travel"],
                "Direction": "Out",
                "Amount": 15.00
            },
            {
                "Timeline_ID": 2,
                "Date": "2026-01-12",
                "Bank": "HSBC",
                "Description": "TFL TRAVEL CHG",
                "Clean_Description": "TfL (Transport for London)",
                "Category": "Transport",
                "Subcategory": "Public Transit (TfL, Metro, Bus)",
                "Tags": ["tfl", "commute", "travel"],
                "Direction": "Out",
                "Amount": 25.00
            },
            {
                "Timeline_ID": 3,
                "Date": "2026-01-15",
                "Bank": "HSBC",
                "Description": "ACME GLOBAL CORP PAYMENT",
                "Clean_Description": "Acme Global Corp",
                "Category": "Salary",
                "Subcategory": "Employment Wages",
                "Tags": ["salary", "acme", "wages"],
                "Direction": "In",
                "Amount": 2400.00
            },
            {
                "Timeline_ID": 4,
                "Date": "2026-01-20",
                "Bank": "HSBC",
                "Description": "TESCO STORES 2910",
                "Clean_Description": "Tesco",
                "Category": "Groceries",
                "Subcategory": "Supermarket",
                "Tags": ["groceries", "supermarket"],
                "Direction": "Out",
                "Amount": 60.00
            }
        ])

    def test_duckdb_views_creation(self):
        con, enriched = prepare_duckdb_conn(self.sample_df, persist_path=None)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        expected_views = [
            "transactions",
            "v_weekly_spend",
            "v_monthly_spend",
            "v_merchant_summary",
            "v_category_summary",
            "v_inflows_summary",
            "v_daily_cashflow"
        ]
        for v in expected_views:
            self.assertIn(v, tables, f"Expected view or table '{v}' missing from DuckDB")

    def test_search_vault_keyword(self):
        res_df, total = search_vault(self.sample_df, query_str="TfL")
        self.assertEqual(len(res_df), 2, "Search for 'TfL' should return 2 transactions")
        self.assertAlmostEqual(total, 40.00, places=2)

    def test_search_vault_inflows_only(self):
        res_df, total = search_vault(self.sample_df, query_str="ACME", direction="In")
        self.assertEqual(len(res_df), 1, "Search for 'ACME' inflows should return 1 transaction")
        self.assertAlmostEqual(total, 2400.00, places=2)

    def test_search_vault_category_filter(self):
        res_df, total = search_vault(self.sample_df, category="Groceries")
        self.assertEqual(len(res_df), 1)
        self.assertAlmostEqual(total, 60.00, places=2)

    def test_weekly_travel_average_calculation(self):
        con, _ = prepare_duckdb_conn(self.sample_df, persist_path=None)
        sql = """
        WITH weekly AS (
          SELECT DATE_TRUNC('week', Date_Parsed) as wk, SUM(Amount) as wk_spend
          FROM transactions
          WHERE Direction = 'Out' AND Category = 'Transport'
          GROUP BY wk
        )
        SELECT ROUND(AVG(wk_spend), 2) as avg_per_week, ROUND(SUM(wk_spend), 2) as total_spend, COUNT(*) as num_weeks FROM weekly;
        """
        row = con.execute(sql).fetchone()
        avg_wk, tot_spend, n_weeks = row
        self.assertEqual(n_weeks, 2, "Transport spend occurred across 2 weeks")
        self.assertAlmostEqual(tot_spend, 40.00, places=2, msg="Total transport spend must be £40.00")
        self.assertAlmostEqual(avg_wk, 20.00, places=2, msg="Average weekly transport spend must be (£15 + £25)/2 = £20.00")

    def test_net_cashflow_calculation(self):
        con, _ = prepare_duckdb_conn(self.sample_df, persist_path=None)
        sql = "SELECT ROUND(SUM(CASE WHEN Direction = 'In' THEN Amount ELSE -Amount END), 2) FROM transactions"
        net_cashflow = con.execute(sql).fetchone()[0]
        self.assertAlmostEqual(net_cashflow, 2300.00, places=2)

    def test_parquet_persistence(self):
        import os
        test_path = "data/test_vault.parquet"
        con, enriched = prepare_duckdb_conn(self.sample_df, persist_path=test_path)
        self.assertTrue(os.path.exists(test_path), f"{test_path} should exist after prepare_duckdb_conn")
        saved = pd.read_parquet(test_path)
        self.assertEqual(len(saved), len(self.sample_df))
        self.assertIn("Search_Text", saved.columns)
        self.assertIn("Signed_Amount", saved.columns)
        if os.path.exists(test_path):
            os.remove(test_path)

if __name__ == "__main__":
    unittest.main()
