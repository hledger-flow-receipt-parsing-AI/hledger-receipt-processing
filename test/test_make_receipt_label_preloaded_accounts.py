"""Callers that already loaded the accounts pass them to make_receipt_label.

``hledger_preprocessor --edit-receipt`` and the "check receipt" action of
receipt matching both do this.  The parameters were dropped when the
labelling TUI moved account loading into a background thread, and both
callers crashed with ``TypeError: make_receipt_label() got an unexpected
keyword argument 'hledger_account_infos'``.
"""

from pathlib import Path
from typing import Any, Dict

import pytest
from test_receipt_not_mine import _config

from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (  # noqa: E501
    HledgerFlowAccountInfo,
)
from hledger_receipt_processing.receipts_to_objects import make_receipt_labels


class _QuestionsAsked(Exception):
    pass


def test_preloaded_accounts_reach_the_questions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    cropped = tmp_path / "receipt_cropped.jpg"
    cropped.write_bytes(b"not shown in headless mode")
    monkeypatch.setenv("HLEDGER_PREPROCESSOR_HEADLESS", "1")
    monkeypatch.setattr("builtins.input", lambda *_args: "")

    asked_with: Dict[str, Any] = {}

    def fake_ask_questions(**kwargs: Any) -> None:
        asked_with.update(kwargs)
        raise _QuestionsAsked

    monkeypatch.setattr(
        make_receipt_labels, "ask_questions", fake_ask_questions
    )
    account_infos = {
        HledgerFlowAccountInfo(
            account_holder="at", bank="triodos", account_type="checking"
        )
    }
    csv_transactions_per_account: Dict = {}

    with pytest.raises(_QuestionsAsked):
        make_receipt_labels.make_receipt_label(
            config=config,
            raw_receipt_img_filepaths=[str(tmp_path / "receipt.jpg")],
            cropped_receipt_img_filepath=str(cropped),
            hledger_account_infos=account_infos,
            csv_transactions_per_account=csv_transactions_per_account,
            receipt_nr=0,
            total_nr_of_receipts=1,
            labelled_receipts=[],
        )

    assert asked_with["hledger_account_infos"] == account_infos
    assert (
        asked_with["csv_transactions_per_account"]
        is csv_transactions_per_account
    )
