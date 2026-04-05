from copy import deepcopy
from decimal import Decimal
from pprint import pprint
from typing import List, Tuple

from typeguard import typechecked

from hledger_config.config import AccountConfig
from hledger_config.config.Config import Config
from hledger_config.config.helper import get_account_config
from hledger_core.generics.GenericTransactionWithCsv import (
    GenericCsvTransaction,
)
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.linking.helper import has_diff_and_print
from hledger_receipt_processing.receipt_transaction_matching.compare_transaction_to_receipt import (
    collect_non_csv_transactions,
)
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.ExchangedItem import ExchangedItem
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def inject_csv_transaction_to_receipt(
    *,
    config: Config,
    original_receipt_account_transaction: AccountTransaction,
    found_csv_transaction: Transaction,
    receipt: Receipt,
) -> Receipt:
    """
    Injects a bank transaction into a Receipt object, linking it to the provided bank details.
    Assumes the provided amount is already in the receipt's currency (e.g., pounds).

    Args:
        receipt: The Receipt object to inject the transaction into.
        bank_account_holder_name: The name of the account holder.
        bank_name: The name of the bank.
        bank_account_type: The type of bank account (e.g., 'checking', 'savings').
        amount: The amount paid in the receipt's currency (e.g., ~103 pounds).
        amount_returned: The amount returned in the receipt's currency (default 0.0).

    Returns:
        Receipt: A new Receipt object with the updated transaction details.

    Raises:
        ValueError: If the transaction details are invalid or do not match the receipt's total.
        TypeError: If the account type is invalid.
    """
    # Create a deep copy of the original receipt to avoid modifying it.
    new_receipt = deepcopy(receipt)

    # Create an Account object for the bank transaction.
    if float(
        Decimal(str(original_receipt_account_transaction.tendered_amount_out))
        - Decimal(str(original_receipt_account_transaction.change_returned))
        > 0
    ):

        # This assumes that the updated transaction contains the the original csv_bank account and the amount payed (and 0 change returned) in the currency of that original csv bank account.
        new_receipt: Receipt = (
            find_matching_receipt_transaction_and_inject_csv_transaction(
                config=config,
                receipt=new_receipt,
                original_receipt_account_transaction=original_receipt_account_transaction,
                found_csv_transaction=found_csv_transaction,
            )
        )
    else:
        raise NotImplementedError(
            "Do not yet know how to handle a foreign currency withdrawl that"
            " yielded money from the bank account for a receipt that only"
            " contained the foreign retrieved amount."
        )
    return new_receipt


@typechecked
def should_convert_faulty_account_transaction(
    *,
    config: Config,
    receipt_tnx: AccountTransaction,
    csv_tnx: GenericCsvTransaction,
) -> bool:
    if isinstance(receipt_tnx, AccountTransaction) and isinstance(
        csv_tnx, GenericCsvTransaction
    ):
        account_config: AccountConfig = get_account_config(
            config=config, account=receipt_tnx.account
        )
        if account_config.has_input_csv():
            return True
    return False


@typechecked
def convert_tnx_type_if_needed(
    *,
    config: Config,
    receipt: Receipt,
    csv_tnx: GenericCsvTransaction,
    receipt_account_transaction: Transaction,
) -> Tuple[bool, Receipt]:
    has_replaced: bool = False
    if isinstance(receipt_account_transaction, AccountTransaction):

        copied_receipt: Receipt = deepcopy(receipt)

        # Use the structure from get_all_transactions_from_receipt to find and replace the reference
        bought_items = (
            [receipt.net_bought_items]
            if isinstance(receipt.net_bought_items, ExchangedItem)
            else receipt.net_bought_items if receipt.net_bought_items else []
        )
        returned_items = (
            [receipt.net_returned_items]
            if isinstance(receipt.net_returned_items, ExchangedItem)
            else (
                receipt.net_returned_items if receipt.net_returned_items else []
            )
        )
        for item in bought_items + returned_items:
            for i, receipt_tnx in enumerate(item.account_transactions):

                if Transaction.get_hash(receipt_tnx) == Transaction.get_hash(
                    csv_tnx
                ):
                    if should_convert_faulty_account_transaction(
                        config=config,
                        receipt_tnx=receipt_tnx,
                        csv_tnx=csv_tnx,
                    ):
                        item.account_transactions[i] = csv_tnx
                        has_replaced = True
                    else:
                        raise SystemError("SHOULD CONVERT BUT DID NOT")

        if not has_replaced:
            raise ValueError(f"Should have replaced transaction.")

        if receipt.net_bought_items and not has_diff_and_print(
            dict1=copied_receipt.net_bought_items.__dict__,
            dict2=receipt.net_bought_items.__dict__,
            name1="original_receipt",
            name2="receipt_with_tnx_replaced",
            ignore_keys_none=None,
            ignore_empty_dict_keys=None,
        ):
            raise ValueError("Did not find receipt diff after changing tnx.")

        if receipt.net_returned_items and not has_diff_and_print(
            dict1=copied_receipt.net_returned_items.__dict__,
            dict2=receipt.net_returned_items.__dict__,
            name1="original_receipt",
            name2="receipt_with_tnx_replaced",
            ignore_keys_none=None,
            ignore_empty_dict_keys=None,
        ):
            raise ValueError("Did not find receipt diff after changing tnx.")
        print()
        return has_replaced, receipt
    else:
        return has_replaced, receipt


@typechecked
def find_matching_receipt_transaction_and_inject_csv_transaction(
    *,
    config: Config,
    receipt: Receipt,
    original_receipt_account_transaction: AccountTransaction,
    found_csv_transaction: Transaction,
) -> Receipt:
    if receipt_already_contains_csv_transaction(
        receipt=receipt, csv_transaction=found_csv_transaction
    ):
        raise SystemError(
            "Should not try to add transaction that is already added."
        )
    else:
        # Inject the csv_transaction into the receipt transaction.
        has_injected: bool = False
        all_account_transactions: List[AccountTransaction] = (
            collect_non_csv_transactions(receipt=receipt)
        )
        for receipt_account_transaction in all_account_transactions:
            
            if Transaction.get_hash(
                receipt_account_transaction
            ) == Transaction.get_hash(original_receipt_account_transaction):
                # if receipt_account_transaction.__eq__(
                #     original_receipt_account_transaction
                # ):
                object.__setattr__(
                    receipt_account_transaction,
                    "original_transaction",
                    found_csv_transaction,
                )
                has_injected = True
        if not has_injected:
            pprint(receipt)
            print(
                f"original_receipt_account_transaction={original_receipt_account_transaction}"
            )
            print(f"found_csv_transaction={found_csv_transaction}")
            raise SystemError("Should have injected by now.")

        # Assert the csv_transaction has been injected into the receipt.
        # TODO: assert that the original csv transaction is found within receipt.

        if not receipt_already_contains_csv_transaction(
            receipt=receipt, csv_transaction=found_csv_transaction
        ):
            pprint(receipt)
            raise NotImplementedError(
                "The csv_transaction should have been found by now."
            )
    return receipt


@typechecked
def receipt_already_contains_csv_transaction(
    *, receipt: Receipt, csv_transaction: Transaction
) -> bool:
    # Collect account transactions in receipt.
    if not isinstance(csv_transaction, Transaction):
        raise TypeError(f"Unsupported csv transaction type:{csv_transaction}")
    receipt_transactions: List[AccountTransaction] = (
        collect_non_csv_transactions(receipt)
    )
    if not receipt_transactions:
        return False

    nr_of_matches: int = 0
    for receipt_transaction in receipt_transactions:
        if receipt_transaction.original_transaction:
            if not (
                isinstance(
                    receipt_transaction.original_transaction,
                    GenericCsvTransaction,
                )
                or isinstance(
                    receipt_transaction.original_transaction, AccountTransaction
                )
            ):
                raise TypeError(
                    "Found unexpected"
                    f" type:{receipt_transaction.original_transaction}"
                )
            if (
                receipt_transaction.original_transaction.get_hash()
                == csv_transaction.get_hash()
            ):
                nr_of_matches += 1
        else:
            # Expected when checking before linking - receipt_transaction has no original yet
            pass
    if nr_of_matches == 1:
        return True
    elif nr_of_matches > 1:
        raise ValueError(
            "Found the same csv transaction more than once in single receipt."
        )
    elif nr_of_matches == 0:
        return False
    else:
        raise SystemError(
            "Should not be able to reach this state, perhas rad particles or"
            " debugging altered state mid computation."
        )
