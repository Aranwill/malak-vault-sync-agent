from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def isolate_rejected_branch_cleanup_for_legacy_reconciliation_tests(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Keep legacy state tests independent from the new remote side effect."""

    if request.node.module.__name__ != "test_proposal_reconciliation":
        return

    module = importlib.import_module(
        "malak_vault_sync.proposal_reconciliation"
    )
    monkeypatch.setattr(
        module,
        "_cleanup_rejected_proposal_branch",
        lambda *args, **kwargs: None,
    )
