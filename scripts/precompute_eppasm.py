"""
Batch-precompute EPPASM comparison results for every PJNZ file in PJNZ_DIR.

Usage:
    uv run python scripts/precompute_eppasm.py [--force]
"""
import argparse

import leapfrog_compare.config as config
from leapfrog_compare.eppasm_runner import run_eppasm

PACKAGES = ("eppasm", "eppasm.lf")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Recompute even if a cached CSV already exists.")
    args = parser.parse_args()

    pjnz_files = sorted(config.PJNZ_DIR.expanduser().glob("*.PJNZ"))
    if not pjnz_files:
        print(f"No PJNZ files found in {config.PJNZ_DIR}")
        return

    n_ok = n_failed = 0
    for pjnz_path in pjnz_files:
        for package in PACKAGES:
            print(f"[{pjnz_path.stem}] {package} ...", end=" ", flush=True)
            try:
                run_eppasm(pjnz_path, package, force=args.force)
            except Exception as exc:
                print(f"FAILED: {exc}")
                n_failed += 1
            else:
                print("ok")
                n_ok += 1

    print(f"\n{n_ok} succeeded, {n_failed} failed.")


if __name__ == "__main__":
    main()
