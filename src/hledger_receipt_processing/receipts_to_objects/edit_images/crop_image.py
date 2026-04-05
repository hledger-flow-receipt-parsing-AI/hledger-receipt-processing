import json
import os
from pathlib import Path
from typing import List, Union

import cv2
import numpy as np
from PIL import Image
from typeguard import typechecked

from hledger_config.config.load_config import Config
from hledger_core.generics.enums import EnumEncoder

# Import drawing functions from the shared module
from hledger_receipt_processing.receipts_to_objects.edit_images.drawing import (
    draw_crop_overlay,
)
from hledger_core.TransactionObjects.Receipt import (  # For image handling
    ExchangedItem,
    Receipt,
)


def crop_and_save_image(
    *,
    image_path: str,
    output_path: str,
    max_window_width: int = 1280,
    max_window_height: int = 720,
) -> Union[List[float], bool]:
    """
    Opens an image, displays it scaled to fit the OpenCV window, allows user to manually set
    crop coordinates (top-left and bottom-right) using number keys for input or arrow keys
    with/without Alt for adjustment, shows live preview of crop region, and saves the cropped
    image when Enter is pressed. Arrow keys adjust active corner (10% steps), Alt switches
    between top-left and bottom-right corners, indicated by a red crosshair.

    Args:
        image_path (str): Path to the input image
        output_path (str): Path to save the cropped image
        max_window_width (int): Maximum width of the display window (default: 1280)
        max_window_height (int): Maximum height of the display window (default: 720)

    Returns:
        Union[List[float], bool]: List of crop coordinates [x1, y1, x2, y2] (normalized 0 to 1)
                                 or False if operation is cancelled
    """
    try:
        pil_image = Image.open(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return False

    if pil_image.mode == "RGBA":
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGBA2BGR)
    else:
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    img_height, img_width = cv_image.shape[:2]

    crop_coords = [0.2, 0.2, 0.8, 0.8]  # [x1, y1, x2, y2]
    current_coord = 0  # Tracks which coordinate is being edited for numerical input (0: x1, 1: y1, 2: x2, 3: y2)
    input_value = ""  # String to build numerical input
    alt_pressed = False  # Track Alt key state (reset after each key event)
    active_corner = 0  # 0 for top-left (x1, y1), 1 for bottom-right (x2, y2)

    max_width = max_window_width

    def resize_to_fit(
        image: np.ndarray, max_width: int, max_height: int
    ) -> np.ndarray:
        h, w = image.shape[:2]
        scale = min(max_width / w, max_height / h)
        if scale < 1:
            new_w, new_h = int(w * scale), int(h * scale)
            return cv2.resize(
                image, (new_w, new_h), interpolation=cv2.INTER_AREA
            )
        return image

    # Use the module-level draw function (for reuse in demos)
    def draw_crop_rectangle(
        image: np.ndarray, coords: List[float], active: int
    ) -> np.ndarray:
        return draw_crop_overlay(image, coords, active)

    display_image = resize_to_fit(cv_image, max_width, max_window_height)

    cv2.namedWindow("Crop Image", cv2.WINDOW_NORMAL)
    cv2.resizeWindow(
        "Crop Image", display_image.shape[1], display_image.shape[0]
    )

    print(
        "Commands: 0-9 (enter coordinate value), Alt (switch active corner),"
        " Arrows (move active corner 10%), Home/End (switch coordinate for"
        " input), Enter (save crop), 'q' (quit)"
    )

    try:
        while True:
            display_with_crop = draw_crop_rectangle(
                display_image, crop_coords, active_corner
            )
            coord_text = f"x1: {crop_coords[0]:.2f}, y1: {crop_coords[1]:.2f}, "
            coord_text += (
                f"x2: {crop_coords[2]:.2f}, y2: {crop_coords[3]:.2f}, "
            )
            coord_text += (
                "Active:"
                f" {'Top-Left' if active_corner == 0 else 'Bottom-Right'}"
            )
            cv2.putText(
                display_with_crop,
                coord_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
            cv2.imshow("Crop Image", display_with_crop)

            key = cv2.waitKeyEx(0)
            key_code = key & 0xFFFF

            if key == 65513 or key == 65514:  # Left or Right Alt pressed
                alt_pressed = True
            else:
                alt_pressed = False

            reset_alt = True

            if key_code == 13 and not input_value:  # Enter key (save crop)
                if (
                    crop_coords[0] < crop_coords[2]
                    and crop_coords[1] < crop_coords[3]
                    and all(0 <= c <= 1 for c in crop_coords)
                ):
                    x1, y1, x2, y2 = (
                        int(c * dim)
                        for c, dim in zip(
                            crop_coords,
                            [img_width, img_height, img_width, img_height],
                        )
                    )
                    cropped_image = pil_image.crop((x1, y1, x2, y2))
                    if cropped_image.mode == "RGBA":
                        cropped_image = cropped_image.convert("RGB")
                    cropped_image.save(output_path)
                    print(f"Cropped image saved to {output_path}")
                    break
                else:
                    print(
                        "Invalid crop coordinates. Ensure x1 < x2, y1 < y2, and"
                        " all values in [0,1]."
                    )
            elif key_code == ord("q"):
                print("Exiting without saving.")
                return False
            elif key_code in [ord(str(i)) for i in range(10)] + [ord(".")]:
                input_value += chr(key_code)
            elif key_code == 8:  # Backspace
                input_value = input_value[:-1]
            elif key_code == 13 and input_value:
                try:
                    value = float(input_value)
                    if 0 <= value <= 1:
                        crop_coords[current_coord] = value
                        print(
                            f"Set {['x1', 'y1', 'x2', 'y2'][current_coord]} to"
                            f" {value:.2f}"
                        )
                    else:
                        print("Value must be between 0 and 1.")
                    input_value = ""
                except ValueError:
                    print("Invalid input. Enter a number between 0 and 1.")
                    input_value = ""
            elif key_code == 0xFF51:  # Left arrow
                if active_corner == 0:
                    crop_coords[0] = max(crop_coords[0] - 0.1, 0.0)
                    print(f"Adjusted x1 to {crop_coords[0]:.2f} (Left)")
                else:
                    crop_coords[2] = max(
                        crop_coords[2] - 0.1, crop_coords[0] + 0.01
                    )
                    print(f"Adjusted x2 to {crop_coords[2]:.2f} (Left)")
            elif key_code == 0xFF53:  # Right arrow
                if active_corner == 0:
                    crop_coords[0] = min(
                        crop_coords[0] + 0.1, crop_coords[2] - 0.01
                    )
                    print(f"Adjusted x1 to {crop_coords[0]:.2f} (Right)")
                else:
                    crop_coords[2] = min(crop_coords[2] + 0.1, 1.0)
                    print(f"Adjusted x2 to {crop_coords[2]:.2f} (Right)")
            elif key_code == 0xFF52:  # Up arrow
                if active_corner == 0:
                    crop_coords[1] = max(crop_coords[1] - 0.1, 0.0)
                    print(f"Adjusted y1 to {crop_coords[1]:.2f} (Up)")
                else:
                    crop_coords[3] = max(
                        crop_coords[3] - 0.1, crop_coords[1] + 0.01
                    )
                    print(f"Adjusted y2 to {crop_coords[3]:.2f} (Up)")
            elif key_code == 0xFF54:  # Down arrow
                if active_corner == 0:
                    crop_coords[1] = min(
                        crop_coords[1] + 0.1, crop_coords[3] - 0.01
                    )
                    print(f"Adjusted y1 to {crop_coords[1]:.2f} (Down)")
                else:
                    crop_coords[3] = min(crop_coords[3] + 0.1, 1.0)
                    print(f"Adjusted y2 to {crop_coords[3]:.2f} (Down)")
            elif key_code == 0xFF50:  # Home
                current_coord = (current_coord - 1) % 4
                input_value = ""
                print(f"Editing {['x1', 'y1', 'x2', 'y2'][current_coord]}")
            elif key_code == 0xFF57:  # End
                current_coord = (current_coord + 1) % 4
                input_value = ""
                print(f"Editing {['x1', 'y1', 'x2', 'y2'][current_coord]}")
            elif alt_pressed:
                active_corner = 1 - active_corner  # Switch between 0 and 1
                print(
                    "Switched to"
                    f" {'Top-Left' if active_corner == 0 else 'Bottom-Right'} corner"
                )
            else:
                reset_alt = False

            if reset_alt:
                alt_pressed = False

    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    finally:
        cv2.destroyAllWindows()

    return crop_coords


@typechecked
def crop_images(
    *, raw_receipt_img_filepaths: List[str], config: "Config"
) -> None:
    """Crop images and save metadata with crop coordinates, ensuring images are rotated first."""
    current_index = 0
    while current_index < len(raw_receipt_img_filepaths):
        raw_receipt_img_filepath = raw_receipt_img_filepaths[current_index]
        metadata_path = os.path.join(
            config.dir_paths.get_path(
                "receipt_images_processed_dir", absolute=True
            ),
            f"{Path(raw_receipt_img_filepath).stem}.json",
        )
        cropped_path = os.path.join(
            config.dir_paths.get_path(
                "receipt_images_processed_dir", absolute=True
            ),
            f"{Path(raw_receipt_img_filepath).stem}_cropped.jpg",
        )

        # Check if metadata exists and if rotation was applied
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = json.load(f)
            # Check if rotation was applied
            rotation_applied = any(
                op["type"] == "rotate" and op["applied"]
                for op in metadata["operations"]
            )
            # Check if crop was already applied
            crop_applied = any(
                op["type"] == "crop" and op["applied"]
                for op in metadata["operations"]
            )
            if crop_applied:
                current_index += 1
                continue
            if not rotation_applied:
                raise ValueError(
                    f"Image {raw_receipt_img_filepath} has not been rotated."
                    " Rotation must be applied before cropping."
                )
        else:
            raise ValueError(
                f"No metadata found for {raw_receipt_img_filepath}. Ensure"
                " rotation is applied first."
            )

        # Use the rotated image as input for cropping
        rotated_path = metadata.get("rotated_path", raw_receipt_img_filepath)
        if not os.path.exists(rotated_path):
            raise FileNotFoundError(
                f"Rotated image {rotated_path} not found for cropping."
            )

        print(f"cropped_path={cropped_path}")
        crop_result = crop_and_save_image(
            image_path=rotated_path, output_path=cropped_path
        )

        if crop_result is False and current_index > 0:
            current_index -= 1
            # Remove metadata and processed image to allow reprocessing
            prev_filepath = raw_receipt_img_filepaths[current_index]
            prev_metadata_path = os.path.join(
                config.dir_paths.get_path(
                    "receipt_images_processed_dir", absolute=True
                ),
                f"{Path(prev_filepath).stem}.json",
            )
            prev_cropped_path = os.path.join(
                config.dir_paths.get_path(
                    "receipt_images_processed_dir", absolute=True
                ),
                f"{Path(prev_filepath).stem}_cropped.jpg",
            )
            if os.path.exists(prev_metadata_path):
                os.remove(prev_metadata_path)
            if os.path.exists(prev_cropped_path):
                os.remove(prev_cropped_path)
            print(f"Going back to previous image: {prev_filepath}")
        else:
            # Update metadata with crop operation
            if crop_result is not False:
                # Load existing metadata to preserve rotation info
                with open(metadata_path) as f:
                    metadata = json.load(f)
                metadata["operations"].append(
                    {
                        "type": "crop",
                        "applied": True,
                        "coordinates": {
                            "x1": crop_result[0],
                            "y1": crop_result[1],
                            "x2": crop_result[2],
                            "y2": crop_result[3],
                        },
                    }
                )
                metadata["cropped_path"] = cropped_path
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2, cls=EnumEncoder)
            current_index += 1
