"""Fixture helpers shared by the Python tests."""
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "test" / "fixtures"


def load_fixture(name):
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def check_fixture(name, data):
    """Compare with the committed fixture, or rewrite it when MOTR_WRITE_FIXTURES=1."""
    path = FIXTURES / name
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    if os.environ.get("MOTR_WRITE_FIXTURES"):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"missing fixture {name}; run MOTR_WRITE_FIXTURES=1 pytest"
    assert json.loads(path.read_text(encoding="utf-8")) == data, f"fixture {name} is stale; regenerate with MOTR_WRITE_FIXTURES=1 pytest and commit"
