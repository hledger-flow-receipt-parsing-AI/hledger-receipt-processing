from copy import deepcopy

from typeguard import typechecked

from hledger_config.config.load_config import Config


@typechecked
def asked_widen_amount_range() -> float:
    while True:
        try:
            abs_additive_widening_fraction = float(
                input("Enter a positive widening fraction: ")
            )
            if abs_additive_widening_fraction <= 0:
                print(
                    "Error: Widening fraction must be positive. Please try"
                    " again."
                )
                continue
            return abs_additive_widening_fraction
        except ValueError:
            print("Error: Please enter a valid number. Try again.")


@typechecked
def widen_amount_range(
    *,
    config: Config,
    abs_additive_widening_fraction: float,
) -> Config:
    updated_config: Config = deepcopy(config)
    if updated_config.matching_algo.amount_range == 0:
        updated_config.matching_algo.amount_range = (
            abs_additive_widening_fraction
        )
    elif updated_config.matching_algo.amount_range > 0:
        updated_config.matching_algo.amount_range += (
            abs_additive_widening_fraction
        )
    elif updated_config.matching_algo.amount_range < 0:
        raise ValueError("Negative matching algo amount range is not allowed.")
    else:
        raise NotImplementedError(
            "Did not know how to handle"
            f" updated_config.matching_algo.amount_range={updated_config.matching_algo.amount_range}"
        )

    return updated_config
