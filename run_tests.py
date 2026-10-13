import sys
sys.stdout.reconfigure(encoding="utf-8")
import unittest
import time

def run_all_tests():
    print("=" * 70)
    print("[Pulse AI] Enterprise Test Suite")
    print("=" * 70)
    start_time = time.time()

    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time
    print("-" * 70)
    print(f"[Time]  Total Execution Time: {elapsed:.2f}s")
    print(f"[Total] Tests Run: {result.testsRun}")
    print(f"[Pass]  Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"[Fail]  Failures: {len(result.failures)}")
    print(f"[Error] Errors: {len(result.errors)}")
    print(f"[Skip]  Skipped: {len(result.skipped)}")
    print("=" * 70)

    if result.wasSuccessful():
        print("[SUCCESS] ALL TESTS PASSED SUCCESSFULLY!")
        return 0
    else:
        print("[FAILURE] SOME TESTS FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
