import logging
from typing import Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (
    HledgerFlowAccountInfo,
)

from ..user_interaction import prompt_user_for_multiple_matches

logger = logging.getLogger(__name__)
import logging
from typing import Dict, List

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction


@typechecked
def handle_many_matches(
    *,
    receipt: Dict,
    account: HledgerFlowAccountInfo,
    transactions_per_account: Dict[AccountConfig, Dict[int, List[Transaction]]],
    config: Config,
    result: Dict[str, Dict],
) -> None:
    """
    Handle case when 15 or more matching transactions are found.

    Args:
        receipt: Receipt object.
        account: Account information.
        transactions_per_account: Transactions organized by account and year.
        config: Configuration object.
        result: Dictionary to store matching results.
    """
    action = prompt_user_for_multiple_matches(receipt, account, config)
    if action:
        retry_matching_with_updated_config(
            receipt, account, transactions_per_account, config, result, action
        )
