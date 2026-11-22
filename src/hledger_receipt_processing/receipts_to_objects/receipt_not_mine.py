"""Take a receipt that is not the user's own out of the bookkeeping folders
and keep it, with everything known about it, as AI training data.

The user says so in the labelling menu ("This receipt is not mine").  The
original image, the rotated and cropped images, the processing metadata and
any label file move to ``<finance root>/receipt_training_dataset/<image
name>/``, next to the answers typed so far and a record of where each file
came from.  Files are moved, never deleted, and a failed move is undone.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from hledger_config.config.Config import Config
from typeguard import typechecked

from hledger_receipt_processing.receipts_to_objects.group_images import (
    load_image_grouping,
    save_image_grouping,
)

TRAINING_DATASET_DIRNAME = "receipt_training_dataset"
PARTIAL_LABEL_FILENAME = "partial_label.json"
PROVENANCE_FILENAME = "moved_from.json"
NOT_MINE_REASON = "This receipt is not mine"


class ReceiptNotMine(Exception):
    """Raised out of the labelling questionnaire when the user says the
    receipt is not theirs; carries the answers given so far.

    tui-image-labeller raises it, the labelling loop in
    make_receipt_labels.py catches it and moves the receipt.
    """

    def __init__(
        self, *, partial_answers: Optional[Dict[str, str]] = None
    ) -> None:
        super().__init__(NOT_MINE_REASON)
        self.partial_answers: Dict[str, str] = dict(partial_answers or {})


class ReceiptMoveError(Exception):
    """The receipt cannot be moved; nothing was changed."""


@typechecked
def training_dataset_dir(*, config: Config) -> str:
    """``<finance root>/receipt_training_dataset``."""
    return os.path.join(
        os.path.abspath(config.dir_paths.root_finance_path),
        TRAINING_DATASET_DIRNAME,
    )


@typechecked
def receipt_files(
    *, config: Config, raw_receipt_img_filepaths: List[str]
) -> List[str]:
    """The existing files of a receipt: per image the original, the rotated
    and cropped copies and the processing metadata."""
    processed_dir = config.dir_paths.get_path(
        "receipt_images_processed_dir", absolute=True
    )
    names = config.file_names.receipt_img
    files: List[str] = []
    for raw_path in raw_receipt_img_filepaths:
        stem = Path(raw_path).stem
        candidates = [
            os.path.abspath(raw_path),
            os.path.join(
                processed_dir, f"{stem}{names.rotate}{names.rotate_ext}"
            ),
            os.path.join(processed_dir, f"{stem}{names.crop}{names.crop_ext}"),
            os.path.join(
                processed_dir, f"{stem}{names.processing_metadata_ext}"
            ),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate) and candidate not in files:
                files.append(candidate)
    return files


@typechecked
def _label_files(*, label_folder_path: Optional[str]) -> List[str]:
    if label_folder_path is None or not os.path.isdir(label_folder_path):
        return []
    return [
        os.path.join(label_folder_path, name)
        for name in sorted(os.listdir(label_folder_path))
        if os.path.isfile(os.path.join(label_folder_path, name))
    ]


@typechecked
def _free_destination(*, dataset_dir: str, name: str) -> str:
    """A folder for the receipt that does not exist yet."""
    candidate = os.path.join(dataset_dir, name)
    number = 2
    while os.path.exists(candidate):
        candidate = os.path.join(dataset_dir, f"{name}_{number}")
        number += 1
    return candidate


@typechecked
def confirm_receipt_not_mine(
    *, config: Config, raw_receipt_img_filepaths: List[str]
) -> bool:
    """Show what would be moved and ask; only an explicit yes confirms."""
    files = receipt_files(
        config=config, raw_receipt_img_filepaths=raw_receipt_img_filepaths
    )
    print("\nThis receipt is not mine. These files will be MOVED:")
    for path in files:
        print(f"    {path}")
    print(
        "to the training dataset, with the answers given so far:\n"
        f"    {training_dataset_dir(config=config)}"
    )
    answer = input("Move this receipt out of the bookkeeping? (y/N) ")
    return answer.strip().lower() in ("y", "yes")


@typechecked
def move_receipt_to_training_dataset(
    *,
    config: Config,
    raw_receipt_img_filepaths: List[str],
    partial_answers: Dict[str, str],
    label_folder_path: Optional[str] = None,
) -> str:
    """Move every file of the receipt into its own folder in the training
    dataset and return that folder.

    *label_folder_path* is the receipt's folder in the labels directory: its
    files (a finished label, if any) move too and the emptied folder is
    removed.  Raises ReceiptMoveError before anything is touched when there
    is nothing to move or two files share a name; any failure while moving
    is undone before it is re-raised.
    """
    sources = receipt_files(
        config=config, raw_receipt_img_filepaths=raw_receipt_img_filepaths
    ) + _label_files(label_folder_path=label_folder_path)
    if not sources:
        raise ReceiptMoveError(
            f"No files found for receipt {raw_receipt_img_filepaths}."
        )
    names = [os.path.basename(path) for path in sources]
    reserved = {PARTIAL_LABEL_FILENAME, PROVENANCE_FILENAME}
    clashing = sorted(
        {name for name in names if names.count(name) > 1 or name in reserved}
    )
    if clashing:
        raise ReceiptMoveError(
            f"Cannot move the receipt: file names clash: {clashing}."
        )

    destination = _free_destination(
        dataset_dir=training_dataset_dir(config=config),
        name=Path(raw_receipt_img_filepaths[0]).stem,
    )
    moved: List[Tuple[str, str]] = []
    os.makedirs(destination)
    try:
        for source in sources:
            target = os.path.join(destination, os.path.basename(source))
            shutil.move(source, target)
            moved.append((source, target))
        with open(
            os.path.join(destination, PARTIAL_LABEL_FILENAME),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                {"complete": False, "answers": partial_answers},
                handle,
                indent=2,
            )
        with open(
            os.path.join(destination, PROVENANCE_FILENAME),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                {
                    "reason": NOT_MINE_REASON,
                    "moved_at": datetime.now().isoformat(timespec="seconds"),
                    # File in this folder -> where it came from.
                    "files": {
                        os.path.basename(target): source
                        for source, target in moved
                    },
                },
                handle,
                indent=2,
            )
    except BaseException:
        # Put back what was already moved; the receipt stays as it was.
        for source, target in reversed(moved):
            shutil.move(target, source)
        shutil.rmtree(destination, ignore_errors=True)
        raise

    if label_folder_path is not None and os.path.isdir(label_folder_path):
        if not os.listdir(label_folder_path):
            os.rmdir(label_folder_path)

    # Loading drops the paths that no longer exist; saving makes the
    # grouping file forget the receipt.
    groups = load_image_grouping(config=config)
    if groups is not None:
        save_image_grouping(config=config, groups=groups)
    return destination


@typechecked
def handle_receipt_not_mine(
    *,
    config: Config,
    raw_receipt_img_filepaths: List[str],
    partial_answers: Dict[str, str],
    label_folder_path: Optional[str] = None,
) -> Optional[str]:
    """Move the receipt and tell the user; return the dataset folder.

    A failed move is reported, not raised: nothing was changed, the
    labelling of the other receipts goes on, and this receipt is simply
    asked again on the next run.
    """
    try:
        destination = move_receipt_to_training_dataset(
            config=config,
            raw_receipt_img_filepaths=raw_receipt_img_filepaths,
            partial_answers=partial_answers,
            label_folder_path=label_folder_path,
        )
    except (ReceiptMoveError, OSError) as error:
        print(
            f"\nCould not move the receipt to the training dataset: {error}"
            "\nNothing was changed; the receipt will be asked again next"
            " time.\n"
        )
        return None
    print(f"\nMoved the receipt to the training dataset:\n{destination}\n")
    return destination
