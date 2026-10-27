"""CLI runner for conformance test suite: python -m kohaku.conformance"""

import sys
from .verifier import verify_all


def main() -> int:
    print("=" * 65)
    print("  🦊⚡ KOHAKU CONFORMANCE SUITE (Cross-Client Spec Verification)")
    print("=" * 65)

    results = verify_all()
    all_ok = True
    total_cases = 0

    for suite_name, res in results.items():
        total_cases += res.cases_run
        status = "PASSED" if res.passed else "FAILED"
        bullet = "✓" if res.passed else "✗"
        print(f" {bullet} {suite_name:<28} [{res.cases_run} vectors] -> {status}")
        if not res.passed:
            all_ok = False
            for err in res.errors:
                print(f"     ! {err}")

    print("-" * 65)
    if all_ok:
        print(f"🎉 100% SPEC PARITY: All {total_cases} canonical vectors verified successfully.")
        return 0
    else:
        print("❌ CONFORMANCE FAILURES DETECTED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
