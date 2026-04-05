import logging
from copy import deepcopy
from typing import Dict, List, Union

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.helper import has_input_csv
from hledger_preprocessor.csv_parsing.assets_to_csv import (
    export_asset_transaction_to_csv,
)
from hledger_preprocessor.csv_parsing.check_assets_in_csv_status import (
    unclassified_transaction_can_be_exported,
    unclassified_transaction_is_exported,
)
from hledger_core.date_extractor import (
    can_swap_day_and_month,
    swap_month_day,
)
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.matching.ask_user_action import (
    ActionDataset,
    ActionValuePair,
    apply_action,
)
from hledger_receipt_processing.matching.linking.one_match import auto_link_receipt
from hledger_receipt_processing.matching.searching.helper import (
    get_receipt_transaction_matches_in_csv_accounts,
)
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.Receipt import Receipt

from ..user_interaction import prompt_user_for_no_matches

logger = logging.getLogger(__name__)
import logging
from typing import Dict, List

from typeguard import typechecked


@typechecked
def handle_no_matches(
    *,
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    actions_value: List[ActionValuePair],
    action_dataset: ActionDataset,
) -> Union[None, ActionDataset]:
    """
    Handle case when no matching transactions are found.

    Args:
        receipt: Receipt object.
        receipt_account: Account information for the receipt.
        search_receipt_account_transaction: The specific account transaction from the receipt.
        config: Configuration object.
        result: Dictionary to store matching results.
        transactions_per_account: Transactions organized by account and year.
    """
    # TODO: get overarching config object.
    if has_input_csv(
        config=action_dataset.config,
        account=action_dataset.search_receipt_account_transaction.account,
    ):

        updated_action_dataset: ActionDataset = action_dataset
        # First try if a "swap day and month" yields 1 match.
        if not try_and_swap_day_month(
            csv_transactions_per_account=csv_transactions_per_account,
            action_dataset=action_dataset,
        ):

            # If that did not work, ask user for help.
            action_value: ActionValuePair = prompt_user_for_no_matches(
                action_dataset=action_dataset
            )

            # Apply the action to the current dataset (without re-matching).
            updated_action_dataset: ActionDataset = apply_action(
                action_dataset=action_dataset,
                action_value=action_value,
            )
            actions_value.append(action_value)

            # Lazy import inside the function
            from hledger_receipt_processing.matching.searching.match_receipt_transaction import (
                match_receipt_item_transaction_to_csv_transactions,
            )

            # Rematch. Note the updated_action_dataset implies the value may be updated.
            match_receipt_item_transaction_to_csv_transactions(
                csv_transactions_per_account=csv_transactions_per_account,
                actions_value=actions_value,
                action_dataset=updated_action_dataset,
            )
            return updated_action_dataset  # TODO: check if you need to return that set, if it is used.

        else:
            print(f"Automatically matched with Day-Month swap.")
    else:
        if unclassified_transaction_can_be_exported(
            config=action_dataset.config,
            account=action_dataset.search_receipt_account_transaction.account,
        ):
            if not unclassified_transaction_is_exported(
                config=action_dataset.config,
                search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
                parent_receipt=action_dataset.receipt,
                ai_models_tnx_classification=action_dataset.ai_models_tnx_classification,  #: Dict[str, str],
                rule_based_models_tnx_classification=action_dataset.rule_based_models_tnx_classification,  #: Dict[str, str]
                category_namespace=action_dataset.config.category_namespace,
            ):
                export_asset_transaction_to_csv(
                    config=action_dataset.config,
                    labelled_receipts=labelled_receipts,
                    search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
                    parent_receipt=action_dataset.receipt,
                    ai_models_tnx_classification=action_dataset.ai_models_tnx_classification,  #: Dict[str, str],
                    rule_based_models_tnx_classification=action_dataset.rule_based_models_tnx_classification,  #: Dict[str, str]
                )
        # print(
        #     "Skipping"
        #     f" {action_dataset.search_receipt_account_transaction} because it's"
        #     " csv is not activated in config."
        # )


def try_and_swap_day_month(
    *,
    # original_receipt_account_transaction: Optional[AccountTransaction] = None,
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    # config: Config,
    action_dataset: ActionDataset,
) -> bool:
    receipt_account: Account = (
        action_dataset.search_receipt_account_transaction.account
    )

    if (
        can_swap_day_and_month(some_date=action_dataset.receipt.the_date)
        and action_dataset.original_receipt_account_transaction is None
    ):

        swapped_date = swap_month_day(some_date=action_dataset.receipt.the_date)
        receipt_with_swapped_day_month: Receipt = deepcopy(
            action_dataset.receipt
        )
        receipt_with_swapped_day_month.the_date = swapped_date

        # Create a backup and update the current receipt.
        action_dataset.original_receipt = action_dataset.receipt
        action_dataset.receipt = receipt_with_swapped_day_month
        transaction_matches: List[Transaction] = (
            get_receipt_transaction_matches_in_csv_accounts(
                csv_transactions_per_account=csv_transactions_per_account,
                action_dataset=action_dataset,
            )
        )

        if len(transaction_matches) == 1:

            auto_link_receipt(
                action_dataset=action_dataset,
                found_csv_transaction=transaction_matches[0],
                original_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
            )
            return True
        else:
            return False
    return False
