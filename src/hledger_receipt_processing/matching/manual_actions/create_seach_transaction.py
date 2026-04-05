from copy import deepcopy
from decimal import Decimal

from typeguard import typechecked

from hledger_core.Currency import Currency
from hledger_core.TransactionObjects.Receipt import AccountTransaction


@typechecked
def convert_search_transaction_with_csv_currency(
    *,
    search_receipt_account_transaction: AccountTransaction,
    from_currency: Currency,
    conversion_ratio_1_from_to: float,
) -> AccountTransaction:
    """
    Converts an AccountTransaction to a new currency using the provided conversion ratio,
    applying a 0.05 factor to the amount. Creates a new transaction with the updated currency
    and amount, preserving other transaction details.

    Args:
        search_receipt_account_transaction: The original transaction to convert.
        from_currency: The currency or asset of the original transaction.
        to_currency: The target currency or asset to convert to.
        conversion_ratio_1_from_to: The conversion ratio (1 unit of from_currency = X units of to_currency).

    Returns:
        AccountTransaction: A new transaction with the converted amount and currency.

    Raises:
        ValueError: If the conversion ratio is not positive or if the transaction constraints are violated.
        TypeError: If the account type is invalid.
    """
    if conversion_ratio_1_from_to <= 0:
        raise ValueError("Conversion ratio must be positive")

    # Create a deep copy of the original transaction
    new_transaction = deepcopy(search_receipt_account_transaction)

    # Calculate the net amount (amount_paid - change_returned)
    net_amount: float = float(
        Decimal(str(search_receipt_account_transaction.tendered_amount_out))
        - Decimal(str(search_receipt_account_transaction.change_returned))
    )

    converted_net_amount_from = net_amount * (1 / conversion_ratio_1_from_to)

    # Validate the new amount
    if converted_net_amount_from < 0:
        raise ValueError("Converted amount paid cannot be negative")

    # Update the transaction fields (frozen dataclass — use object.__setattr__)
    object.__setattr__(new_transaction, "tendered_amount_out", converted_net_amount_from)
    object.__setattr__(new_transaction, "change_returned", 0.0)
    # Update the account's base_currency to the from_currency
    from hledger_core.TransactionObjects.Account import Account
    new_account = Account(
        base_currency=from_currency,
        account_holder=new_transaction.account.account_holder,
        bank=new_transaction.account.bank,
        account_type=new_transaction.account.account_type,
    )
    object.__setattr__(new_transaction, "account", new_account)

    # Validate the new transaction
    if converted_net_amount_from == 0 and new_transaction.change_returned == 0:
        raise ValueError(
            "Cannot receive AND pay 0 in the converted transaction"
        )

    return new_transaction
