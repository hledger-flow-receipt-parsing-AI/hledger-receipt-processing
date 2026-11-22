"""A receipt that is not the user's own is taken out of the bookkeeping
folders and kept, with everything known about it, as AI training data.

Nothing is ever deleted: files are moved, and a failed move is undone.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest
from hledger_config.config.CategorisationConfig import CategorisationConfig
from hledger_config.config.Config import Config
from hledger_config.config.DirPathsConfig import DirPathsConfig
from hledger_config.config.Filenames import FileNames
from hledger_config.config.MatchingAlgoConfig import MatchingAlgoConfig
from hledger_config.config.ReceiptImgConfig import ReceiptImgConfig
from hledger_core.Currency import Currency
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Receipt import Receipt

from hledger_receipt_processing.matching.ask_user_action import (
    ReceiptMatchingAction,
    get_receipt_action,
)
from hledger_receipt_processing.receipts_to_objects import receipt_not_mine
from hledger_receipt_processing.receipts_to_objects.group_images import (
    load_image_grouping,
    save_image_grouping,
)
from hledger_receipt_processing.receipts_to_objects.receipt_not_mine import (
    PARTIAL_LABEL_FILENAME,
    PROVENANCE_FILENAME,
    TRAINING_DATASET_DIRNAME,
    ReceiptNotMine,
    confirm_receipt_not_mine,
    handle_receipt_not_mine,
    move_receipt_to_training_dataset,
    receipt_files,
    training_dataset_dir,
)

ANSWERS = {"date": "2025-01-15 10:30:00", "category": "groceries"}


def _config(tmp_path: Path) -> Config:
    root = tmp_path / "finance"
    for name in (
        "receipt_images_input",
        "receipt_images_processed",
        "receipt_labels",
    ):
        (root / name).mkdir(parents=True)
    (root / "categories.yaml").write_text("groceries: {}\n", encoding="utf-8")
    return Config(
        accounts=[],
        dir_paths=DirPathsConfig(
            root_finance_path=str(root),
            working_subdir="work",
            receipt_images_input_dir="receipt_images_input",
            hledger_plot_dir="plots",
            receipt_images_processed_dir="receipt_images_processed",
            receipt_labels_dir="receipt_labels",
            asset_transaction_csvs_dir="asset_transaction_csvs",
        ),
        file_names=FileNames(
            start_journal_filepath="start.journal",
            root_journal_filename="all.journal",
            tui_label_filename="receipt_image_to_obj_label",
            receipt_img=ReceiptImgConfig(
                processing_metadata_ext=".json",
                rotate="_rotated",
                rotate_ext=".jpg",
                crop="_cropped",
                crop_ext=".jpg",
            ),
            categories_filename="categories.yaml",
        ),
        categorisation=CategorisationConfig(quick=False),
        csv_encoding="utf-8",
        matching_algo=MatchingAlgoConfig(
            days=2,
            amount_range=0.0,
            days_month_swap=False,
            multiple_receipts_per_transaction=False,
        ),
    )


def _root(config: Config) -> Path:
    return Path(config.dir_paths.root_finance_path)


def _make_receipt(config: Config, stem: str) -> str:
    """Create the four files of one photographed receipt; return the path of
    the original image."""
    root = _root(config)
    original = root / "receipt_images_input" / f"{stem}.jpg"
    original.write_text(f"original {stem}")
    processed = root / "receipt_images_processed"
    (processed / f"{stem}_rotated.jpg").write_text(f"rotated {stem}")
    (processed / f"{stem}_cropped.jpg").write_text(f"cropped {stem}")
    (processed / f"{stem}.json").write_text(f'{{"stem": "{stem}"}}')
    return str(original)


def _tree(folder: Path) -> Dict[str, str]:
    """Relative path -> content of every file below *folder*."""
    return {
        str(path.relative_to(folder)): path.read_text()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


# ------------------------------------------------------------------ listing


def test_lists_original_and_processed_files_of_every_image(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    first = _make_receipt(config, "photo_a")
    second = _make_receipt(config, "photo_b")
    files = receipt_files(
        config=config, raw_receipt_img_filepaths=[first, second]
    )
    assert [os.path.basename(path) for path in files] == [
        "photo_a.jpg",
        "photo_a_rotated.jpg",
        "photo_a_cropped.jpg",
        "photo_a.json",
        "photo_b.jpg",
        "photo_b_rotated.jpg",
        "photo_b_cropped.jpg",
        "photo_b.json",
    ]
    assert all(os.path.isabs(path) for path in files)


def test_missing_files_are_left_out(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    os.remove(_root(config) / "receipt_images_processed" / "photo_a_rotated.jpg")
    files = receipt_files(config=config, raw_receipt_img_filepaths=[original])
    assert [os.path.basename(path) for path in files] == [
        "photo_a.jpg",
        "photo_a_cropped.jpg",
        "photo_a.json",
    ]


def test_dataset_folder_is_in_the_finance_root(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert training_dataset_dir(config=config) == str(
        _root(config) / TRAINING_DATASET_DIRNAME
    )


# ------------------------------------------------------------------- moving


def test_moves_every_file_and_keeps_the_typed_answers(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    other = _make_receipt(config, "photo_a_2")  # a different photo

    destination = move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[original],
        partial_answers=ANSWERS,
    )

    root = _root(config)
    assert destination == str(root / TRAINING_DATASET_DIRNAME / "photo_a")
    moved = _tree(Path(destination))
    assert moved["photo_a.jpg"] == "original photo_a"
    assert moved["photo_a_rotated.jpg"] == "rotated photo_a"
    assert moved["photo_a_cropped.jpg"] == "cropped photo_a"
    assert moved["photo_a.json"] == '{"stem": "photo_a"}'

    label = json.loads(moved[PARTIAL_LABEL_FILENAME])
    assert label["complete"] is False
    assert label["answers"] == ANSWERS

    provenance = json.loads(moved[PROVENANCE_FILENAME])
    assert provenance["reason"] == "This receipt is not mine"
    assert provenance["files"]["photo_a.jpg"] == original
    assert provenance["files"]["photo_a_cropped.jpg"] == str(
        root / "receipt_images_processed" / "photo_a_cropped.jpg"
    )
    assert datetime.fromisoformat(provenance["moved_at"])

    # Gone from the bookkeeping folders; the other photo is untouched.
    assert _tree(root / "receipt_images_input") == {
        "photo_a_2.jpg": "original photo_a_2"
    }
    assert sorted(_tree(root / "receipt_images_processed")) == [
        "photo_a_2.json",
        "photo_a_2_cropped.jpg",
        "photo_a_2_rotated.jpg",
    ]
    assert os.path.isfile(other)


def test_all_images_of_a_group_move_together(tmp_path: Path) -> None:
    config = _config(tmp_path)
    first = _make_receipt(config, "photo_a")
    second = _make_receipt(config, "photo_b")

    destination = move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[first, second],
        partial_answers={},
    )

    assert os.path.basename(destination) == "photo_a"  # the prime image
    names = sorted(_tree(Path(destination)))
    assert "photo_a.jpg" in names and "photo_b_cropped.jpg" in names
    assert len(names) == 8 + 2
    assert _tree(_root(config) / "receipt_images_input") == {}


def test_empty_label_folder_is_removed(tmp_path: Path) -> None:
    """The labelling loop creates the label folder before the questions."""
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    label_folder = _root(config) / "receipt_labels" / "abc123"
    label_folder.mkdir()

    move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[original],
        partial_answers=ANSWERS,
        label_folder_path=str(label_folder),
    )
    assert not label_folder.exists()


def test_existing_label_file_moves_too(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    label_folder = _root(config) / "receipt_labels" / "abc123"
    label_folder.mkdir()
    label_file = label_folder / "receipt_image_to_obj_label.json"
    label_file.write_text('{"receipt_category": "groceries"}')

    destination = move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[original],
        partial_answers=ANSWERS,
        label_folder_path=str(label_folder),
    )

    moved = _tree(Path(destination))
    assert moved["receipt_image_to_obj_label.json"] == (
        '{"receipt_category": "groceries"}'
    )
    provenance = json.loads(moved[PROVENANCE_FILENAME])
    assert provenance["files"]["receipt_image_to_obj_label.json"] == str(
        label_file
    )
    assert not label_folder.exists()


def test_existing_dataset_entry_is_never_overwritten(tmp_path: Path) -> None:
    config = _config(tmp_path)
    earlier = _root(config) / TRAINING_DATASET_DIRNAME / "photo_a"
    earlier.mkdir(parents=True)
    (earlier / "photo_a.jpg").write_text("an earlier receipt")
    original = _make_receipt(config, "photo_a")

    destination = move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[original],
        partial_answers={},
    )

    assert os.path.basename(destination) == "photo_a_2"
    assert (earlier / "photo_a.jpg").read_text() == "an earlier receipt"
    assert _tree(Path(destination))["photo_a.jpg"] == "original photo_a"


def test_failed_move_puts_everything_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    root = _root(config)
    before = _tree(root)

    real_move = receipt_not_mine.shutil.move
    calls: List[str] = []

    def fail_on_third(source: str, target: str) -> str:
        calls.append(source)
        if len(calls) == 3:
            raise OSError("disk full")
        return real_move(source, target)

    monkeypatch.setattr(receipt_not_mine.shutil, "move", fail_on_third)
    with pytest.raises(OSError, match="disk full"):
        move_receipt_to_training_dataset(
            config=config,
            raw_receipt_img_filepaths=[original],
            partial_answers=ANSWERS,
        )
    monkeypatch.undo()

    assert _tree(root) == before
    assert not (root / TRAINING_DATASET_DIRNAME / "photo_a").exists()


def test_two_files_with_the_same_name_stop_the_move_before_it_starts(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    label_folder = _root(config) / "receipt_labels" / "abc123"
    label_folder.mkdir()
    (label_folder / "photo_a.json").write_text("clashes with the metadata")
    before = _tree(_root(config))

    with pytest.raises(receipt_not_mine.ReceiptMoveError):
        move_receipt_to_training_dataset(
            config=config,
            raw_receipt_img_filepaths=[original],
            partial_answers={},
            label_folder_path=str(label_folder),
        )
    assert _tree(_root(config)) == before


def test_nothing_to_move_is_an_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    missing = str(_root(config) / "receipt_images_input" / "gone.jpg")
    with pytest.raises(receipt_not_mine.ReceiptMoveError):
        move_receipt_to_training_dataset(
            config=config,
            raw_receipt_img_filepaths=[missing],
            partial_answers={},
        )
    assert not (_root(config) / TRAINING_DATASET_DIRNAME).exists()


def test_handler_moves_and_reports_the_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    destination = handle_receipt_not_mine(
        config=config,
        raw_receipt_img_filepaths=[original],
        partial_answers=ANSWERS,
    )
    assert destination is not None and os.path.isdir(destination)
    assert not os.path.exists(original)
    assert destination in capsys.readouterr().out


def test_handler_reports_a_failed_move_instead_of_crashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """One receipt that cannot be moved must not end the labelling run."""
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    before = _tree(_root(config))

    def refuse(source: str, target: str) -> str:
        raise OSError("read-only file system")

    monkeypatch.setattr(receipt_not_mine.shutil, "move", refuse)
    assert (
        handle_receipt_not_mine(
            config=config,
            raw_receipt_img_filepaths=[original],
            partial_answers=ANSWERS,
        )
        is None
    )
    monkeypatch.undo()

    shown = capsys.readouterr().out
    assert "read-only file system" in shown
    assert "Nothing was changed" in shown
    assert _tree(_root(config)) == before


# ----------------------------------------------------------------- grouping


def test_grouping_file_forgets_the_moved_receipt(tmp_path: Path) -> None:
    config = _config(tmp_path)
    kept = _make_receipt(config, "photo_kept")
    first = _make_receipt(config, "photo_a")
    second = _make_receipt(config, "photo_b")
    save_image_grouping(config=config, groups=[[kept], [first, second]])

    move_receipt_to_training_dataset(
        config=config,
        raw_receipt_img_filepaths=[first, second],
        partial_answers={},
    )

    grouping_file = (
        _root(config) / "receipt_images_processed" / "image_grouping.json"
    )
    assert json.loads(grouping_file.read_text()) == [[kept]]
    assert load_image_grouping(config=config) == [[kept]]


def test_no_grouping_file_is_created_when_there_was_none(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    move_receipt_to_training_dataset(
        config=config, raw_receipt_img_filepaths=[original], partial_answers={}
    )
    assert not (
        _root(config) / "receipt_images_processed" / "image_grouping.json"
    ).exists()


# ------------------------------------------------------------- confirmation


@pytest.mark.parametrize(
    "typed, expected",
    [("y", True), ("Y", True), ("yes", True), ("", False), ("n", False)],
)
def test_confirmation_needs_an_explicit_yes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    typed: str,
    expected: bool,
) -> None:
    config = _config(tmp_path)
    original = _make_receipt(config, "photo_a")
    before = _tree(_root(config))
    monkeypatch.setattr("builtins.input", lambda _prompt="": typed)

    assert (
        confirm_receipt_not_mine(
            config=config, raw_receipt_img_filepaths=[original]
        )
        is expected
    )

    shown = capsys.readouterr().out
    assert original in shown
    assert "photo_a_cropped.jpg" in shown
    assert TRAINING_DATASET_DIRNAME in shown
    assert _tree(_root(config)) == before  # asking moves nothing


def test_exception_carries_the_answers() -> None:
    assert ReceiptNotMine(partial_answers=ANSWERS).partial_answers == ANSWERS
    assert ReceiptNotMine().partial_answers == {}


# --------------------------------------------------------------------- menu


def _menu_arguments() -> dict:
    account = Account(
        base_currency=Currency.EUR,
        account_holder="at",
        bank="triodos",
        account_type="checking",
    )
    when = datetime(2025, 1, 15, 10, 30)
    receipt = Receipt.__new__(Receipt)
    receipt.the_date = when
    return {
        "account": account,
        "search_receipt_account_transaction": AccountTransaction(
            account=account, the_date=when, tendered_amount_out=10.0
        ),
        "receipt": receipt,
    }


def _typing(monkeypatch: pytest.MonkeyPatch, *answers: str) -> List[str]:
    prompts: List[str] = []
    pending = list(answers)

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return pending.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    return prompts


def test_labelling_menu_offers_not_mine_as_option_six(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _typing(monkeypatch, "6")
    action = get_receipt_action(**_menu_arguments(), allow_not_mine=True)
    assert action == ReceiptMatchingAction.NOT_MINE
    assert "6. This receipt is not mine" in prompts[0]
    assert "1-6" in prompts[0]
    assert "5. Widen the amount margin" in prompts[0]


def test_menu_elsewhere_is_unchanged_and_refuses_six(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    prompts = _typing(monkeypatch, "6", "2")
    action = get_receipt_action(**_menu_arguments())
    assert action == ReceiptMatchingAction.CHECK_RECEIPT
    assert "not mine" not in prompts[0]
    assert "1-5" in prompts[0]
    assert "Invalid input" in capsys.readouterr().out


def test_swap_day_and_month_stays_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It was the unlisted number 6; "not mine" took that number."""
    _typing(monkeypatch, "7")
    assert (
        get_receipt_action(**_menu_arguments())
        == ReceiptMatchingAction.SWAP_DAY_AND_MONTH
    )
    _typing(monkeypatch, "7")
    assert (
        get_receipt_action(**_menu_arguments(), allow_not_mine=True)
        == ReceiptMatchingAction.SWAP_DAY_AND_MONTH
    )
