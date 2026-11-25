"""Each receipt label is matched to bank transactions once per run.

A receipt can reach the matcher under several image paths: every image of
a multi-image receipt maps to it, and separate image groups can resolve to
the same label file.  Linking saves the label file, so a second pass would
work on the stale in-memory receipt and link the same transaction again.
"""

from pathlib import Path
from typing import List

import pytest
from hledger_core.generics.enums import ClassifierType, LogicType
from hledger_core.TransactionObjects.Receipt import Receipt

from hledger_receipt_processing.matching.searching import matching

from test_receipt_not_mine import _config


def _receipt(config, raw_img_filepaths: List[str]) -> Receipt:
    """A receipt carrying only what the matching loop looks at."""
    receipt = Receipt.__new__(Receipt)
    receipt.config = config
    receipt.raw_img_filepaths = raw_img_filepaths
    receipt.net_bought_items = []
    receipt.net_returned_items = []
    return receipt


@pytest.fixture
def matched(monkeypatch) -> List[Receipt]:
    calls: List[Receipt] = []
    monkeypatch.setattr(
        matching, "check_missing_accounts", lambda **kwargs: []
    )
    monkeypatch.setattr(
        matching,
        "match_receipt_items_to_csv_transactions",
        lambda **kwargs: calls.append(kwargs["receipt"]),
    )
    return calls


def _run(config, json_paths_receipt_objs) -> None:
    matching.manage_matching_receipts_to_transactions(
        config=config,
        labelled_receipts=[],
        json_paths_receipt_objs=json_paths_receipt_objs,
        csv_transactions_per_account={},
        models={
            ClassifierType.TRANSACTION_CATEGORY: {LogicType.RULE_BASED: []}
        },
    )


def test_receipt_shared_by_its_images_is_matched_once(
    tmp_path: Path, matched: List[Receipt]
) -> None:
    config = _config(tmp_path)
    receipt = _receipt(config, ["/in/a.jpg", "/in/b.jpg"])
    _run(config, {"/in/a.jpg": receipt, "/in/b.jpg": receipt})
    assert [id(r) for r in matched] == [id(receipt)]


def test_label_read_twice_is_matched_once(
    tmp_path: Path, matched: List[Receipt]
) -> None:
    """Two groups that resolve to the same label file each read it."""
    config = _config(tmp_path)
    first = _receipt(config, ["/in/a.jpg", "/in/b.jpg"])
    second = _receipt(config, ["/in/a.jpg", "/in/b.jpg"])
    _run(config, {"/in/a.jpg": first, "/in/b.jpg": second})
    assert [id(r) for r in matched] == [id(first)]


def test_different_receipts_are_all_matched(
    tmp_path: Path, matched: List[Receipt]
) -> None:
    config = _config(tmp_path)
    first = _receipt(config, ["/in/a.jpg"])
    second = _receipt(config, ["/in/b.jpg"])
    _run(config, {"/in/a.jpg": first, "/in/b.jpg": second})
    assert [id(r) for r in matched] == [id(first), id(second)]
