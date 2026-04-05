import logging
from typing import Dict, Union

from hledger_config.config.Config import Config
from hledger_config.config.load_config import (  # Config,
    raw_receipt_img_filepath_to_cropped,
)
from hledger_core.Currency import Currency
from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (
    HledgerFlowAccountInfo,
)

logger = logging.getLogger(__name__)
from typeguard import typechecked

from hledger_core.date_extractor import (
    can_swap_day_and_month,
    swap_month_day,
)
from hledger_receipt_processing.management.get_all_hledger_flow_accounts import (
    get_all_accounts,
)
from hledger_receipt_processing.matching.ask_user_action import (
    ActionDataset,
    ActionValuePair,
    AlternateCurrencyWithdrawl,
    ReceiptMatchingAction,
    get_receipt_action,
)
from hledger_receipt_processing.matching.manual_actions.alternate_currency_withdrawl import (
    add_estimated_conversion_ratio,
)
from hledger_receipt_processing.matching.manual_actions.widen_amount_range import (
    asked_widen_amount_range,
)
from hledger_receipt_processing.matching.manual_actions.widen_date_range import (
    asked_widen_date_range,
)
from hledger_receipt_processing.receipts_to_objects.make_receipt_labels import (
    make_receipt_label,
)
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def prompt_user_for_no_matches(
    *,
    action_dataset: ActionDataset,
) -> ActionValuePair:
    """
    Prompt user for actions when no matches are found.

    Args:
        receipt: Receipt object.
        account: Account information.
        config: Configuration object.

    Returns:
        Dictionary of selected actions or None if no action taken.
    """

    action: ReceiptMatchingAction = get_receipt_action(
        account=action_dataset.account,
        search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
        receipt=action_dataset.receipt,
    )

    action_values: Union[AlternateCurrencyWithdrawl, Receipt, float, bool]
    if action == ReceiptMatchingAction.ALTERNATE_CURRENCY_WITHDRAWL:
        from_currency: Currency
        conversion_ratio_1_from_to: float

        from_currency, _, conversion_ratio_1_from_to = (
            add_estimated_conversion_ratio(
                search_receipt_account_transaction=action_dataset.search_receipt_account_transaction,
            )
        )
        action_values = AlternateCurrencyWithdrawl(
            from_currency=from_currency,
            conversion_ratio_1_from_to=conversion_ratio_1_from_to,
        )

    elif action == ReceiptMatchingAction.CHECK_RECEIPT:
        cropped_receipt_img_filepath: str = raw_receipt_img_filepath_to_cropped(
            config=action_dataset.config,
            raw_receipt_img_filepath=action_dataset.receipt.raw_img_filepath,
        )
        # Load receipt image, load receipt.
        modified_receipt: Receipt = make_receipt_label(
            config=action_dataset.config,
            raw_receipt_img_filepath=action_dataset.receipt.raw_img_filepath,
            cropped_receipt_img_filepath=cropped_receipt_img_filepath,
            hledger_account_infos=get_all_accounts(
                config=action_dataset.config,
                labelled_receipts=action_dataset.labelled_receipts,
            )[0],
            receipt_nr=0,
            total_nr_of_receipts=1,
            labelled_receipts=[],
            prefilled_receipt=action_dataset.receipt,
        )
        action_values = modified_receipt

        # TODO: check if the new receipt is different from the old one.
    elif action == ReceiptMatchingAction.CHECK_TRANSACTIONS:
        raise NotImplementedError("Did not implement this yet.")
    elif action == ReceiptMatchingAction.WIDEN_DATE:
        # raise NotImplementedError("Did not implement this yet.")

        additional_days: float = asked_widen_date_range(
            config=action_dataset.config
        )
        action_values = additional_days

    elif action == ReceiptMatchingAction.WIDEN_AMOUNT:
        abs_additive_widening_fraction: float = asked_widen_amount_range()
        action_values = abs_additive_widening_fraction

    elif action == ReceiptMatchingAction.SWAP_DAY_AND_MONTH:
        if (
            can_swap_day_and_month(some_date=action_dataset.receipt.the_date)
            and action_dataset.original_receipt_account_transaction is None
        ):

            swapped_date = swap_month_day(
                some_date=action_dataset.receipt.the_date
            )
            action_values = swapped_date
        else:
            raise ValueError(
                "Cannot swap month and day if it is not the first modification."
            )

    else:
        raise ValueError(f"Not a supported action:{action}")

    action_value_pair: ActionValuePair = ActionValuePair(
        action=action,
        values=action_values,
    )
    return action_value_pair


@typechecked
def prompt_user_for_multiple_matches(
    *, receipt: Dict, account: HledgerFlowAccountInfo, config: Config
) -> str:
    """
    Prompt user for actions when too many matches are found.

    Args:
        receipt: Receipt object.
        account: Account information.
        config: Configuration object.

    Returns:
        Dictionary of selected actions or None if no action taken.
    """
    account_key = (
        f"{account.account_holder}:{account.bank}:{account.account_type}"
    )
    something: str = input(
        f"Too many matches (>15) found for receipt {receipt.get('id')} on"
        f" account {account_key}. Please select an action:\n1. Check if the"
        " receipt is correct\n2. Check if transactions for this account are up"
        " to date\n3. Reduce the date margin\n4. Reduce the amount margin\n5."
        " Skip this receipt"
    )
    # Simulated user input (in practice, this would be an interactive prompt)
    # For demo purposes, return a sample action
    return something
