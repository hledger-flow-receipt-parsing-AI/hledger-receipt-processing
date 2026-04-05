import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List

from hledger_config.config.AccountConfig import AccountConfig
from hledger_receipt_processing.matching.ask_user_action import ActionDataset
from hledger_core.TransactionObjects.Receipt import Account

from ..helper import (
    get_net_receipt_transactions_per_account,
    get_transactions_in_date_range,
)

logger = logging.getLogger(__name__)
import logging
from datetime import timedelta
from typing import Dict, List

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction


@typechecked
def get_receipt_transaction_matches_in_csv_accounts(
    *,
    # config: Config,
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ],
    # original_receipt_account_transaction: Optional[AccountTransaction] = None,
    action_dataset: ActionDataset,
) -> List[Transaction]:
    net_payed_amounts: Dict[Account, float] = (
        get_net_receipt_transactions_per_account(receipt=action_dataset.receipt)
    )
    receipt_account: Account = (
        action_dataset.search_receipt_account_transaction.account
    )
    transaction_matches: List[Transaction] = []
    for (
        csv_account,
        csv_transactions_of_an_account,
    ) in csv_transactions_per_account.items():
        # Only search CSV accounts that match the receipt's account.
        if not csv_account.has_input_csv():
            continue
        if csv_account.account != receipt_account:
            continue
        yearly_transactions: List[Transaction] = (
            get_transactions_in_date_range(
                transactions_per_year=csv_transactions_of_an_account,
                target_date=action_dataset.receipt.the_date,
                date_margin=timedelta(
                    days=action_dataset.config.matching_algo.days
                ),
            )
        )
        if receipt_account in net_payed_amounts.keys():
            transaction_matches.extend(
                filter_transactions_by_amount(
                    yearly_transactions=yearly_transactions,
                    action_dataset=action_dataset,
                )
            )
        else:
            raise ValueError(
                f"{receipt_account} not in keys {net_payed_amounts.keys()}"
            )
    return transaction_matches


@typechecked
def filter_transactions_by_amount(
    *,
    yearly_transactions: List[Transaction],
    # receipt_account: Account,
    # net_payed_amounts: Dict[Account, float],
    # amount_range: float,
    # original_receipt_account_transaction: Optional[AccountTransaction] = None,
    action_dataset: ActionDataset,
) -> list:
    """
    Filter transactions where the amount is within the specified margin, with debug print statements.

    Args:
        yearly_transactions: List of transactions to filter
        receipt_account: Account identifier for net paid amounts
        net_payed_amounts: Dictionary of net paid amounts by account
        amount_range: Allowed margin for amount comparison
        search_receipt_account_transaction: The receipt transaction to match against
        original_receipt_account_transaction: Optional original transaction before modifications

    Returns:
        List of transactions within the amount margin
    """
    filtered_transactions = []
    # Use search_receipt_account_transaction.amount_paid if original_receipt_account_transaction is not None
    # TODO: determine when you want to use the search receipt account transaction and when you
    # want to use the original receipt. Specifically, you should try to prevent overwriting the original receipt.
    target_amount = (
        action_dataset.search_receipt_account_transaction.tendered_amount_out
        - action_dataset.search_receipt_account_transaction.change_returned
        # if original_receipt_account_transaction is not None
        # else net_payed_amounts[receipt_account]
    )

    amount_range: float = action_dataset.config.matching_algo.amount_range
    currency = (
        action_dataset.search_receipt_account_transaction.account.base_currency.value
    )
    print(f"\nSearching for: {currency} {target_amount:.2f}")
    for transaction in yearly_transactions:
        net_out = transaction.tendered_amount_out - transaction.change_returned
        if is_amount_within_margin(
            transaction_amount=net_out,
            receipt_amount=target_amount,
            margin=amount_range,
        ):
            print(
                f"  ✓ Match: {transaction.the_date.strftime('%Y-%m-%d')} "
                f" {currency} {net_out:.2f}"
            )
            filtered_transactions.append(transaction)
    return filtered_transactions


@typechecked
def is_amount_within_margin(
    *, transaction_amount: float, receipt_amount: float, margin: float
) -> bool:
    """
    Check if transaction amount is within the margin of receipt amount.

    Args:
        transaction_amount: Amount of the transaction.
        receipt_amount: Amount of the receipt.
        margin: Allowed margin for amount comparison.

    Returns:
        True if amounts are within margin, False otherwise.
    """
    return abs(
        float(Decimal(str(transaction_amount)) - Decimal(str(receipt_amount)))
    ) <= margin * max(receipt_amount, 0.01)
