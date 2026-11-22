"""Shared test setup."""

# The packages import each other at module level; the application always
# enters through hledger_preprocessor, which resolves the cycle.  Importing
# a receipt-processing module first fails with a circular-import error.
import hledger_preprocessor  # noqa: F401
