import dataclasses
import logging
import os
from pprint import pprint
from typing import Any, Optional, Set, Union

from hledger_config.config.Config import Config
from hledger_config.config.load_config import (
    raw_receipt_img_filepath_to_cropped,
)
from hledger_config.dir_reading_and_writing import create_image_folder
from hledger_core.file_reading_and_writing import assert_file_exists
from hledger_core.generics.enums import ClassifierType, LogicType
from hledger_receipt_processing.receipt_transaction_matching.read_receipt import (
    read_receipt_from_json,
)
from hledger_receipt_processing.receipts_to_objects.make_receipt_labels import (
    export_human_label,
)
from hledger_core.TransactionObjects.Receipt import Receipt

logger = logging.getLogger(__name__)
import logging

from typeguard import typechecked


@typechecked
def get_label_filepath(
    *,
    receipt: Receipt,
    config: Config,
) -> str:
    label_filename: str = (
        # TODO: generalise this and store it in the receipt (even though it is already in the filename.)
        f"{str(ClassifierType.RECEIPT_IMAGE_TO_OBJ.value)}_{str(LogicType.LABEL.value)}.json"
    )

    cropped_receipt_img_filepath: str = raw_receipt_img_filepath_to_cropped(
        config=config, raw_receipt_img_filepath=receipt.raw_img_filepath
    )

    receipt_folder_path: str = create_image_folder(
        dataset_path=config.dir_paths.get_path(
            "receipt_labels_dir", absolute=True
        ),
        cropped_receipt_img_filepath=cropped_receipt_img_filepath,
    )

    label_filepath: str = os.path.join(receipt_folder_path, label_filename)
    return label_filepath


@typechecked
def store_updated_receipt_label(
    *,
    latest_receipt: Receipt,
    config: Config,
) -> None:
    """The incoming receipt arg may be changed by the matching algo, e.g. date correction. The stored_receipt is the original receipt that is loaded from json, (which lead to the incoming receipt through the matching algo), the loaded_receipt is the import of the export of the modified receipt arg."""

    label_filepath: str = get_label_filepath(
        receipt=latest_receipt,
        config=config,
    )
    assert_file_exists(filepath=label_filepath)
    original_receipt: Receipt = read_receipt_from_json(
        config=config,
        label_filepath=label_filepath,
        verbose=False,
        raw_receipt_img_filepath=latest_receipt.raw_img_filepath,
    )

    if original_receipt.__dict__ != latest_receipt.__dict__:
        export_human_label(
            receipt=latest_receipt, label_filepath=label_filepath, verbose=False
        )

        loaded_receipt: Receipt = read_receipt_from_json(
            config=config,
            label_filepath=label_filepath,
            verbose=False,
            raw_receipt_img_filepath=latest_receipt.raw_img_filepath,
        )

        ignore_keys_none = {
            "balance_after",
            "bic",
            "description",
            "extra",
            "other_party_account_name",
            "other_party_name",
            "transaction_code",
            # "original_transaction",  # optional: also ignore this if often None
        }

        if has_diff_and_print(
            dict1=loaded_receipt.__dict__,
            dict2=latest_receipt.__dict__,
            name1="loaded_receipt",
            name2="latest_receipt",
            ignore_keys_none=ignore_keys_none,
            ignore_empty_dict_keys={"extra"},
            ignore_keys={"nr_in_batch", "config", "payment_currency", "_csv_column_mapping"},
        ):

            raise ValueError(
                "The exported receipt is not the same as the updated receipt. "
            )

        if not has_diff_and_print(
            dict1=loaded_receipt.__dict__,
            dict2=original_receipt.__dict__,
            name1="loaded_receipt",
            name2="original_receipt",
            ignore_keys_none=ignore_keys_none,
            ignore_empty_dict_keys={"extra", "nr_in_batch"},
            ignore_keys={"nr_in_batch", "config"},
        ):
            print("loaded")
            pprint(loaded_receipt.get_both_item_types())
            print("original")
            pprint(original_receipt.get_both_item_types())
            raise ValueError(
                "The loaded receipt is the same as the original receipt. "
            )


@typechecked
def has_diff_and_print(
    *,
    dict1,
    dict2,
    name1: str,
    name2: str,
    indent: int = 0,
    path: str = "",
    ignore_keys_none: Union[None, Set[str]],
    ignore_empty_dict_keys: Union[
        None, Set[str]
    ],  # New: keys where {} vs missing is ignored
    ignore_keys: Union[None, Set[str]],
    verbose: Optional[bool] = False,
) -> bool:
    # Debug: print(f"Warning: ignore_keys={ignore_keys}")
    if ignore_keys_none is None:
        ignore_keys_none = set()
    if ignore_empty_dict_keys is None:
        ignore_empty_dict_keys = set()

    prefix = " " * indent
    current_path = path or "root"
    all_keys = sorted(set(dict1.keys()) | set(dict2.keys()))
    differences_found = False

    for key in all_keys:
        key_path = f"{current_path}[{key!r}]"

        # Case: key missing in dict1
        if key not in dict1:
            val2 = dict2[key]

            # Ignore if val2 is None and key is ignorable
            if key in ignore_keys_none and val2 is None:
                continue
            # Ignore if val2 is {} and key is in empty dict ignore list
            if key in ignore_empty_dict_keys and val2 == {}:
                continue
            if ignore_keys and key in ignore_keys:
                continue
            else:
                if verbose:
                    print(
                        f"\nFor: {name2} the last key:{key} with"
                        f" ignore_keys={ignore_keys} of:"
                    )
                    print(
                        f"{prefix}+ {key_path} is missing in:{name1} and is has"
                        " value:"
                    )
                    pprint(val2)
                    print("Return True B")
                differences_found = True

        # Case: key missing in dict2
        elif key not in dict2:
            val1 = dict1[key]

            # Ignore if val1 is None and key is ignorable
            if key in ignore_keys_none and val1 is None:
                continue
            # Ignore if val1 is {} and key is in empty dict ignore list
            if key in ignore_empty_dict_keys and val1 == {}:
                continue
            if ignore_keys and key in ignore_keys:
                continue
            else:
                if verbose:
                    print(
                        f"\nFor: {name1} the last key:{key} with"
                        f" ignore_keys={ignore_keys} of:"
                    )
                    print(
                        f"prefix:{prefix}- {key_path} is missing in:{name2} and"
                        " is has value:"
                    )
                    pprint(val1)
                    print("Return True C")
                differences_found = True

        # Both sides have the key
        else:
            val1, val2 = dict1[key], dict2[key]
            if val1 == val2:
                continue

            # Special: both None → skip
            if val1 is None and val2 is None:
                continue
            if ignore_keys and key in ignore_keys:
                continue
            # One is None, key is ignorable → skip
            if key in ignore_keys_none and (val1 is None or val2 is None):
                continue

            def is_empty_or_none(x):
                return x is None or (isinstance(x, (dict, set)) and len(x) == 0)

            if (
                key in ignore_empty_dict_keys
                and is_empty_or_none(val1)
                and is_empty_or_none(val2)
            ):
                continue
            # One is {}, key in ignore_empty_dict_keys → skip

            # print(f'val={val2}')
            # if key in ignore_empty_dict_keys and (
            #     {val1, val2} == {set(), dict()} or val1 == val2 == {}
            # ):
            #     continue

            # Handle lists
            if isinstance(val1, list) and isinstance(val2, list):
                if len(val1) != len(val2):
                    if verbose:
                        print(
                            f"{prefix}* {key!r} lists have different lengths:"
                            f" {len(val1)} vs {len(val2)}"
                        )
                        print("Return True D")
                    differences_found = True
                    continue

                list_diff = False
                for i, (item1, item2) in enumerate(zip(val1, val2)):
                    if item1 == item2:
                        continue
                    if verbose:
                        print(
                            f"{prefix}* Difference in element of {key!r}[{i}]:"
                        )
                    list_diff |= _compare_values(
                        item1,
                        item2,
                        name1,
                        name2,
                        indent + 4,
                        f"{key_path}[{i}]",
                        ignore_keys_none,
                        ignore_empty_dict_keys,
                        ignore_keys,
                        verbose=verbose,
                    )
                if list_diff:
                    if verbose:
                        print("Return True E")
                    differences_found = True
                continue

            # Recurse into objects
            dict1_val = _to_dict(val1)
            dict2_val = _to_dict(val2)
            if dict1_val is not None and dict2_val is not None:
                # Temporarily increase indent but don't print header yet
                sub_diff = has_diff_and_print(
                    dict1=dict1_val,
                    dict2=dict2_val,
                    name1=name1,
                    name2=name2,
                    indent=indent + 4,
                    path=key_path,
                    ignore_keys_none=ignore_keys_none,
                    ignore_empty_dict_keys=ignore_empty_dict_keys,
                    ignore_keys=ignore_keys,
                    verbose=verbose,
                )
                if sub_diff:
                    # print(f"{prefix}* {key!r} differs^.")
                    if verbose:
                        print("Return True F")
                    differences_found = True
            else:
                if verbose:
                    print(f"{prefix}* {name1}{key_path} =")
                    pprint(val1)
                    print(f"{prefix}  {name2}{key_path} =")
                    pprint(val2)
                    print("Return True G")
                differences_found = True

    if indent == 0 and not differences_found:
        pass  # Silent when no differences
    return differences_found


def _to_dict(obj: Any) -> dict | None:
    if isinstance(obj, dict):
        return obj
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return None


def _compare_values(
    v1,
    v2,
    name1,
    name2,
    indent,
    path,
    ignore_keys_none,
    ignore_empty_dict_keys,
    ignore_keys,
    verbose: Optional[bool] = False,
):
    d1 = _to_dict(v1)
    d2 = _to_dict(v2)
    if d1 is not None and d2 is not None:
        return has_diff_and_print(
            dict1=d1,
            dict2=d2,
            name1=name1,
            name2=name2,
            indent=indent,
            path=path,
            ignore_keys_none=ignore_keys_none,
            ignore_empty_dict_keys=ignore_empty_dict_keys,
            ignore_keys=ignore_keys,
            verbose=verbose,
        )
    else:
        if verbose:
            print(f"{' ' * indent}* {name1}{path} = ")
            pprint(v1)
            print(f"{' ' * indent}  {name2}{path} = ")
            pprint(v2)
            print("Return True A")
        return True
