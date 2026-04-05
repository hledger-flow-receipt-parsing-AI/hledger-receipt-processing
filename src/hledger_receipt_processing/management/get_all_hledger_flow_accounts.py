import os
from typing import Dict, List, Tuple

from typeguard import typechecked

from hledger_config.config.AccountConfig import AccountConfig
from hledger_config.config.load_config import Config
from hledger_preprocessor.csv_parsing.csv_to_transactions import (
    load_csv_transactions_from_file_per_year,
)
from hledger_core.generics.Transaction import Transaction
from hledger_receipt_processing.receipt_transaction_matching.get_bank_data_from_transactions import (
    HledgerFlowAccountInfo,
    get_account_info_groups_from_years,
)
from hledger_core.TransactionObjects.Receipt import Receipt


# Action 0.
@typechecked
def get_all_accounts(
    *, config: Config, labelled_receipts: List[Receipt]
) -> Tuple[
    set[HledgerFlowAccountInfo],
    Dict[AccountConfig, Dict[int, List[Transaction]]],
]:
    """Return account info set AND csv_transactions_per_account dict.

    The CSV data is already loaded to extract account metadata, so we
    keep it around for background matching during the TUI.
    """

    all_accounts: set[HledgerFlowAccountInfo] = set()
    csv_transactions_per_account: Dict[
        AccountConfig, Dict[int, List[Transaction]]
    ] = {}
    for account_config in config.accounts:
        abs_csv_filepath = account_config.get_abs_csv_filepath(
            dir_paths_config=config.dir_paths
        )
        if not os.path.isfile(abs_csv_filepath):
            continue

        transactions_per_year_per_account: Dict[int, List[Transaction]] = (
            load_csv_transactions_from_file_per_year(
                config=config,
                labelled_receipts=labelled_receipts,
                abs_csv_filepath=abs_csv_filepath,
                account_config=account_config,
                csv_encoding=config.csv_encoding,
            )
        )
        csv_transactions_per_account[account_config] = (
            transactions_per_year_per_account
        )
        accounts_in_those_transactions: set[HledgerFlowAccountInfo] = set(
            get_account_info_groups_from_years(
                transactions_per_year=transactions_per_year_per_account
            )
        )
        # Update means merge.
        all_accounts.update(accounts_in_those_transactions)
    return all_accounts, csv_transactions_per_account
