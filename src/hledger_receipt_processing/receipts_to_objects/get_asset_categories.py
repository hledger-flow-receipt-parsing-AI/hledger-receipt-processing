import os
import subprocess
from typing import List

from hledger_config.config.load_config import Config
from hledger_core.TransactionObjects.Receipt import (  # For image handling
    ExchangedItem,
)


def get_all_hledger_asset_accounts(*, config: Config) -> set[str]:
    """
    Retrieves the list of all accounts that are classified under assets, even if they are
    not pure assets like bank accounts (instead of gold etc.).

    Returns:
        List[str]: List of account names matching the '^Assets' pattern.

    Raises:
        subprocess.CalledProcessError: If the hledger command fails.
        FileNotFoundError: If the journal file does not exist.
    """
    abs_journal_filepath: str = config.file_names.get_filepath(
        dir_path_config=config.dir_paths, filename="root_journal_filename"
    )

    if not os.path.isfile(abs_journal_filepath):
        accounts: List[str] = []
        for (
            currency
        ) in (
            config.include_asset_transactions.currencies.get_configured_currencies()
        ):
            # TODO: add the owner.
            accounts.append(currency.value)
        for (
            direct_asset
        ) in config.include_asset_transactions.direct_assets.include_map.keys():
            # TODO: add the owner.
            accounts.append(direct_asset.value)
        return set(accounts)
        # raise FileNotFoundError(
        #     f"Journal file not found: {abs_journal_filepath}"
        # )

    # Run hledger command
    cmd = ["hledger", "accounts", "-f", abs_journal_filepath, "^Assets"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Split output into list, removing empty lines
    accounts = [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
    return set(accounts)
