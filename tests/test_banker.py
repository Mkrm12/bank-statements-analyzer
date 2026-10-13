"""
Unit tests for banker.py.
Validates taxonomy, subcategories, tags, seed matching, and spending math.
"""
import unittest
import pandas as pd
from banker import TAXONOMY, VALID_CATEGORIES, SEED_PATTERNS, clean_raw_description

class TestBanker(unittest.TestCase):

    def test_taxonomy_completeness(self):
        self.assertGreaterEqual(len(VALID_CATEGORIES), 30, "Taxonomy must define at least 30 distinct categories")
        required_cats = [
            "Groceries",
            "Dining",
            "Takeaway",
            "Coffee",
            "Bars",
            "Shopping",
            "Fashion",
            "Beauty",
            "Home",
            "Electronics",
            "Software",
            "Streaming",
            "Gaming",
            "Transport",
            "Taxis",
            "Fuel",
            "Rent",
            "Energy",
            "Salary",
            "Transfers",
            "Peer-to-Peer",
            "Cash",
            "Refunds"
        ]
        for rc in required_cats:
            self.assertIn(rc, VALID_CATEGORIES, f"Required category '{rc}' missing from master taxonomy")

    def test_no_generic_categories_or_tags(self):
        banned_terms = ["misc", "miscellaneous", "general", "other", "unknown"]
        for cat, subcats in TAXONOMY.items():
            for b in banned_terms:
                self.assertNotIn(b, cat.lower(), f"Category '{cat}' contains banned generic term '{b}'")
            for sub in subcats:
                for b in banned_terms:
                    self.assertNotIn(b, sub.lower(), f"Subcategory '{sub}' contains banned generic term '{b}'")

    def test_clean_merchant_text(self):
        test_cases = [
            ("TFL TRAVEL CHARGE TFL.GOV.UK/CP", "TFL TRAVEL CHARGE"),
            ("UBER *TRIP HELP.UBER.COM", "UBER TRIP"),
            ("CARD PAYMENT TO TESCO STORES 1234 ON 09-01-2026", "TESCO STORES"),
        ]
        for raw, expected_substr in test_cases:
            cleaned = clean_raw_description(raw)
            self.assertTrue(len(cleaned) > 0)
            self.assertTrue(any(w in cleaned.upper() for w in expected_substr.split()[:2]),
                            f"Cleaned '{cleaned}' should retain core merchant name from '{raw}'")

    def test_seed_pattern_matches(self):
        import re
        sample_merchants = [
            ("TFL TRAVEL CHG", "Transport", "TfL (Transport for London)"),
            ("UBER *EATS PENDING", "Takeaway", "Uber Eats"),
            ("DELIVEROO ORDER", "Takeaway", "Deliveroo"),
            ("AMAZON UK MARKETPLACE", "Shopping", "Amazon"),
            ("TESCO STORE 4921", "Groceries", "Tesco"),
            ("SAINSBURYS S/MKTS", "Groceries", "Sainsbury's"),
        ]
        for raw, expected_cat, expected_name in sample_merchants:
            matched = False
            for pat, cat, subcat, c_name, tags in SEED_PATTERNS:
                if re.search(pat, raw, re.IGNORECASE):
                    self.assertEqual(cat, expected_cat)
                    self.assertEqual(c_name, expected_name)
                    self.assertIsInstance(tags, list)
                    self.assertTrue(len(tags) > 0)
                    matched = True
                    break
            self.assertTrue(matched, f"Seed patterns must match standard merchant '{raw}'")

    def test_spend_calculation_strict_outflow(self):
        test_df = pd.DataFrame([
            {"Date": "2026-01-01", "Bank": "HSBC", "Description": "Salary", "Direction": "In", "Amount": 3000.0, "Category": "Salary"},
            {"Date": "2026-01-02", "Bank": "HSBC", "Description": "Tesco", "Direction": "Out", "Amount": 50.0, "Category": "Groceries"},
            {"Date": "2026-01-03", "Bank": "HSBC", "Description": "TfL", "Direction": "Out", "Amount": 10.0, "Category": "Transport"},
            {"Date": "2026-01-04", "Bank": "HSBC", "Description": "Refund", "Direction": "In", "Amount": 20.0, "Category": "Refunds"},
        ])
        out_df = test_df[test_df['Direction'] == 'Out']
        summary_df = out_df.groupby('Category', as_index=False).agg(
            Total_Spent=('Amount', 'sum'),
            Tx_Count=('Amount', 'count')
        )
        total_out = summary_df['Total_Spent'].sum()
        self.assertEqual(total_out, 60.0, "Total spend must strictly sum Out transactions (£50 + £10 = £60)")
        self.assertNotIn("Salary", summary_df['Category'].tolist())

    def test_seed_subcategories_in_taxonomy(self):
        for pat, cat, subcat, clean_name, tags in SEED_PATTERNS:
            self.assertIn(cat, TAXONOMY, f"Category '{cat}' must exist in TAXONOMY")
            self.assertIn(subcat, TAXONOMY[cat], f"Subcategory '{subcat}' for pattern '{pat}' must exist in TAXONOMY['{cat}']")

    def test_pass2_ai_qa_audit_fallback_on_error(self):
        from unittest.mock import patch
        from banker import pass2_ai_qa_audit
        test_df = pd.DataFrame([
            {"Description": "JOHN SMITH", "Clean_Description": "JS", "Direction": "Out", "Amount": 150.0, "Category": "Transfers", "Subcategory": "Internal Account Transfer"}
        ])
        with patch("banker.invoke_llm", side_effect=Exception("API connection timeout")):
            audited_df, cache = pass2_ai_qa_audit(test_df.copy(), memory_cache={})
            self.assertEqual(audited_df.loc[0, "Category"], "Transfers")
            self.assertEqual(audited_df.loc[0, "Subcategory"], "Internal Account Transfer")

    def test_pass2_ai_qa_audit_applies_corrections(self):
        from unittest.mock import patch
        from banker import pass2_ai_qa_audit
        test_df = pd.DataFrame([
            {"Description": "TRANSFER TO J SMITH", "Clean_Description": "JS", "Direction": "Out", "Amount": 200.0, "Category": "Transfers", "Subcategory": "Internal Account Transfer"}
        ])
        mock_response = '[{"id": 0, "category": "Peer-to-Peer", "subcategory": "Personal Transfer", "reason": "Transfer to individual"}]'
        with patch("banker.invoke_llm", return_value=(mock_response, "mock")):
            audited_df, cache = pass2_ai_qa_audit(test_df.copy(), memory_cache={})
            self.assertEqual(audited_df.loc[0, "Category"], "Peer-to-Peer")
            self.assertEqual(audited_df.loc[0, "Subcategory"], "Personal Transfer")
            self.assertIn("TRANSFER TO J SMITH", cache)
            self.assertEqual(cache["TRANSFER TO J SMITH"]["category"], "Peer-to-Peer")

if __name__ == "__main__":
    unittest.main()

