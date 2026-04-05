from typing import Dict, List

import urwid
from typeguard import typechecked

from hledger_core.Currency import Currency
from hledger_core.TransactionObjects.Receipt import Receipt


@typechecked
def display_receipt_tui(receipts: List[Receipt]) -> Receipt:
    selected_receipt = None

    @typechecked
    def exit_program(button=None) -> None:
        raise urwid.ExitMainLoop()

    @typechecked
    def select_receipt(button, receipt: Receipt) -> None:
        nonlocal selected_receipt
        selected_receipt = receipt
        raise urwid.ExitMainLoop()

    sorted_receipts = sorted(receipts, key=lambda x: x.the_date)

    items = []
    for receipt in sorted_receipts:
        net_amount_dict: Dict[Currency, float] = (
            receipt.get_net_exchange_amount()
        )
        default_currency: Currency = (
            list(net_amount_dict.keys())[0] if net_amount_dict else Currency.USD
        )
        default_amount: float = net_amount_dict.get(default_currency, 0.0)
        line = (
            f"Date: {receipt.the_date.strftime('%Y-%m-%d-%H-%M-%S')} | Amount:"
            f" {default_amount:.2f} {default_currency.value} | File:"
            f" {receipt.raw_img_filepath}"
        )
        button = urwid.Button(line)
        urwid.connect_signal(
            button, "click", select_receipt, receipt
        )  # Pass receipt directly
        item = urwid.AttrMap(button, None, focus_map="reversed")
        items.append(item)

    list_walker = urwid.SimpleFocusListWalker(items)
    list_box = urwid.ListBox(list_walker)

    header = urwid.Text(
        "Receipts List (Use UP/DOWN arrows, ENTER to select, Q to quit)",
        align="center",
    )

    frame = urwid.Frame(
        body=list_box, header=urwid.Pile([header, urwid.Divider("-")])
    )

    @typechecked
    def handle_input(key: str) -> None:
        if key in ("q", "Q"):
            exit_program()
        elif key == "enter":
            if list_walker.focus is not None:
                receipt = sorted_receipts[list_walker.focus]
                select_receipt(None, receipt)

    loop = urwid.MainLoop(
        frame,
        unhandled_input=handle_input,
        palette=[("reversed", "standout", "")],
    )
    loop.run()

    if selected_receipt is None:
        raise ValueError("No receipt was selected.")
    if not isinstance(selected_receipt, Receipt):
        raise TypeError(
            f"The selected receipt: {selected_receipt}, was not of type"
            f" Receipt: {type(selected_receipt)}"
        )
    return selected_receipt


@typechecked
def tui_select_receipt(receipts: List[Receipt]) -> Receipt:
    if not receipts:
        raise ValueError("No receipt labels found that can be edited.")
    return display_receipt_tui(receipts)
