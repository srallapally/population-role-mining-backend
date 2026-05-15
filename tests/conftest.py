# backend/tests/conftest.py
import os
import sys

import pytest
from data import store

# Ensure backend/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(autouse=True)
def load_fixtures(monkeypatch):
    from data import loader
    import config

    fixture_path = os.path.join(FIXTURES, "entitlements.csv")

    monkeypatch.setattr(config, "IDENTITIES_FILE", os.path.join(FIXTURES, "identities.csv"))
    monkeypatch.setattr(config, "ENTITLEMENTS_FILE", fixture_path)
    monkeypatch.setattr(config, "ASSIGNMENTS_FILE", os.path.join(FIXTURES, "assignments.csv"))

    store.clear_all()
    loader.load_all()
