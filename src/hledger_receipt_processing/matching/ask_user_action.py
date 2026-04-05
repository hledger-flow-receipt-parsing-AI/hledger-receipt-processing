import logging
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Union

from typeguard import typechecked

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_core.Currency import Currency
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.linking.helper import (
    store_updated_receipt_label,
)
from hledger_receipt_processing.matching.manual_actions.create_seach_transaction import (
    convert_search_transaction_with_csv_currency,
)
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Receipt import Receipt

logger = logging.getLogger(__name__)

from hledger_core.date_extractor import can_swap_day_and_month
from hledger_receipt_processing.matching.manual_actions.create_seach_transaction import (
    convert_search_transaction_with_csv_currency,
)
from hledger_receipt_processing.matching.manual_actions.widen_amount_range import (
    widen_amount_range,
)
from hledger_receipt_processing.matching.manual_actions.widen_date_range import (
    widen_date_range,
)


@dataclass
class ActionDataset:
    receipt: Receipt
    account: Account
    labelled_receipts: List[Receipt]
    search_receipt_account_transaction: AccountTransaction
    config: Config
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ]
    ai_models_tnx_classification: List
    rule_based_models_tnx_classification: List

    original_receipt_account_transaction: Optional[AccountTransaction] = None
    original_receipt: Optional[Receipt] = None


@dataclass
class AlternateCurrencyWithdrawl:
    from_currency: Currency
    conversion_ratio_1_from_to: float


class ReceiptMatchingAction(Enum):
    ALTERNATE_CURRENCY_WITHDRAWL = "1"
    CHECK_RECEIPT = "2"
    CHECK_TRANSACTIONS = "3"
    WIDEN_DATE = "4"
    WIDEN_AMOUNT = "5"
    SWAP_DAY_AND_MONTH = "6"


class ActionValuePair:
    def __init__(
        self,
        action: ReceiptMatchingAction,
        values: Union[AlternateCurrencyWithdrawl, Receipt, float, bool],
    ):
        self.action: ReceiptMatchingAction = action
        self.values: Union[AlternateCurrencyWithdrawl, Receipt, float, bool] = (
            values
        )

        if action == ReceiptMatchingAction.ALTERNATE_CURRENCY_WITHDRAWL:
            if not isinstance(values, AlternateCurrencyWithdrawl):
                raise TypeError(
                    "For the ALTERNATE_CURRENCY_WITHDRAWL action, the values"
                    " stored from the user interaction should be of"
                    f" class:{AlternateCurrencyWithdrawl},"
                    f" got:{type(values)} with content:{values}"
                )
        elif action == ReceiptMatchingAction.CHECK_RECEIPT:
            if not isinstance(values, Receipt):
                raise TypeError(
                    "For the CHECK_RECEIPT action, the values stored from the"
                    f" user interaction should be of class:{Receipt},"
                    f" got:{type(values)} with content:{values}"
                )
        elif action == ReceiptMatchingAction.CHECK_TRANSACTIONS:
            raise NotImplementedError("Did not implement this yet.")
        elif action == ReceiptMatchingAction.WIDEN_DATE:
            if not isinstance(values, float):
                raise TypeError(
                    "For the WIDEN_DATE action, the values stored from the"
                    " user interaction should be a float,"
                    f" got:{type(values)} with content:{values}"
                )
        elif action == ReceiptMatchingAction.WIDEN_AMOUNT:
            if not isinstance(values, float):
                raise TypeError(
                    "For the WIDEN_DATE action, the values stored from the"
                    " user interaction should be a float,"
                    f" got:{type(values)} with content:{values}"
                )

        elif action == ReceiptMatchingAction.SWAP_DAY_AND_MONTH:
            if not isinstance(values, bool):
                raise TypeError(
                    "For the SWAP_DAY_AND_MONTH action, the values stored from"
                    " the user interaction should be a bool,"
                    f" got:{type(values)} with content:{values}"
                )
        else:
            raise ValueError(f"Not a supported action:{action}")


def apply_action(
    *,
    action_dataset: ActionDataset,
    action_value: ActionValuePair,
) -> ActionDataset:
    # Initialise the modifiable objects with the originals.
    updated_search_receipt_account_transaction: AccountTransaction = (
        action_dataset.search_receipt_account_transaction
    )
    updated_config: Config = action_dataset.config
    modified_receipt: Receipt = action_dataset.receipt

    if (
        action_value.action
        == ReceiptMatchingAction.ALTERNATE_CURRENCY_WITHDRAWL
    ):

        action_dataset.original_receipt_account_transaction = (
            updated_search_receipt_account_transaction
        )
        # Call search algo again with estimated euros. Preferably add a factor 0.05 to the amount ratio.
        updated_search_receipt_account_transaction: AccountTransaction = (
            convert_search_transaction_with_csv_currency(
                search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
                from_currency=action_value.values.from_currency,
                conversion_ratio_1_from_to=action_value.values.conversion_ratio_1_from_to,
            )
        )

        # The transaction pair (bank csv + foreighn currency asset) should only be injected into the receipt if (and after) a single match is found.

    elif action_value.action == ReceiptMatchingAction.CHECK_RECEIPT:
        modified_receipt: Receipt = action_value.values
        if is_new_transaction(
            updated_receipt=modified_receipt,
            search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
        ):

            updated_search_receipt_account_transaction: AccountTransaction = (
                get_single_account_transaction(updated_receipt=modified_receipt)
            )
            store_updated_receipt_label(
                latest_receipt=modified_receipt, config=action_dataset.config
            )
            input(f"updated receipt!")
            if modified_receipt.__dict__ == action_dataset.receipt.__dict__:
                raise ValueError(
                    f"Modified receipt should not equal the action_dataset"
                    f" receipt yet."
                )
            else:
                action_dataset.original_receipt = deepcopy(
                    action_dataset.receipt
                )

    elif action_value.action == ReceiptMatchingAction.CHECK_TRANSACTIONS:
        raise NotImplementedError("Did not implement this yet.")
    elif action_value.action == ReceiptMatchingAction.WIDEN_DATE:
        additional_days: int = action_value.values
        updated_config: Config = widen_date_range(
            config=action_dataset.config,
            additional_days=additional_days,
        )
    elif action_value.action == ReceiptMatchingAction.WIDEN_AMOUNT:

        abs_additive_widening_fraction: float = action_value.values
        updated_config: Config = widen_amount_range(
            config=action_dataset.config,
            abs_additive_widening_fraction=abs_additive_widening_fraction,
        )
    elif action_value.action == ReceiptMatchingAction.SWAP_DAY_AND_MONTH:
        if (
            can_swap_day_and_month(some_date=action_dataset.receipt.the_date)
            and action_dataset.original_receipt_account_transaction is None
        ):

            swapped_date = action_value.values
            modified_receipt: Receipt = deepcopy(action_dataset.receipt)
            modified_receipt.the_date = swapped_date
        else:
            raise ValueError(
                "Cannot swap month and day if it is not the first modification."
            )

    else:
        raise ValueError(f"Not a supported action:{action_value.action}")

    # Store the updated object for the next action.
    action_dataset.search_receipt_account_transaction = deepcopy(
        updated_search_receipt_account_transaction
    )
    action_dataset.config = deepcopy(updated_config)
    action_dataset.receipt = deepcopy(modified_receipt)
    return action_dataset


def get_receipt_action(
    *,
    account: Account,
    search_receipt_account_transaction: AccountTransaction,
    receipt: Receipt,
) -> ReceiptMatchingAction:
    """
    Prompts the user to select an action for a receipt with no matches found and returns the corresponding action.
    Re-prompts if the input is not a valid number (1-5).

    Args:
        account_key (str): The account identifier to display in the prompt.

    Returns:
        ReceiptMatchingAction: The selected action as an Enum value.
    """
    account_key: str = (
        f"{account.account_holder}:{account.bank}:{account.account_type}"
    )

    prompt = (
        "\nNo matches found for the above transaction in a receipt of:\n  "
        f"  {receipt.the_date}\nfrom account:\n    {account_key}.\nPlease"
        " select an action (enter a number 1-5):\n\n1. Add estimated"
        " conversion rate for alternative currency.\n2. Check if the"
        " receipt is correct\n3. Check if transactions for this account"
        " are up to date\n4. Widen the date margin\n5. Widen the amount"
        " margin\n"
    )

    while True:
        user_input = input(prompt).strip()
        if user_input.isdigit() and user_input in [
            e.value for e in ReceiptMatchingAction
        ]:
            return ReceiptMatchingAction(user_input)
        print("Invalid input. Please enter a number between 1 and 6.")


@typechecked
def is_new_transaction(
    *,
    updated_receipt: Receipt,
    search_receipt_account_transaction: AccountTransaction,
) -> bool:
    """
    Determines if the updated_receipt represents a new transaction compared to search_receipt_account_transaction.
    Checks if the total number of AccountTransactions in net_bought_items and net_returned_items is exactly 1.

    Args:
        updated_receipt (Receipt): The receipt to check for newness.
        search_receipt_account_transaction (AccountTransaction): The existing transaction to compare against.

    Returns:
        bool: True if the updated_receipt is newer than the search_receipt_account_transaction, False otherwise.

    Raises:
        NotImplementedError: If the total number of AccountTransactions in net_bought_items and net_returned_items is not exactly 1.
    """
    receipt_transaction: AccountTransaction = get_single_account_transaction(
        updated_receipt=updated_receipt
    )
    return (
        receipt_transaction.account
        != search_receipt_account_transaction.account
        or receipt_transaction.account.base_currency
        != search_receipt_account_transaction.account.base_currency
        or receipt_transaction.tendered_amount_out
        != search_receipt_account_transaction.tendered_amount_out
        or receipt_transaction.change_returned
        != search_receipt_account_transaction.change_returned
        or receipt_transaction.original_transaction
        != search_receipt_account_transaction.original_transaction
    )


@typechecked
def get_single_account_transaction(
    *, updated_receipt: Receipt
) -> AccountTransaction:
    """
    Retrieves the single AccountTransaction from the updated_receipt's net_bought_items or net_returned_items.

    Args:
        updated_receipt (Receipt): The receipt containing ExchangedItems with AccountTransactions.

    Returns:
        AccountTransaction: The single AccountTransaction found.

    Raises:
        NotImplementedError: If the total number of AccountTransactions is not exactly 1.
        ValueError: If net_bought_items or net_returned_items is None.
    """
    # Ensure fields are not None
    if (
        updated_receipt.net_bought_items is None
        and updated_receipt.net_returned_items is None
    ):
        raise NotImplementedError("No ExchangedItems found in receipt")

    # Collect non-None ExchangedItems
    items = []
    if updated_receipt.net_bought_items is not None:
        items.append(updated_receipt.net_bought_items)
    if updated_receipt.net_returned_items is not None:
        items.append(updated_receipt.net_returned_items)

    # Count total AccountTransactions
    total_account_transactions = sum(
        len(item.account_transactions) for item in items
    )

    if total_account_transactions != 1:
        raise NotImplementedError(
            "Expected exactly 1 AccountTransaction, found"
            f" {total_account_transactions}"
        )

    # Find the ExchangedItem with the AccountTransaction
    for item in items:
        if item.account_transactions:
            return item.account_transactions[0]

    raise NotImplementedError("No AccountTransaction found in receipt")
