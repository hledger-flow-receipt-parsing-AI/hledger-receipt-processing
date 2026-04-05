import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pprint import pprint
from typing import Dict, List

logger = logging.getLogger(__name__)
from typeguard import typechecked

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_preprocessor.csv_parsing.csv_to_transactions import (
    load_csv_transactions_from_file_per_year,
)
from hledger_core.generics.Transaction import Transaction
from hledger_core.TransactionObjects.Account import Account
from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def get_net_receipt_transactions_per_account(
    *,
    receipt: Receipt,
) -> Dict[Account, float]:
    """
    Extract transaction date and amount from a receipt.

    Args:
        receipt: Receipt object containing transaction details.

    Returns:
        Tuple of (transaction_date, amount) or (None, None) if not found.
    """
    net_payed_amounts: Dict[Account, float] = {}
    search_receipt_account_transactions: List[AccountTransaction] = (
        receipt.get_both_item_types()
    )
    if len(search_receipt_account_transactions) < 1:
        pprint(receipt.__dict__)
        raise ValueError(
            "Receipt must have at least 1 transaction of either category."
            f" Got:{search_receipt_account_transactions}"
        )

    for (
        search_receipt_account_transaction
    ) in search_receipt_account_transactions:
        net_payed_from_account: float = float(
            Decimal(str(search_receipt_account_transaction.tendered_amount_out))
            - Decimal(str(search_receipt_account_transaction.change_returned))
        )

        if (
            search_receipt_account_transaction.account
            in net_payed_amounts.keys()
        ):
            raise NotImplementedError(
                f"Did not yet support multiple transactions on single account"
                f" for a receipt."
            )
        net_payed_amounts[search_receipt_account_transaction.account] = (
            net_payed_from_account
        )

    if len(net_payed_amounts.keys()) < 1:
        raise ValueError(
            f"Receipt must have at least 1 transaction. Got:{net_payed_amounts}"
        )
    return net_payed_amounts


@typechecked
def get_transactions_in_date_range(
    *,
    transactions_per_year: Dict[int, List[Transaction]],
    target_date: datetime,
    date_margin: timedelta,
) -> List[Transaction]:
    """
    Get transactions within a date range for a given year.

    Args:
        transactions_per_year: Transactions organized by year.
        target_date: Target date to match transactions against.
        date_margin: Margin of days to include before and after target date.

    Returns:
        List of transactions within the date range.
    """
    year = target_date.year
    transactions = transactions_per_year.get(year, [])
    start_date = target_date - date_margin
    end_date = target_date + date_margin

    # TODO: ensure the generic transaction type also has a "the_date".
    return [t for t in transactions if start_date <= t.the_date <= end_date]


@typechecked
def prepare_transactions_per_account(
    *,
    config: Config,
    labelled_receipts: List[Receipt],
) -> Dict[AccountConfig, Dict[int, List[Transaction]]]:
    """
    Prepare transactions per account from the configuration.

    Args:
        config: Configuration object containing accounts and CSV encoding.

    Returns:
        Dictionary mapping AccountConfig to transactions organized by year.
    """
    transactions_per_account = {}
    for account_config in config.accounts:

        abs_csv_filepath: str = account_config.get_abs_csv_filepath(
            dir_paths_config=config.dir_paths
        )

        if os.path.isfile(abs_csv_filepath):

            transactions_per_year = load_csv_transactions_from_file_per_year(
                config=config,
                labelled_receipts=labelled_receipts,
                abs_csv_filepath=abs_csv_filepath,
                account_config=account_config,
                csv_encoding=config.csv_encoding,
            )
            transactions_per_account[account_config] = transactions_per_year
    return transactions_per_account
