"""Ingest a folder of documents into the configured Qdrant + database.

    python scripts/ingest.py                       # data/corpus with configs/settings.yaml
    python scripts/ingest.py --dir my_pdfs --reset # wipe the collection first
    COPILOT_QDRANT_URL=http://localhost:6333 DATABASE_URL=postgresql+psycopg://... python scripts/ingest.py
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.config import load_settings, resolve  # noqa: E402
from copilot.pipeline import Copilot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="folder with PDF / md / txt files")
    ap.add_argument("--reset", action="store_true", help="delete the vector collection first")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_settings()
    cp = Copilot(cfg)
    if args.reset:
        cp.store.reset()
    folder = Path(args.dir) if args.dir else resolve(cfg["app"]["corpus_dir"])
    t = time.time()
    res = cp.ingestor.ingest_dir(folder)
    new = [r for r in res if not r.skipped]
    print(f"{len(new)} documents ingested, {len(res) - len(new)} unchanged, "
          f"{sum(r.chunks for r in new)} chunks, {time.time() - t:.1f} s; collection has {cp.store.count()} chunks")


if __name__ == "__main__":
    main()
