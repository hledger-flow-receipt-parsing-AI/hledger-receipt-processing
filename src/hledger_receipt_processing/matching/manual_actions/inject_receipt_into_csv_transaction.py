from copy import deepcopy
from decimal import Decimal
from typing import List

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.manual_actions.helper import (
    convert_into_account_transaction_objects,
)
from hledger_receipt_processing.receipt_transaction_matching.compare_transaction_to_receipt import (
    collect_non_csv_transactions,
)
from hledger_core.TransactionObjects.AssetType import AssetType
from hledger_core.TransactionObjects.Receipt import (
    Account,
    AccountTransaction,
    ExchangedItem,
    Receipt,
)
from hledger_core.TransactionTypes.TriodosTransaction import (
    TriodosTransaction,
)


@typechecked
def inject_csv_transaction_to_receipt(
    *,
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

        # Create foreign currency account
        foreign_currency_account: Account = Account(
            base_currency=original_receipt_account_transaction.currency,
            asset_type=AssetType.ASSET,
            asset_category=str(original_receipt_account_transaction.currency),
        )
        # Create foreign currency
        asset_transaction: AccountTransaction = AccountTransaction(
            account=foreign_currency_account,
            currency=original_receipt_account_transaction.account.base_currency,  # Infer currency from receipt
            tendered_amount_out=original_receipt_account_transaction.tendered_amount_out,
            change_returned=original_receipt_account_transaction.change_returned,
        )

        # TODO Integrate the updated receipt transaction and the asset transaction in the receipt.
        # Integrate the updated receipt transaction and the asset transaction into the receipt
        # Append both transactions to the receipt's account_transactions list

        if (
            len(new_receipt.net_bought_items.account_transactions) == 1
            and new_receipt.net_returned_items is None
            or len(new_receipt.net_returned_items.account_transactions) == 0
        ):  # Lazy eval.

            new_receipt.net_bought_items = ExchangedItem(
                quantity=1,
                description=receipt.receipt_category,
                the_date=receipt.the_date,
                account_transactions=convert_into_account_transaction_objects(
                    transactions=[
                        found_csv_transaction,
                        asset_transaction,
                    ]
                ),
            )
        else:
            raise NotImplementedError(
                "Do not yet know how to handle the scenario of multiple"
                " transacted items per receipt for foreign currency withdrawl"
                " receipts."
            )
    else:
        raise NotImplementedError(
            "Do not yet know how to handle a foreign currency withdrawl that"
            " yielded money from the bank account for a receipt that only"
            " contained the foreign retrieved amount."
        )
    return new_receipt


@typechecked
def receipt_already_contains_csv_transaction(
    *, receipt: Receipt, csv_transaction: Transaction
) -> bool:
    # Collect account transactions in receipt.
    if not isinstance(csv_transaction, TriodosTransaction):
        raise TypeError(f"Unsupported csv transaction type:{csv_transaction}")
    receipt_transactions: List[AccountTransaction] = (
        collect_non_csv_transactions(receipt)
    )
    if not receipt_transactions:
        return False

    nr_of_matches: int = 0
    for receipt_transaction in receipt_transactions:
        if receipt_transaction.original_transaction:
            if (
                receipt_transaction.original_transaction.get_hash()
                == csv_transaction.get_hash()
            ):
                nr_of_matches += 1
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
