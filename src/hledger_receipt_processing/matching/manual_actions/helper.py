from typing import List, Union

from typeguard import typechecked

from hledger_core.TransactionObjects.AccountTransaction import (
    AccountTransaction,
)
from hledger_core.TransactionTypes.TriodosTransaction import (
    TriodosTransaction,
)


@typechecked
def convert_into_account_transaction_objects(
    *, transactions: List[Union[AccountTransaction, TriodosTransaction]]
) -> List[AccountTransaction]:
    uniform_transactions: List[AccountTransaction] = []
    for transaction in transactions:
        if isinstance(transaction, TriodosTransaction):
            uniform_transactions.append(transaction.to_account_transaction())
        elif isinstance(transaction, AccountTransaction):
            uniform_transactions.append(transaction)
        else:
            raise TypeError(f"Unexpected transaction type:{type(transaction)}")
    return uniform_transactions
