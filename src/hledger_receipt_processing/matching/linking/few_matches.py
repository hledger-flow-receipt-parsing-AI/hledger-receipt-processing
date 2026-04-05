import logging
from typing import Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.ask_user_action import (
    ActionDataset,
    ActionValuePair,
)
from hledger_receipt_processing.matching.linking.no_matches import handle_no_matches
from hledger_receipt_processing.matching.linking.one_match import auto_link_receipt
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Receipt import Account

logger = logging.getLogger(__name__)
import logging
from dataclasses import dataclass
from pprint import pprint
from typing import Dict, List

from typeguard import typechecked


@dataclass
class TransactionSelection:
    SELECTED: int = 0
    NO_MATCH: int = -1


@typechecked
def handle_few_matches(
    *,
    original_receipt_account_transaction: AccountTransaction,
    transaction_matches: List[Transaction],
    receipt_account: Account,
    # config: Config,
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    actions_value: List[ActionValuePair],
    action_dataset: ActionDataset,
) -> None:
    """
    Handles cases where a few transaction matches (1 to 14) are found for a receipt.
    Prompts the user to select a transaction by number or indicate no match.
    Asserts the user input is valid and processes the selection accordingly.

    Args:
        receipt: The receipt to match.
        receipt_account: The account associated with the receipt.
        search_receipt_account_transaction: The transaction to match against.
        config: Configuration settings for matching.
        csv_transactions_per_account: Dictionary of transactions per account.
    """
    account_key: str = (
        f"{receipt_account.account_holder}:{receipt_account.bank}:{receipt_account.account_type}"
    )
    print("\n")
    pprint(action_dataset.search_receipt_account_transaction)
    print(
        f"\nFound {len(transaction_matches)} possible transaction matches for"
        f" receipt on {action_dataset.receipt.the_date}"
    )
    print(f"from account: {account_key}\n")

    # Display all matches with numbers
    for idx, transaction in enumerate(transaction_matches, 1):
        print(f"{idx}. {transaction}")

    prompt = (
        "\nPlease select a transaction by number"
        f" (1-{len(transaction_matches)}) or enter 0 to indicate no match:\n"
    )

    while True:
        user_input = input(prompt).strip()
        if user_input.isdigit() and 0 <= int(user_input) <= len(
            transaction_matches
        ):
            selected_number = int(user_input)
            if selected_number == TransactionSelection.NO_MATCH:
                handle_no_matches(
                    csv_transactions_per_account=csv_transactions_per_account,
                    actions_value=actions_value,
                    action_dataset=action_dataset,
                )
                break
            else:
                auto_link_receipt(
                    original_receipt_account_transaction=original_receipt_account_transaction,
                    found_csv_transaction=transaction_matches[
                        selected_number - 1
                    ],
                    # account=receipt_account,
                    action_dataset=action_dataset,
                )
                break
        print(
            "Invalid input. Please enter a number between 0 and"
            f" {len(transaction_matches)}."
        )
