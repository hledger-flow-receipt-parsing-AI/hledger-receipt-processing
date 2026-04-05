import json
import os
from typing import Dict, List, Optional, Tuple

from typeguard import typechecked

from hledger_config.config.Config import Config
from hledger_config.config.load_config import (
    raw_receipt_img_filepath_to_cropped,
)
from hledger_config.dir_reading_and_writing import (
    get_receipt_folder_name,
)
from hledger_core.generics.enums import ClassifierType, LogicType
from hledger_core.helper import assert_dir_exists, get_images_in_folder
from hledger_receipt_processing.receipts_to_objects.make_receipt_labels import (
    export_human_label,
)
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def load_existing_receipt_labels_via_images(
    *,
    config: Config,
) -> Dict[Tuple[str, str], Receipt]:

    raw_receipt_img_filepaths: List[str] = get_images_in_folder(
        folder_path=config.dir_paths.get_path(
            "receipt_images_input_dir", absolute=True
        )
    )

    receipt_per_raw_img_filepath: Dict[Tuple[str, str], Receipt] = {}
    for receipt_nr, raw_receipt_img_filepath in enumerate(
        raw_receipt_img_filepaths
    ):
        cropped_receipt_img_filepath: str = raw_receipt_img_filepath_to_cropped(
            config=config, raw_receipt_img_filepath=raw_receipt_img_filepath
        )

        if not os.path.isfile(cropped_receipt_img_filepath):
            continue

        receipt_folder_name: str = get_receipt_folder_name(
            cropped_receipt_img_filepath=cropped_receipt_img_filepath
        )

        receipt_labels_dir: str = config.dir_paths.get_path(
            "receipt_labels_dir", absolute=True
        )

        receipt_folder_path: str = os.path.join(
            receipt_labels_dir, receipt_folder_name
        )
        # receipt_folder_path: str = create_image_folder(
        #     dataset_path=config.dir_paths.get_path(
        #         "receipt_labels_dir", absolute=True
        #     ),
        #     cropped_receipt_img_filepath=cropped_receipt_img_filepath,
        # )

        label_filename: str = (
            f"{str(ClassifierType.RECEIPT_IMAGE_TO_OBJ.value)}_{str(LogicType.LABEL.value)}.json"
        )

        label_filepath: str = os.path.join(receipt_folder_path, label_filename)

        if os.path.isfile(path=label_filepath):
            with open(label_filepath, encoding=config.csv_encoding) as f:
                receipt_data = json.load(f)
                if "raw_img_filepath" not in receipt_data.keys():
                    receipt_data["raw_img_filepath"] = raw_receipt_img_filepath
                if "config" in receipt_data.keys():
                    receipt_data.pop("config")
                receipt = Receipt(
                    config=config, **receipt_data
                )  # Assuming Receipt is a dataclass or similar
                receipt_per_raw_img_filepath[
                    (raw_receipt_img_filepath, label_filepath)
                ] = receipt
    return receipt_per_raw_img_filepath


@typechecked
def load_receipts_from_dir(*, config: Config) -> List[Receipt]:
    """
    Load all Receipt objects from the receipt labels directory.

    Args:
        config: Configuration object containing directory paths

    Returns:
        List of Receipt objects loaded from the labels directory
    """

    # Ensure the labels directory exists
    abs_receipt_dir_path: str = config.dir_paths.get_path(
        "receipt_labels_dir", absolute=True
    )
    assert_dir_exists(dirpath=abs_receipt_dir_path)

    receipts: List[Receipt] = []
    label_files = get_files_in_folder(
        folder_path=abs_receipt_dir_path,
        file_name=config.file_names.tui_label_filename,
        extensions=[".json"],  # Assuming labels are stored as JSON files
    )

    img_receipts: Dict[Tuple[str, str], Receipt] = (
        load_existing_receipt_labels_via_images(config=config)
    )

    for label_filepath in label_files:
        # input(f'label_filepath={label_filepath}')
        with open(label_filepath, encoding=config.csv_encoding) as f:
            receipt_data = json.load(f)
            if "raw_img_filepath" not in receipt_data.keys():
                found_label: bool = False
                for (
                    raw_receipt_img_filepath,
                    other_label_filepath,
                ) in img_receipts.keys():
                    if label_filepath == other_label_filepath:
                        # receipt_data
                        receipt_data["raw_img_filepath"] = (
                            raw_receipt_img_filepath
                        )
                        if "config" in receipt_data.keys():
                            receipt_data.pop("config")
                        receipt = Receipt(config=config, **receipt_data)
                        found_label = True

                        export_human_label(
                            receipt=receipt, label_filepath=other_label_filepath
                        )
                if not found_label:
                    raise FileNotFoundError(f" did not find:{label_filepath}")
            else:
                if "config" in receipt_data.keys():
                    receipt_data.pop("config")
                receipt = Receipt(config=config, **receipt_data)
                receipts.append(receipt)
        # if receipt_data["the_date"] == "2024-12-20T20:31:00":
        #     pprint(receipt)
        #     # input(f'{receipt_data.keys()}')
        #     raise ValueError("FOUDN RECEIPT")
    return receipts


@typechecked
def get_files_in_folder(
    *,
    folder_path: str,
    file_name: Optional[str] = None,
    extensions: Optional[List[str]] = None,
) -> List[str]:
    """
    Retrieve a list of file paths in the specified folder and its subdirectories,
    optionally filtered by file name and/or file extensions.

    Args:
        folder_path: Path to the directory to scan for files
        file_name: Optional specific file name to match (e.g., 'hello.json').
                   If None, no file name filtering is applied.
        extensions: Optional list of file extensions to filter (e.g., ['.jpg', '.json']).
                   If None, no extension filtering is applied.

    Returns:
        List of absolute file paths for files matching the criteria in the folder and its subdirectories
    """
    # Ensure the directory exists
    assert_dir_exists(dirpath=folder_path)

    # Initialize empty list for file paths
    file_paths: List[str] = []
    # Walk through the folder and its subdirectories
    for root, _, files in os.walk(folder_path):
        for fname in files:
            file_path = os.path.join(root, fname)

            # Verify it's a file
            if os.path.isfile(file_path):
                # Check file name if provided

                for extension in extensions:
                    if fname == f"{file_name}{extension}":
                        # Include file if it matches both criteria
                        file_paths.append(file_path)

    return file_paths
