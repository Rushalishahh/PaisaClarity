"""
Generate frontend-react/public/samples/sample_statement.pdf.

Reuses the synthetic fixture data from scripts/make_test_pdfs.py so the
public sample and the test fixtures stay in sync. The PDF is a normal,
text-based (not password-protected) bordered statement, so the owner can
try the app's PDF upload path with a real file.

Run from the repo root:
    backend\\venv\\Scripts\\python scripts\\make_sample_pdfs.py
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from scripts.make_test_pdfs import HEADER, DATA_ROWS, make_bordered  # noqa: E402

SAMPLES_DIR = os.path.join(REPO, "frontend-react", "public", "samples")


def main():
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    # make_bordered writes "ACME BANK - Account Statement" + the standard
    # 7-column layout using DATA_ROWS (Jan 2026) - identical content to
    # sample_statement.csv, so both should parse to the same transactions.
    make_bordered(os.path.join(SAMPLES_DIR, "sample_statement.pdf"))
    _ = HEADER  # imported for clarity; used inside make_bordered
    print("Done.")


if __name__ == "__main__":
    main()
