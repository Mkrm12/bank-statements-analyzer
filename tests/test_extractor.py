"""
Unit and integration tests for extractor.py.
Validates statement parsing, mathematical reconciliation, and non-statement rejection.
"""
import os
import io
import unittest
import pandas as pd
from extractor import extract_statement, process_pdf, detect_bank

PDFS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdfs")

class TestExtractor(unittest.TestCase):

    def test_bank_detection_from_statement_headers(self):
        """Verifies detect_bank identifies supported UK institutions accurately."""
        headers = {
            "HSBC UK. SORT CODE: 40-00-00. ACCOUNT NUMBER: 12345678. STATEMENT. BALANCE: £500.00": "HSBC",
            "SANTANDER. SORT CODE: 09-01-28. ACCOUNT NUMBER: 87654321. STATEMENT. BALANCE: £250.00": "Santander",
            "STARLING BANK. SORT CODE: 60-83-71. ACCOUNT NUMBER: 11223344. STATEMENT. BALANCE: £1,200.00": "Starling",
            "REVOLUT LTD. IBAN: GB12REVO. ACCOUNT NUMBER: 99887766. STATEMENT. BALANCE: £750.00": "Revolut",
            "NATIONWIDE BUILDING SOCIETY. SORT CODE: 07-01-16. ACCOUNT NUMBER: 44556677. STATEMENT. BALANCE: £100.00": "Nationwide",
            "BARCLAYS BANK. SORT CODE: 20-00-00. ACCOUNT NUMBER: 55667788. STATEMENT. BALANCE: £890.00": "Barclays"
        }
        for sample_text, expected_bank in headers.items():
            self.assertEqual(detect_bank(sample_text), expected_bank, f"Failed detecting {expected_bank}")

    def test_process_pdf_wrapper_handles_errors_gracefully(self):
        """Verify process_pdf returns a clean (None, error_msg) tuple on invalid data."""
        corrupt_f = io.BytesIO(b"Not a PDF")
        df, msg = process_pdf(corrupt_f, "test_file.pdf")
        self.assertIsNone(df)
        self.assertTrue(msg.startswith("🚨") or msg.startswith("❌"))

    def test_sample_statement_extraction_and_reconciliation(self):
        """Validates 100-row synthetic Barclays statement extraction, math reconciliation, and types."""
        fname = "synthetic_barclays_current.pdf"
        pdf_path = os.path.join(PDFS_DIR, fname)
        if not os.path.exists(pdf_path):
            self.skipTest(f"Missing sample statement: {pdf_path}")
        with open(pdf_path, "rb") as f:
            df, meta = extract_statement(f)
        self.assertIsNotNone(df, f"Failed to extract {fname}")
        self.assertEqual(meta.get("bank"), "Barclays")
        self.assertTrue(meta.get("reconciled"), f"{fname} failed mathematical reconciliation")
        self.assertEqual(len(df), 100, f"{fname} expected 100 rows, got {len(df)}")
        self.assertIn("Direction", df.columns)
        self.assertIn("Amount", df.columns)
        self.assertTrue((df["Amount"] > 0).all(), "All amounts must be strictly positive")
        self.assertTrue(df["Direction"].isin(["In", "Out"]).all(), "Direction must be 'In' or 'Out'")
        in_sum = df[df["Direction"] == "In"]["Amount"].sum()
        out_sum = df[df["Direction"] == "Out"]["Amount"].sum()
        self.assertAlmostEqual(in_sum, 3854.19, places=2)
        self.assertAlmostEqual(out_sum, 3766.02, places=2)

    def test_non_statement_controls_rejected(self):
        """Verifies corrupt files and non-statement documents (resumes, notes) are rejected."""
        corrupt_f = io.BytesIO(b"Not a valid PDF byte sequence")
        df, meta = extract_statement(corrupt_f)
        self.assertIsNone(df, "Corrupt stream must be rejected")
        self.assertIn("error", meta)

        from unittest.mock import patch, MagicMock
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "CURRICULUM VITAE\nSoftware Engineer\nExperience: Python, SQL"
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open") as mock_open:
            mock_open.return_value.__enter__.return_value = mock_pdf
            df, meta = extract_statement(io.BytesIO(b"%PDF-1.4 mock"))
            self.assertIsNone(df, "Non-statement document must be rejected")
            self.assertIn("error", meta)
            self.assertIn("Not recognised as a supported bank statement", meta["error"])

if __name__ == "__main__":
    unittest.main()
