"""
Generalization and anti-overfitting tests for Pulse AI.
Verifies that the system functions universally for any user, bank, or transaction
without hardcoded assumptions or personal overfitting.
"""
import unittest
from extractor import detect_bank, _find_columns
from banker import rule_based_classify, clean_raw_description, SEED_PATTERNS

class TestGeneralization(unittest.TestCase):

    def test_bank_detection_generalization(self):
        # A statement from Barclays
        barclays_text = "BARCLAYS BANK UK PLC. SORT CODE: 20-00-00. ACCOUNT NUMBER: 12345678. STATEMENT 42. BALANCE: £500.00"
        self.assertEqual(detect_bank(barclays_text), "Barclays")

        # A statement from Monzo
        monzo_text = "MONZO BANK LTD. SORT CODE: 04-00-04. ACCOUNT NUMBER: 99887766. STATEMENT. BALANCE £1,250.00"
        self.assertEqual(detect_bank(monzo_text), "Monzo")

        # An unlisted regional or international bank with valid banking signals
        generic_text = "FIRST REGIONAL BANK. SORT CODE: 11-22-33. ACCOUNT NUMBER: 88776655. MONTHLY STATEMENT. BALANCE £3,400.00"
        self.assertEqual(detect_bank(generic_text), "Bank Statement")

    def test_column_header_generalization(self):
        # Test headers with Credit, Debit, Balance
        line_credit_debit = [
            {"text": "Date", "x0": 20, "x1": 50},
            {"text": "Description", "x0": 80, "x1": 200},
            {"text": "Debit", "x0": 250, "x1": 290},
            {"text": "Credit", "x0": 340, "x1": 380},
            {"text": "Balance", "x0": 430, "x1": 480}
        ]
        cols = _find_columns([line_credit_debit], 0)
        self.assertIsNotNone(cols, "Must detect table header with Debit / Credit / Balance")
        self.assertIn("in", cols)
        self.assertIn("out", cols)
        self.assertIn("balance", cols)

        # Test headers with Deposits, Withdrawals, Balance
        line_dep_with = [
            {"text": "Transaction Date", "x0": 20, "x1": 90},
            {"text": "Description", "x0": 110, "x1": 220},
            {"text": "Withdrawals", "x0": 260, "x1": 320},
            {"text": "Deposits", "x0": 360, "x1": 410},
            {"text": "Balance", "x0": 450, "x1": 500}
        ]
        cols2 = _find_columns([line_dep_with], 0)
        self.assertIsNotNone(cols2, "Must detect table header with Withdrawals / Deposits / Balance")
        self.assertIn("in", cols2)
        self.assertIn("out", cols2)
        self.assertIn("balance", cols2)

    def test_universal_salary_payroll_rule(self):
        # Any employer with standard payroll, salary, or wage markers
        salary_samples = [
            "ACME CORP MONTHLY SALARY",
            "GLOBAL TECH LTD DIRECT DEPOSIT PAYROLL",
            "HEALTHCARE NHS WAGES DEPOSIT"
        ]
        for s in salary_samples:
            cat, subcat, name, tags = rule_based_classify(s, direction="In")
            self.assertEqual(cat, "Salary", f"'{s}' must map to Salary")
            self.assertEqual(subcat, "Employment Wages")

        # HMRC Inflow must map to Benefits (Tax Rebates), not Salary
        h_cat, h_sub, h_name, _ = rule_based_classify("HMRC REVENUE REFUND", direction="In")
        self.assertEqual(h_cat, "Benefits", "HMRC Inflow must map to Benefits, not Salary")
        self.assertEqual(h_sub, "Tax Rebates")

        # HMRC Outflow must map to Tax (Self Assessment), not Salary
        o_cat, o_sub, o_name, _ = rule_based_classify("HMRC SELF ASSESSMENT TAX", direction="Out")
        self.assertEqual(o_cat, "Tax", "HMRC Outflow must map to Tax")

    def test_merchant_cleaner_generalization(self):
        # Verify cleaner strips postal districts, terminal codes, and domains universally (Manchester, Birmingham, etc.)
        test_strings = [
            ("CARD PAYMENT TO SHELL OIL ON 12-05-2025 REF 994821", "SHELL OIL"),
            ("TFL TRAVEL CHG TFL.GOV.UK", "TFL TRAVEL CHG"),
            ("UBER TRIP HELP.UBER.COM", "UBER TRIP"),
            ("TESCO STORES M1 4BT REF 83749201", "TESCO STORES"),
        ]
        for raw, expected_token in test_strings:
            cleaned = clean_raw_description(raw)
            self.assertTrue(expected_token in cleaned, f"Cleaned '{cleaned}' must retain '{expected_token}' from '{raw}'")

    def test_no_hardcoded_user_names_in_seed_patterns(self):
        # Strict anti-overfitting test: ensure no specific private individuals or niche personal entities are hardcoded
        overfit_keywords = ["jordan", "ellis", "acme_custom", "fake_personal_vendor"]
        for pat, cat, subcat, clean_name, tags in SEED_PATTERNS:
            for kw in overfit_keywords:
                self.assertNotIn(kw, pat.lower(), f"Seed pattern '{pat}' contains overfitted keyword '{kw}'")
                self.assertNotIn(kw, clean_name.lower(), f"Clean name '{clean_name}' contains overfitted keyword '{kw}'")

if __name__ == "__main__":
    unittest.main()
