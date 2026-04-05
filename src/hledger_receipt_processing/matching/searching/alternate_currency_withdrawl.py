from typing import Tuple

from typeguard import typechecked

from hledger_core.Currency import Currency
from hledger_core.TransactionObjects.Receipt import AccountTransaction


@typechecked
def add_estimated_conversion_ratio(
    *, search_receipt_account_transaction: AccountTransaction
) -> Tuple[
    Currency,
    Currency,
    float,
]:
    """
    Determines the currency of a transaction and prompts the user for either a conversion
    ratio to the base currency or an estimated amount for direct asset purchases.
    Assumes the receipt transaction currency differs from the CSV transaction currency.
    Returns a string representing the conversion details or estimated amount.

    Args:
        search_receipt_account_transaction: The transaction from the receipt with its currency.

    Returns:
        str: A string with the conversion ratio or estimated amount details.

    Raises:
        AssertionError: If the transaction currency matches the receipt currency.
    """

    def prompt_for_currency() -> Currency:
        """Prompts the user to select a valid currency from the Currency enum."""
        currency_options = "\n".join(
            f"{i + 1}. {currency.value}" for i, currency in enumerate(Currency)
        )
        prompt = (
            "\nSelect the (csv) currency that is sold to obtain the receipt"
            f" currency:\n{currency_options}\nEnter the number corresponding to"
            " the currency: "
        )
        while True:
            user_input = input(prompt).strip()
            if user_input.isdigit() and 1 <= int(user_input) <= len(Currency):
                selected_currency = list(Currency)[int(user_input) - 1]
                return selected_currency
            print(
                "Invalid input. Please enter a number between 1 and"
                f" {len(Currency)}."
            )

    def prompt_for_conversion_ratio(
        *,
        from_currency: Currency,
        to_currency: Currency,
    ) -> float:
        """Prompts the user for a valid conversion ratio between two currencies."""
        while True:
            try:
                ratio = float(
                    input(
                        f"\nEnter the conversion ratio from {from_currency} to"
                        f" {to_currency} (e.g., 1 {from_currency} = X"
                        f" {to_currency}, enter X): "
                    ).strip()
                )
                if ratio > 0:
                    return ratio
                print("Conversion ratio must be a positive number.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")

    # Use payment_currency (foreign currency) when available, otherwise base_currency
    payment_cur = getattr(search_receipt_account_transaction, "payment_currency", None)
    to_currency = (
        payment_cur
        if payment_cur is not None
        else search_receipt_account_transaction.account.base_currency
    )

    from_currency: Currency = prompt_for_currency()
    conversion_ratio = prompt_for_conversion_ratio(
        from_currency=from_currency,
        to_currency=to_currency,
    )
    return (
        from_currency,
        to_currency,
        conversion_ratio,
    )
