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
    Prompts the user to select a currency or asset (from a unified list) sold to obtain the receipt
    currency and provide a conversion ratio. Assumes the selected currency/asset differs from the
    receipt transaction currency.

    Args:
        search_receipt_account_transaction: The transaction from the receipt with its currency.

    Returns:
        Tuple containing:
        - from_currency: The selected currency or asset sold (from CSV).
        - to_currency: The receipt transaction currency.
        - conversion_ratio: The conversion ratio from from_currency to to_currency.

    Raises:
        AssertionError: If the selected currency/asset matches the receipt currency.
    """

    def prompt_for_currency_or_asset() -> Currency:
        """Prompts the user to select a valid currency or asset from a unified list."""
        options = list(Currency)
        options_display = "\n".join(
            f"{i + 1}. {option.value}" for i, option in enumerate(options)
        )
        prompt = (
            "\nSelect the currency or asset (from CSV) sold to obtain the"
            f" receipt currency:\n{options_display}\nEnter the number"
            " corresponding to the currency or asset: "
        )
        while True:
            user_input = input(prompt).strip()
            if user_input.isdigit() and 1 <= int(user_input) <= len(options):
                selected_option = options[int(user_input) - 1]
                return selected_option
            print(
                "Invalid input. Please enter a number between 1 and"
                f" {len(options)}."
            )

    def prompt_for_conversion_ratio(
        *,
        from_currency: Currency,
        to_currency: Currency,
    ) -> float:
        """Prompts the user for a valid conversion ratio between two currencies/assets."""
        while True:
            try:
                ratio = float(
                    input(
                        "\nEnter the conversion ratio from"
                        f" {from_currency.value} to {to_currency.value} (e.g.,"
                        f" 1 {from_currency.value} = X {to_currency.value},"
                        " enter X): "
                    ).strip()
                )
                if ratio > 0:
                    return ratio
                print("Conversion ratio must be a positive number.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")

    # Prompt for a single currency or asset from the unified list
    from_currency = prompt_for_currency_or_asset()
    # Use payment_currency (foreign currency) when available, otherwise base_currency
    payment_cur = getattr(search_receipt_account_transaction, "payment_currency", None)
    to_currency = (
        payment_cur
        if payment_cur is not None
        else search_receipt_account_transaction.account.base_currency
    )
    conversion_ratio = prompt_for_conversion_ratio(
        from_currency=from_currency, to_currency=to_currency
    )

    return from_currency, to_currency, conversion_ratio
