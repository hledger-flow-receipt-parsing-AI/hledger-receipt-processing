from typing import Dict, List, NamedTuple

from typeguard import typechecked

from hledger_core.generics.Transaction import Transaction


class HledgerFlowAccountInfo(NamedTuple):
    account_holder: str
    bank: str
    account_type: str

    def __eq__(self, other) -> bool:
        if not isinstance(other, HledgerFlowAccountInfo):
            return False
        # Compare normalized values
        return (
            self.account_holder == other.account_holder
            and self.bank == other.bank
            and self.account_type == other.account_type
        )

    @typechecked
    def to_colon_separated_string(self) -> str:
        """Returns the HledgerFlowAccountInfo in format:
        account_holder:bank:account_type
        """
        return f"{self.account_holder}:{self.bank}:{self.account_type}"


@typechecked
def get_account_info_groups(
    *, transactions: List[Transaction]
) -> List[HledgerFlowAccountInfo]:
    """
    Gets all unique groups of account information from transactions.

    Args:
        transactions: List of Transaction objects.

    Returns:
        A set of HledgerFlowAccountInfo tuples containing unique combinations of
        account_holder, bank, and account_type.
    """
    account_info_groups: List[HledgerFlowAccountInfo] = []

    for transaction in transactions:
        account_info = HledgerFlowAccountInfo(
            account_holder=transaction.account.account_holder,
            bank=transaction.account.bank,
            account_type=transaction.account.account_type,
        )
        account_info_groups.append(account_info)

    return account_info_groups


@typechecked
def get_account_info_groups_from_years(
    *, transactions_per_year: Dict[int, List[Transaction]]
) -> List[HledgerFlowAccountInfo]:
    """
    Wrapper function to get unique account information groups from transactions organized by year.

    Args:
        transactions_per_year: Dictionary mapping years to lists of Transaction objects.

    Returns:
        A set of HledgerFlowAccountInfo tuples containing unique combinations of
        account_holder, bank, and account_type across all years.
    """
    # Flatten all transactions from all years into a single list
    all_transactions: List[Transaction] = []
    for transactions in transactions_per_year.values():
        all_transactions.extend(transactions)

    # Call the original function with the flattened list
    return get_account_info_groups(transactions=all_transactions)
