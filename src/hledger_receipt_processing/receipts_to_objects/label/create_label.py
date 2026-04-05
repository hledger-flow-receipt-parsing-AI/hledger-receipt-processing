from typing import Tuple

from typeguard import typechecked

from hledger_core.file_reading_and_writing import load_json_from_file
from hledger_core.TransactionObjects.Receipt import Receipt


# Example usage
class CreateLabel:
    name = "create_label"

    def image_path_to_receipt(
        self, receipt_filepath: str
    ) -> Tuple[str, Receipt]:
        receipt_label_filepath: str = f"receipt_filepath"  # TODO: change.
        receipt_json_label: str = load_json_from_file(
            json_filepath=receipt_label_filepath
        )
        receipt: Receipt = self._json_object_to_receipt(
            json_object=receipt_json_label
        )
        # TODO: include GUI to draw/select boxes with characters, words and/or lines.
        # TODO: include GUI to group boxes and or characters/words and/or lines.
        # TODO: create GUI to create key-value pairs of items.
        # TODO: create GUI to create key-value pairs of description, item.
        # TODO: create GUI to correct text that is parsed from boxes.
        return receipt_json_label, receipt

    def _json_object_to_receipt(self, json_object: str) -> Receipt:
        return json_object

    @typechecked
    def get_name(self) -> str:
        return self.name
