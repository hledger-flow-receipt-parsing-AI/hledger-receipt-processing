from copy import deepcopy

from typeguard import typechecked

from hledger_config.config.load_config import Config


@typechecked
def asked_widen_date_range(
    *,
    config: Config,
) -> float:
    while True:
        try:
            additional_days = int(
                input(
                    "Enter a positive number of days to widen the date range: "
                )
            )
            if additional_days <= 0:
                print(
                    "Error: Number of days must be positive. Please try again."
                )
                continue
            return float(additional_days)
        except ValueError:
            print("Error: Please enter a valid integer. Try again.")


@typechecked
def widen_date_range(
    *,
    config: Config,
    additional_days: float,
) -> Config:
    updated_config: Config = deepcopy(config)
    if updated_config.matching_algo.days < 0:
        raise ValueError("Negative matching algo days is not allowed.")
    if additional_days <= 0:
        raise ValueError("Negative/zero additional_days is not allowed.")
    updated_config.matching_algo.days += additional_days
    return updated_config
