import logging
from typing import Any, Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_core.generics.enums import ClassifierType, LogicType
from hledger_receipt_processing.matching.searching.match_receipt import (
    match_receipt_items_to_csv_transactions,
)
from hledger_core.TransactionObjects.Receipt import (
    Account,
    AccountTransaction,
    Receipt,
)

logger = logging.getLogger(__name__)
import logging
from typing import Dict, List

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction


@typechecked
def manage_matching_receipts_to_transactions(
    *,
    config: Config,
    labelled_receipts: List[Receipt],
    json_paths_receipt_objs: Dict[str, Receipt],
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    models: Dict[ClassifierType, Dict[LogicType, Any]],
) -> None:
    """
    Match receipts to transactions across all accounts.

    Args:
        config: Configuration object containing accounts and matching settings.
        json_paths_receipt_objs: List of receipt objects with their JSON paths.
        transactions_per_account: Transactions organized by account and year.

    Returns:
        Dictionary mapping logic type to matched results per account.
    """
    # result: Dict[LogicType, Dict] = {LogicType.LABEL: {}}

    csv_accounts: List[Account] = [
        account_config.account for account_config in config.accounts
    ]
    check_missing_accounts(
        csv_accounts=csv_accounts,
        json_paths_receipt_objs=json_paths_receipt_objs,
    )

    for img_label_filepath, receipt in json_paths_receipt_objs.items():
        match_receipt_items_to_csv_transactions(
            receipt=receipt,
            labelled_receipts=labelled_receipts,
            search_receipt_account_transactions=receipt.get_both_item_types(),
            csv_transactions_per_account=csv_transactions_per_account,
            config=config,
            ai_models_tnx_classification=models[
                ClassifierType.TRANSACTION_CATEGORY
            ][LogicType.AI],
            rule_based_models_tnx_classification=models[
                ClassifierType.TRANSACTION_CATEGORY
            ][LogicType.RULE_BASED],
        )
    # return result


@typechecked
def check_missing_accounts(
    *,
    csv_accounts: List[Account],
    json_paths_receipt_objs: Dict[str, Receipt],
) -> List[Account]:
    """
    Check for missing accounts or asset categories in receipts.

    Args:
        config: Configuration object containing account information.
        json_paths_receipt_objs: Dictionary of receipt objects.
        available_accounts: List of available accounts.

    Returns:
        List of missing account identifiers.
    """
    missing_accounts: List[Account] = []

    for receipt in json_paths_receipt_objs.values():
        search_receipt_account_transactions: List[AccountTransaction] = (
            receipt.get_both_item_types()
        )
        for transaction in search_receipt_account_transactions:
            account = transaction.account
            if account not in csv_accounts:
                # account_str = account.to_string()
                if account not in missing_accounts:
                    missing_accounts.append(account)

    return missing_accounts
