import logging
from typing import Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_receipt_processing.matching.ask_user_action import (
    ActionDataset,
    ActionValuePair,
)
from hledger_receipt_processing.matching.searching.match_receipt_transaction import (
    match_receipt_item_transaction_to_csv_transactions,
)
from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (
    HledgerFlowAccountInfo,
)
from hledger_core.TransactionObjects.Receipt import (
    AccountTransaction,
    Receipt,
)

logger = logging.getLogger(__name__)
import logging
from typing import Dict, List

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction


@typechecked
def match_receipt_items_to_csv_transactions(
    *,
    receipt: Receipt,
    labelled_receipts: List[Receipt],
    search_receipt_account_transactions: List[AccountTransaction],
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    config: Config,
    ai_models_tnx_classification: List,
    rule_based_models_tnx_classification: List,
) -> None:
    """
    Match a single receipt to transactions in relevant accounts.

    Args:
        receipt: Receipt object to match.
        relevant_accounts: List of relevant account information.
        transactions_per_account: Transactions organized by account and year.
        config: Configuration object with matching settings.
        result: Dictionary to store matching results.
    """
    if len(search_receipt_account_transactions) < 1:
        raise ValueError(
            "A receipt must be categorised under an"
            f" account:{search_receipt_account_transactions.__dict__}"
        )

    # Loop over accounts in receipt.
    for (
        search_receipt_account_transaction
    ) in search_receipt_account_transactions:
        actions_value: List[ActionValuePair] = []
        if not search_receipt_account_transaction.original_transaction:

            # Initialise action_dataset.
            action_dataset: ActionDataset = ActionDataset(
                receipt=receipt,
                labelled_receipts=labelled_receipts,
                account=search_receipt_account_transaction.account,
                search_receipt_account_transaction=search_receipt_account_transaction,
                config=config,
                csv_transactions_per_account=csv_transactions_per_account,
                ai_models_tnx_classification=ai_models_tnx_classification,
                rule_based_models_tnx_classification=rule_based_models_tnx_classification,
                original_receipt_account_transaction=None,
                original_receipt=None,
            )
            match_receipt_item_transaction_to_csv_transactions(
                csv_transactions_per_account=csv_transactions_per_account,
                actions_value=actions_value,
                action_dataset=action_dataset,
            )


@typechecked
def retry_matching_with_updated_config(
    *,
    receipt: Dict,
    account: HledgerFlowAccountInfo,
    transactions_per_account: Dict[AccountConfig, Dict[int, List[Transaction]]],
    config: Config,
    result: Dict[str, Dict],
    action: Dict,
) -> None:
    """
    Retry matching with updated configuration based on user action.

    Args:
        receipt: Receipt object.
        account: Account information.
        transactions_per_account: Transactions organized by account and year.
        config: Configuration object.
        result: Dictionary to store matching results.
        action: User-selected action to adjust matching parameters.
    """
    updated_config = update_config_from_action(config, action)

    error_TODO_match_receipt_items_to_csv_transactions(
        receipt, [account], transactions_per_account, updated_config, result
    )


@typechecked
def update_config_from_action(*, config: Config, action: Dict) -> Config:
    """
    Update configuration based on user action.

    Args:
        config: Original configuration object.
        action: Dictionary containing user-selected action.

    Returns:
        Updated configuration object.
    """
    input("TODO: Make this only a temporary action for this receipt.")
    new_config = config
    if action.get("widen_date_margin"):
        new_config.matching_algo.date_margin_days += 5
    if action.get("widen_amount_margin"):
        new_config.matching_algo.amount_margin += 0.1
    if action.get("reduce_date_margin"):
        new_config.matching_algo.date_margin_days = max(
            1, new_config.matching_algo.date_margin_days - 5
        )
    if action.get("reduce_amount_margin"):
        new_config.matching_algo.amount_margin = max(
            0.01, new_config.matching_algo.amount_margin - 0.1
        )
    return new_config
