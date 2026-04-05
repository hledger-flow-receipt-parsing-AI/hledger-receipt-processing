import copy
import json
import os
import tkinter as tk
from dataclasses import asdict
from datetime import datetime
from pprint import pprint
from typing import Dict, List, Optional

from typeguard import typechecked

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.Config import Config
from hledger_config.config.load_config import (
    raw_receipt_img_filepath_to_cropped,
)
from hledger_core.Currency import Currency
from hledger_config.dir_reading_and_writing import (
    find_receipt_folder_path,
)
from hledger_core.generics.enums import (
    ClassifierType,
    EnumEncoder,
    LogicType,
)
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.management.get_all_hledger_flow_accounts import (
    get_all_accounts,
)
from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (
    HledgerFlowAccountInfo,
)
from hledger_receipt_processing.receipt_transaction_matching.read_receipt import (
    read_receipt_from_json,
)
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.AssetType import AssetType
from hledger_core.TransactionObjects.Posting import TransactionCode
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def manually_make_receipt_labels(
    *,
    config: Config,
    raw_receipt_img_filepaths: List[str],
    labelled_receipts: List[Receipt],
    verbose: bool,
) -> Dict[str, Receipt]:
    receipts: Dict[str, Receipt] = {}

    for receipt_nr, raw_receipt_img_filepath in enumerate(
        raw_receipt_img_filepaths
    ):
        cropped_receipt_img_filepath: str = raw_receipt_img_filepath_to_cropped(
            config=config, raw_receipt_img_filepath=raw_receipt_img_filepath
        )

        # receipt_folder_path: str = create_image_folder(
        #     dataset_path=config.dir_paths.get_path(
        #         "receipt_labels_dir", absolute=True
        #     ),
        #     cropped_receipt_img_filepath=cropped_receipt_img_filepath,
        # )
        receipt_folder_path: str = find_receipt_folder_path(
            dataset_path=config.dir_paths.get_path(
                "receipt_labels_dir", absolute=True
            ),
            cropped_receipt_img_filepath=cropped_receipt_img_filepath,
        )

        # label_filepath: str = os.path.join(receipt_folder_path, "receipt_image_to_obj_label.json")

        # if not os.path.isfile(label_filepath):

        label_filename: str = (
            f"{str(ClassifierType.RECEIPT_IMAGE_TO_OBJ.value)}_{str(LogicType.LABEL.value)}.json"
        )

        label_filepath: str = os.path.join(receipt_folder_path, label_filename)

        if not os.path.isfile(label_filepath):

            hledger_account_infos, csv_transactions_per_account = (
                get_all_accounts(
                    config=config,
                    labelled_receipts=labelled_receipts,
                )
            )
            receipt_label: Receipt = make_receipt_label(
                config=config,
                raw_receipt_img_filepath=raw_receipt_img_filepath,
                cropped_receipt_img_filepath=cropped_receipt_img_filepath,
                hledger_account_infos=hledger_account_infos,
                csv_transactions_per_account=csv_transactions_per_account,
                receipt_nr=receipt_nr,
                total_nr_of_receipts=len(raw_receipt_img_filepaths),
                labelled_receipts=labelled_receipts,
            )
            receipts[raw_receipt_img_filepath] = receipt_label
            # Store the manually generated receipt label.
            export_human_label(
                receipt=receipt_label,
                label_filepath=label_filepath,
                verbose=verbose,
            )
            print(f"Saved manual label to:\n{label_filepath}")
        else:
            receipt_label: Receipt = read_receipt_from_json(
                config=config,
                label_filepath=label_filepath,
                verbose=verbose,
                raw_receipt_img_filepath=raw_receipt_img_filepath,
            )
            receipts[raw_receipt_img_filepath] = receipt_label

    return receipts


@typechecked
def ask_questions(
    *,
    config: Config,
    raw_receipt_img_filepath: str,
    hledger_account_infos: set[HledgerFlowAccountInfo],
    labelled_receipts: List[Receipt],
    prefilled_receipt: Optional[Receipt],
    csv_transactions_per_account: Optional[
        Dict[AccountConfig, Dict[int, List[Transaction]]]
    ] = None,
) -> Receipt:
    """Asks the relevant questions to the user about the receipt to generate
    the labels."""
    from tui_labeller.tuis.urwid.ask_urwid_receipt import (
        build_receipt_from_urwid,
    )

    # Get the asset categories.
    accounts_without_csv: set[str] = set(
        list(
            map(
                lambda asset_account_config: asset_account_config.account.to_string(),
                config.get_account_configs_without_csv(),
            )
        )
    )

    return build_receipt_from_urwid(
        config=config,
        raw_receipt_img_filepath=raw_receipt_img_filepath,
        hledger_account_infos=hledger_account_infos,
        accounts_without_csv=accounts_without_csv,
        labelled_receipts=labelled_receipts,
        prefilled_receipt=prefilled_receipt,
        csv_transactions_per_account=csv_transactions_per_account,
    )


@typechecked
def export_human_label(
    *, receipt: "Receipt", label_filepath: str, verbose: bool = True
) -> None:
    """
    Stores the manually generated Receipt object to a JSON file.

    Args:
        receipt: The Receipt object containing the label data to be stored.
        label_filepath: The full path where the JSON file should be saved.
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(label_filepath), exist_ok=True)

    # Convert the Receipt object to a dictionary with a deep copy
    receipt_dict = copy.deepcopy(asdict(receipt))

    def convert_types(obj):
        """Recursively convert datetime to isoformat, Currency to string, Account to string, and AssetType to string."""
        if isinstance(obj, dict):
            return {key: convert_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return [convert_types(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Currency):
            return obj.value
        elif isinstance(obj, Account):
            return obj.to_string()
        elif isinstance(obj, AssetType):
            return obj.value
        elif isinstance(obj, str):
            return obj
        elif isinstance(obj, int):
            return obj
        elif isinstance(obj, float):
            return obj
        elif isinstance(obj, TransactionCode):
            return obj
        elif obj is None:
            return None
        else:
            raise TypeError(f"Unexpected type:{type(obj)} for:{obj}")
        # return obj

    # Apply recursive conversion
    receipt_dict = convert_types(receipt_dict)

    # Strip runtime-only metadata that does not survive JSON round-trip
    # (tuples become lists after json.load, causing comparison failures).
    def _strip_runtime_keys(obj):
        if isinstance(obj, dict):
            obj.pop("_csv_column_mapping", None)
            for v in obj.values():
                _strip_runtime_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                _strip_runtime_keys(item)

    _strip_runtime_keys(receipt_dict)

    # Convert payment_currency → currency in each transaction dict for
    # backward-compatible JSON format.  On import the "currency" key is
    # consumed by initialize_account_transaction which converts it back to
    # payment_currency when it differs from base_currency.
    def _convert_payment_currency(transaction: dict) -> None:
        """Convert payment_currency → currency in a transaction dict."""
        pay_cur = transaction.pop("payment_currency", None)
        if pay_cur is not None:
            transaction["currency"] = pay_cur
        else:
            # Domestic: use the account's base_currency
            acct = transaction.get("account")
            if isinstance(acct, dict):
                transaction["currency"] = acct.get(
                    "base_currency", ""
                )

    for item_key in ["net_bought_items", "net_returned_items"]:
        item = receipt_dict.get(item_key)
        if not isinstance(item, dict):
            continue
        for transaction in item.get("account_transactions", []):
            if not isinstance(transaction, dict):
                continue
            _convert_payment_currency(transaction)

    # Also convert payment_currency in withdrawal_metadata.source_account_transaction
    wm = receipt_dict.get("withdrawal_metadata")
    if isinstance(wm, dict):
        sat = wm.get("source_account_transaction")
        if isinstance(sat, dict):
            _convert_payment_currency(sat)

    # Validate currency fields in receipt and transactions
    for item_key in ["net_bought_items", "net_returned_items"]:
        item = receipt_dict.get(item_key)
        if not isinstance(item, dict):
            continue
        for transaction in item.get("account_transactions", []):
            if not isinstance(transaction, dict):
                continue
            if not isinstance(transaction.get("currency"), str):
                raise TypeError(
                    "Expected str for currency in AccountTransaction after"
                    " conversion."
                )
            if not isinstance(transaction.get("account"), dict):
                raise TypeError(
                    "Expected dict for account in AccountTransaction after"
                    " conversion."
                )
    printing_receipt: Dict = copy.deepcopy(receipt_dict)
    printing_receipt.pop("config")
    if verbose:
        pprint(printing_receipt)
        input(f"EXPORTING to:\n{label_filepath}")
    with open(label_filepath, "w") as f:
        json.dump(receipt_dict, f, indent=4, cls=EnumEncoder)


@typechecked
def make_receipt_label(
    *,
    config: Config,
    raw_receipt_img_filepath: str,
    cropped_receipt_img_filepath: str,
    hledger_account_infos: set[HledgerFlowAccountInfo],
    receipt_nr: int,
    total_nr_of_receipts: int,
    labelled_receipts: List[Receipt],
    prefilled_receipt: Optional[Receipt] = None,
    csv_transactions_per_account: Optional[
        Dict[AccountConfig, Dict[int, List[Transaction]]]
    ] = None,
) -> Receipt:
    """
    Opens an image, asks the user questions about it, and returns the answers.

    Args:
        img_filepath: The path to the image file.

    Returns:
        A dictionary containing the user's answers to the questions.
        Returns None if there is an issue opening the image.
    """

    from matplotlib import pyplot as plt
    from tensorflow import image as img
    from tensorflow import io

    # Validate cropped image exists before attempting to load
    if not os.path.isfile(cropped_receipt_img_filepath):
        raise FileNotFoundError(
            "Cropped receipt image not found:"
            f" {cropped_receipt_img_filepath}\nPlease run the image cropping"
            " step first (rotate and crop the receipt images).\nRaw image"
            f" path: {raw_receipt_img_filepath}"
        )

    tensor_img = io.read_file(cropped_receipt_img_filepath)
    tensor_img = img.decode_png(tensor_img, channels=3)

    plt.style.use("dark_background")
    plt.ion()

    # For some reason this code attempts to rotate the images. Prevent that.
    # rotated_img = img.rot90(tensor_img, k=nr_of_quarter_turns_cw)
    img_array = tensor_img.numpy()
    plt.figure()
    plt.imshow(img_array, origin="upper")
    plt.title(f"Answer the questions about this receipt in the CLI/TUI")
    plt.axis("off")
    plt.subplots_adjust(bottom=0, top=1, left=0, right=1)

    # Maximize the figure window
    fig_manager = plt.get_current_fig_manager()
    fig_manager.window.attributes(
        "-zoomed", True
    )  # Works on Linux with Tk backend

    # Allow closing the image afterwards.
    root = tk.Tk()  # TODO: See if you can delete.
    root.withdraw()  # TODO: See if you can delete.

    input(
        f"({receipt_nr}/{total_nr_of_receipts}) Can you"
        f" see:{cropped_receipt_img_filepath} (Press [enter] for yes)?"
    )
    receipt: Receipt = ask_questions(
        config=config,
        hledger_account_infos=hledger_account_infos,
        labelled_receipts=labelled_receipts,
        raw_receipt_img_filepath=raw_receipt_img_filepath,
        prefilled_receipt=prefilled_receipt,
        csv_transactions_per_account=csv_transactions_per_account,
    )

    plt.close()
    plt.ioff()
    root.destroy()  # TODO: See if you can delete.
    return receipt
