import logging

from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.ask_user_action import ActionDataset
from hledger_receipt_processing.matching.linking.helper import (
    store_updated_receipt_label,
)
from hledger_receipt_processing.matching.manual_actions.inject_transaction_into_receipt import (
    inject_csv_transaction_to_receipt,
    receipt_already_contains_csv_transaction,
)
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Receipt import Receipt

logger = logging.getLogger(__name__)
import logging

from typeguard import typechecked


@typechecked
def auto_link_receipt(
    *,
    action_dataset: ActionDataset,
    original_receipt_account_transaction: AccountTransaction,
    found_csv_transaction: Transaction,
) -> None:
    """
    Auto-link a receipt to a single matching transaction.

    Args:
        receipt: Receipt object to link.
        transaction: Matching transaction.
        account: Account information.
        result: Dictionary to store matching results.
    """
    # Assert the csv_transaction is not yet in the AccountTransaction.
    if receipt_already_contains_csv_transaction(
        receipt=action_dataset.receipt, csv_transaction=found_csv_transaction
    ):
        raise ValueError(
            "Link was already made, csv_transaction is in receipt already."
        )

    updated_receipt: Receipt = inject_csv_transaction_to_receipt(
        config=action_dataset.config,
        original_receipt_account_transaction=original_receipt_account_transaction,
        found_csv_transaction=found_csv_transaction,
        receipt=action_dataset.receipt,
    )

    store_updated_receipt_label(
        latest_receipt=updated_receipt,
        config=action_dataset.config,
    )

    # TODO: Assert the receipt file contains the  injected csv account.
    if not receipt_already_contains_csv_transaction(
        receipt=updated_receipt, csv_transaction=found_csv_transaction
    ):
        updated_receipt.pretty_print_receipt_without_config()
        raise ValueError(
            "Link was not properly made, csv_transaction is not yet in receipt."
        )


    # TODO: Assert the csv_transaction is not yet in the AccountTransaction.

    # TODO: inject the receipt into the csv_transaction.
    # original_receipt_account_transaction.raw_receipt_img_filepath = (
    #     action_dataset.receipt.raw_img_filepath
    # )

    # TODO: export the TriodosTransaction (with raw_receipt_img_filepath) back into the original csv file.

    # TODO: assert the file and transaction contain the raw_receipt_img_filepath
    # Load the receipt from the csv_transaction from file and assert it is the same one as the incoming one.

    # TODO: Store transaction in receipt.
    # TODO: Store receipt link in transaction.

    # 0. Assert the transaction is an account transaction.
    # 1. In the account transaction, add the link to the raw image input path.
    # 2. Write a function to get the Receipt image from the raw input image path and verify you can get that from the transaction.

    # A. In the receipt per transaction (within net_bought_items and net_sold_items)
    # B. Get the receipt transaction in as argument.
    # C. Get a classifier on in which group net bought or net returned the transaction is.
    # D. Ensure you can find that transaction in the receipt.
    # E. In the receipt in the transaction receipt transaction, add the link to the csv transaction (or the transaction itself). E.g. by transaction hash.

    # I. Write a function that returns that CSV transaction based on the info stored in the receipt transaction.
    # II. Write a function that returns that receipt transaction based on the receipt_raw_input_img in the csv_transaction, (by within the receipt, looking at the transactions and finding the hash that matches the hash of the csv_transaction.)

