import logging
from typing import Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_core.generics.GenericTransactionWithCsv import (
    GenericCsvTransaction,
)
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.ask_user_action import (
    ActionDataset,
    ActionValuePair,
)
from hledger_receipt_processing.matching.searching.helper import (
    get_receipt_transaction_matches_in_csv_accounts,
)
from hledger_receipt_processing.matching.searching.match_handler import (
    handle_receipt_item_transaction_to_csv_matches,
)

logger = logging.getLogger(__name__)
import logging
from typing import Dict, List

from typeguard import typechecked


@typechecked
def match_receipt_item_transaction_to_csv_transactions(
    *,
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    actions_value: List[ActionValuePair],
    action_dataset: ActionDataset,
) -> None:
    """
    Matches a single receipt account transaction to corresponding transactions in CSV data.

    Args:
        search_receipt_account_transaction: The receipt transaction to match against CSV transactions.
        receipt: The Receipt object containing transaction context.
        csv_transactions_per_account: A dictionary mapping AccountConfig to transactions, organized by year.
        config: Configuration object containing settings for the matching process.
        original_receipt_account_transaction: Optional original transaction before any modifications, for reference.

    Returns:
        None: The function modifies external state or performs matching without returning a value.
    """
    # TODO: handle the case where the search transaction is updated. DO THIS!

    transaction_matches: List[Transaction] = (
        get_receipt_transaction_matches_in_csv_accounts(
            csv_transactions_per_account=csv_transactions_per_account,
            action_dataset=action_dataset,
        )
    )

    csv_transaction_matches: List[GenericCsvTransaction] = []
    # Loop over the accounts for which csv files are available.
    for txn in transaction_matches:
        if isinstance(txn, GenericCsvTransaction):
            csv_transaction_matches.append(txn)
            # raise TypeError(f"Expected GenericCsvTransaction, got:{txn}")

    handle_receipt_item_transaction_to_csv_matches(
        transaction_matches=csv_transaction_matches,
        csv_transactions_per_account=csv_transactions_per_account,
        actions_value=actions_value,
        action_dataset=action_dataset,
    )
