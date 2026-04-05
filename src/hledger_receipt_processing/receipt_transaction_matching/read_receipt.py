"""This file takes in a Receipt object of a card purchase. Then it loads the `.csv` of that card, looks into the respective transactions of that year, and finds the matching transaction.

The transaction data from the .csv file is used to correct/overwrite any incorrect labels generated manually.
"""

import json
from datetime import datetime
from pprint import pprint
from typing import Dict, List, Optional, Union

from typeguard import typechecked

from hledger_config.config.Config import Config
from hledger_core.Currency import Currency
from hledger_core.generics.GenericTransactionWithCsv import (
    GenericCsvTransaction,
)
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Address import Address
from hledger_core.TransactionObjects.AssetType import AssetType
from hledger_core.TransactionObjects.ExchangedItem import ExchangedItem
from hledger_core.TransactionObjects.Posting import TransactionCode
from hledger_core.TransactionObjects.Receipt import (
    Receipt,
    WithdrawalMetadata,
)
from hledger_core.TransactionObjects.ShopId import ShopId


@typechecked
def read_receipt_from_json(
    *,
    config: Config,
    label_filepath: str,
    verbose: bool,
    raw_receipt_img_filepath: Optional[str],
) -> Receipt:
    """
    Read a Receipt object from a JSON file.

    Args:
        label_filepath: Path to the JSON file.
        verbose: If True, print the file path and JSON data.

    Returns:
        Receipt object reconstructed from JSON.
    """

    with open(label_filepath) as f:
        data = json.load(f)

    if verbose:
        print(f"Reading receipt from:\n{label_filepath}")
        pprint(data)

    def convert_types(obj):
        """Recursively convert strings to datetime, Currency, Account, Address, and ShopId."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "the_date" and isinstance(value, str):
                    result[key] = datetime.fromisoformat(value)
                elif key == "currency" and isinstance(value, str):
                    result[key] = Currency(value)
                elif key == "account" and isinstance(value, str):
                    result[key] = Account.from_string(value)
                elif key == "asset_type" and isinstance(value, str):
                    result[key] = AssetType(value)
                elif key == "address" and isinstance(value, dict):
                    # Convert address dictionary to Address object
                    result[key] = Address(**convert_types(value))
                elif key == "shop_identifier" and isinstance(value, dict):
                    # Convert shop_identifier dictionary to ShopId object
                    result[key] = ShopId(**convert_types(value))
                else:
                    result[key] = convert_types(value)
            return result
        elif isinstance(obj, list):
            return [convert_types(item) for item in obj]
        return obj

    # Ensure data is a dictionary
    if not isinstance(data, dict):
        raise TypeError(f"Expected a dictionary in JSON file, got {type(data)}")

    converted_data = convert_types(data)
    net_bought_items_dict: Union[None, Dict] = converted_data.pop(
        "net_bought_items"
    )
    net_returned_items_dict: Union[None, Dict] = converted_data.pop(
        "net_returned_items"
    )

    if "raw_img_filepath" not in converted_data.keys():
        if not raw_receipt_img_filepath:
            raise KeyError(
                f"Did not find the {raw_receipt_img_filepath} in the receipt."
            )
        converted_data["raw_img_filepath"] = raw_receipt_img_filepath
    if "config" in converted_data.keys():
        converted_data.pop("config")
        # Config is stored in receipt JSON but we use the provided config instead

    # Convert withdrawal_metadata dict to WithdrawalMetadata object
    wm = converted_data.get("withdrawal_metadata")
    if isinstance(wm, dict):
        sat = wm.get("source_account_transaction")
        if isinstance(sat, dict):
            # Handle currency → payment_currency conversion (same as ExchangedItem import)
            acct_dict = sat.get("account")
            if isinstance(acct_dict, dict):
                if isinstance(acct_dict.get("base_currency"), str):
                    acct_dict["base_currency"] = Currency(
                        acct_dict["base_currency"]
                    )
                sat["account"] = Account(**acct_dict)
            currency_val = sat.pop("currency", None)
            if currency_val is not None:
                if isinstance(currency_val, str):
                    currency_val = Currency(currency_val)
                if currency_val != sat["account"].base_currency:
                    sat["payment_currency"] = currency_val
            sat["the_date"] = converted_data["the_date"]
            # Remove fields not accepted by AccountTransaction
            sat.pop("parent_receipt_category", None)
            wm["source_account_transaction"] = AccountTransaction(**sat)
        converted_data["withdrawal_metadata"] = WithdrawalMetadata(**wm)

    return Receipt(
        config=config,
        # shop_identifier=converted_data["shop_identifier"],
        net_bought_items=convert_to_exchanged_item(
            the_date=converted_data["the_date"],
            net_items_dict=net_bought_items_dict,
            account_transaction_type="account_transactions",
        ),
        net_returned_items=convert_to_exchanged_item(
            the_date=converted_data["the_date"],
            net_items_dict=net_returned_items_dict,
            account_transaction_type="account_transactions",  # TODO: convert to ENUM
        ),
        **converted_data,
    )


@typechecked
def convert_original_transaction_dict(
    original_txn_dict: Dict,
    parent_currency: Optional[Currency] = None,
) -> GenericCsvTransaction:
    """Convert a dictionary to a GenericCsvTransaction object.

    Args:
        original_txn_dict: Dictionary containing GenericCsvTransaction data.
        parent_currency: Currency from parent context to use if not in dict.

    Returns:
        GenericCsvTransaction object.
    """
    # Map 'amount' to 'tendered_amount_out' if needed
    if (
        "amount" in original_txn_dict
        and "tendered_amount_out" not in original_txn_dict
    ):
        original_txn_dict["tendered_amount_out"] = float(
            original_txn_dict["amount"]
        )

    # Set default change_returned if missing
    if "change_returned" not in original_txn_dict:
        original_txn_dict["change_returned"] = 0.0

    # Get currency from dict or parent context
    currency_val = (
        original_txn_dict.get("currency")
        or original_txn_dict.get("base_currency")
        or parent_currency
    )
    if currency_val and isinstance(currency_val, str):
        currency_val = Currency(currency_val)

    # Convert account dict to Account object
    account_val = original_txn_dict.get("account")
    if account_val and isinstance(account_val, dict):
        if isinstance(account_val.get("base_currency"), str):
            account_val["base_currency"] = Currency(
                account_val["base_currency"]
            )
        original_txn_dict["account"] = Account(**account_val)
    elif account_val and isinstance(account_val, str):
        # Account is a string like "at:triodos:checking" - need currency from elsewhere
        parts = account_val.split(":")
        if len(parts) == 3 and currency_val:
            original_txn_dict["account"] = Account(
                base_currency=currency_val,
                account_holder=parts[0],
                bank=parts[1],
                account_type=parts[2],
            )
    elif not account_val:
        # Build Account from top-level fields if account is missing
        account_holder = original_txn_dict.get("account_holder")
        bank = original_txn_dict.get("bank")
        account_type = original_txn_dict.get("account_type")
        if currency_val and account_holder and bank and account_type:
            original_txn_dict["account"] = Account(
                base_currency=currency_val,
                account_holder=account_holder,
                bank=bank,
                account_type=account_type,
            )

    # Convert the_date string to datetime
    if isinstance(original_txn_dict.get("the_date"), str):
        original_txn_dict["the_date"] = datetime.fromisoformat(
            original_txn_dict["the_date"]
        )

    # Convert transaction_code string to TransactionCode enum
    txn_code = original_txn_dict.get("transaction_code")
    if txn_code and isinstance(txn_code, str):
        original_txn_dict["transaction_code"] = (
            TransactionCode.normalize_transaction_code(txn_code)
        )

    # Only keep fields that GenericCsvTransaction accepts
    valid_fields = {
        "account",
        "the_date",
        "tendered_amount_out",
        "change_returned",
        "balance_after",
        "description",
        "other_party_name",
        "other_party_account_name",
        "transaction_code",
        "bic",
        "payment_currency",
        "original_transaction",
        "extra",
    }
    filtered_dict = {
        k: v for k, v in original_txn_dict.items() if k in valid_fields
    }

    return GenericCsvTransaction(**filtered_dict)


@typechecked
def convert_to_exchanged_item(
    *,
    the_date: datetime,
    net_items_dict: Union[None, Dict],
    account_transaction_type: str,
) -> Union[None, ExchangedItem]:
    """
    Convert a dictionary to an ExchangedItem, processing account transactions.

    Args:
        net_items_dict: Dictionary containing ExchangedItem data.
        account_transaction_type: Key for account transactions in the dictionary.

    Returns:
        ExchangedItem object or None if input is None.
    """
    if net_items_dict:
        account_transactions: List[AccountTransaction] = []
        for account_transaction_dict in net_items_dict[
            account_transaction_type
        ]:
            # Convert the 'account' dictionary to an Account object
            account_dict = account_transaction_dict.get("account")

            if account_dict and isinstance(account_dict, dict):
                if (
                    "currency"
                    in account_transaction_dict.keys()
                ):
                    currency_str = account_transaction_dict.pop("currency")
                    payment_currency = Currency(currency_str)
                    base_cur = account_dict.get("base_currency", "")
                    if isinstance(base_cur, str):
                        base_cur = Currency(base_cur)
                    if payment_currency != base_cur:
                        account_transaction_dict["payment_currency"] = payment_currency
                if isinstance(account_dict["base_currency"], str):
                    account_dict["base_currency"] = Currency(
                        account_dict["base_currency"]
                    )

                # TODO: delete this after reformatting receipt label.

                if "asset_category" in account_dict.keys():
                    # TODO: delete this after reformatting receipt label.
                    account_dict.pop("asset_category")

                account_transaction_dict["account"] = Account(**account_dict)
                # Use the transaction's own the_date if present in JSON;
                # fall back to the receipt-level date for older files.
                if "the_date" not in account_transaction_dict:
                    account_transaction_dict["the_date"] = the_date

            # Convert original_transaction dict to GenericCsvTransaction object
            original_txn = account_transaction_dict.get("original_transaction")
            if original_txn and isinstance(original_txn, dict):
                # Get currency from parent context to pass to original_transaction
                parent_currency = account_transaction_dict.get("currency")
                if (
                    not parent_currency
                    and account_dict
                    and isinstance(account_dict, dict)
                ):
                    parent_currency = account_dict.get("base_currency")
                if parent_currency and isinstance(parent_currency, str):
                    parent_currency = Currency(parent_currency)
                account_transaction_dict["original_transaction"] = (
                    convert_original_transaction_dict(
                        original_txn, parent_currency
                    )
                )

            account_transactions.append(
                AccountTransaction(**account_transaction_dict)
            )
        net_items_dict[account_transaction_type] = account_transactions
        return ExchangedItem(**net_items_dict)
    return None
