from pathlib import Path

import pytest

from copilot.config import load_settings
from copilot.pipeline import Copilot

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"


def make_settings(**extra):
    over = {"qdrant": {"url": "", "path": ":memory:"}, "database": {"url": "sqlite://"},
            "app": {"auto_ingest": True}}
    for k, v in extra.items():
        over.setdefault(k, {}).update(v)
    return load_settings(overrides=over)


@pytest.fixture(scope="session")
def copilot() -> Copilot:
    cp = Copilot(make_settings())
    cp.ingestor.ingest_dir(CORPUS)
    return cp


@pytest.fixture()
def fresh_copilot() -> Copilot:
    """Separate instance for tests that change the index."""
    cp = Copilot(make_settings())
    cp.ingestor.ingest_dir(CORPUS)
    return cp


@pytest.fixture(scope="session")
def users(copilot):
    return copilot.policy.users
