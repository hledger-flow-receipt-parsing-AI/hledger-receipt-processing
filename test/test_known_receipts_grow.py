"""A receipt labelled in this run is known to the receipts after it.

The shop address list of the questionnaire is built from the receipts it
is given; with only the labels of earlier runs, a shop entered by hand on
one receipt was missing from the list of the next until the TUI was
restarted.  All data here is invented.
"""

from pathlib import Path
from typing import List

from hledger_core.TransactionObjects.Receipt import Receipt

from hledger_receipt_processing.receipts_to_objects import make_receipt_labels

from test_receipt_not_mine import _config, _make_receipt


def _receipt(name: str) -> Receipt:
    receipt = Receipt.__new__(Receipt)
    receipt.receipt_category = name
    return receipt


def _label_all(monkeypatch, config, image_groups, labelled_receipts):
    """Run the labelling loop with a questionnaire that answers at once;
    return what each receipt's questionnaire was given and what it made."""
    given: List[List[Receipt]] = []
    made: List[Receipt] = []

    def answer(**kwargs) -> Receipt:
        given.append(list(kwargs["labelled_receipts"]))
        made.append(_receipt(f"made {len(made)}"))
        return made[-1]

    monkeypatch.setattr(make_receipt_labels, "make_receipt_label", answer)
    monkeypatch.setattr(
        make_receipt_labels, "export_human_label", lambda **kwargs: None
    )
    monkeypatch.setattr(
        make_receipt_labels, "start_preload_threads", lambda *t: [None, None]
    )
    make_receipt_labels.manually_make_receipt_labels(
        config=config,
        image_groups=image_groups,
        labelled_receipts=labelled_receipts,
        verbose=False,
    )
    return given, made


def test_the_next_receipt_knows_the_one_labelled_before_it(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    first = _make_receipt(config, "20240101_100000")
    second = _make_receipt(config, "20240101_100100")
    third = _make_receipt(config, "20240101_100200")
    earlier = _receipt("labelled in an earlier run")

    given, made = _label_all(
        monkeypatch, config, [[first], [second], [third]], [earlier]
    )

    assert given[0] == [earlier]
    assert given[1] == [earlier, made[0]]
    assert given[2] == [earlier, made[0], made[1]]


def test_the_callers_list_is_left_as_it_was(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    first = _make_receipt(config, "20240101_100000")
    earlier = _receipt("labelled in an earlier run")
    labelled_receipts = [earlier]

    _label_all(monkeypatch, config, [[first]], labelled_receipts)

    assert labelled_receipts == [earlier]


def test_a_skipped_receipt_gets_no_label_and_the_loop_goes_on(
    tmp_path: Path, monkeypatch
) -> None:
    from tui_labeller.tuis.urwid.skip_receipt import ReceiptSkipped

    config = _config(tmp_path)
    first = _make_receipt(config, "20240101_100000")
    second = _make_receipt(config, "20240101_100100")
    asked_to_offer_skip: List[bool] = []
    exported: List[Receipt] = []
    labelled = _receipt("labelled after the skip")

    def answer(**kwargs) -> Receipt:
        asked_to_offer_skip.append(kwargs["allow_skip"])
        if kwargs["raw_receipt_img_filepaths"] == [first]:
            raise ReceiptSkipped()
        return labelled

    monkeypatch.setattr(make_receipt_labels, "make_receipt_label", answer)
    monkeypatch.setattr(
        make_receipt_labels,
        "export_human_label",
        lambda **kwargs: exported.append(kwargs["receipt"]),
    )
    monkeypatch.setattr(
        make_receipt_labels, "start_preload_threads", lambda *t: [None, None]
    )

    receipts = make_receipt_labels.manually_make_receipt_labels(
        config=config,
        image_groups=[[first], [second]],
        labelled_receipts=[],
        verbose=False,
    )

    assert asked_to_offer_skip == [True, True]
    assert exported == [labelled]
    assert receipts == {second: labelled}
