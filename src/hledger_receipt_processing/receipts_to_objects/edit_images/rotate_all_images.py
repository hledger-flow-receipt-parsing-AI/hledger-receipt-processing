import json
import os
from pathlib import Path
from typing import List, Union

import cv2
import numpy as np
import screeninfo  # Required for getting screen resolution
from PIL import Image
from typeguard import typechecked

from hledger_config.config.Config import Config
from hledger_config.config.ReceiptImgConfig import ReceiptImgConfig


@typechecked
def rotate_and_save_image(
    *,
    image_path: str,
    output_path: str,
    max_window_width: int = 1280,
    max_window_height: int = 720,
) -> Union[int, bool]:
    """
    Opens an image, displays it scaled to fit the OpenCV window, allows user to rotate it by pressing
    'r' (right) or 'l' (left), revert with 'Backspace', and saves it when Enter is pressed.

    Args:
        image_path (str): Path to the input image
        output_path (str): Path to save the rotated image
        max_window_width (int): Maximum width of the display window (default: 1280)
        max_window_height (int): Maximum height of the display window (default: 720)

    Returns:
        Union[int, bool]: Rotation angle in degrees (0, 90, 180, 270) or False if reverting to previous image
    """
    # Load image with PIL for rotation
    try:
        pil_image = Image.open(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return False

    # Convert PIL image to OpenCV format for display
    if pil_image.mode == "RGBA":
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGBA2BGR)
    else:
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    rotation_angle = 0  # Cumulative rotation in degrees
    angle_history = [0]  # Store history of rotation angles, starting with 0

    # Set maximum window dimensions
    max_width, max_height = max_window_width, max_window_height

    # Function to resize image for display while preserving aspect ratio
    def resize_to_fit(
        image: np.ndarray, max_width: int, max_height: int
    ) -> np.ndarray:
        h, w = image.shape[:2]
        scale = min(max_width / w, max_height / h)
        if scale < 1:  # Only resize if image is larger than max dimensions
            new_w, new_h = int(w * scale), int(h * scale)
            return cv2.resize(
                image, (new_w, new_h), interpolation=cv2.INTER_AREA
            )
        return image

    # Initial resize for display
    display_image = resize_to_fit(cv_image, max_width, max_height)

    # Create and resize OpenCV window
    cv2.namedWindow("Image", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Image", display_image.shape[1], display_image.shape[0])

    # Display instructions
    print(
        "Commands: 'r' (rotate 90° clockwise), 'l' (rotate 90°"
        " counter-clockwise), BaCkspace (undo last rotation), Enter (save and"
        " exit), 'q' (quit without saving)"
    )

    try:
        while True:
            # Display the resized image
            cv2.imshow("Image", display_image)
            key = cv2.waitKey(0) & 0xFF  # Wait for a keypress

            if key == 13:  # Enter key
                if rotation_angle != 0:
                    # Save the rotated image using original PIL image
                    rotated_image = pil_image.rotate(
                        -rotation_angle, expand=True
                    )
                else:
                    rotated_image = pil_image
                # Convert RGBA to RGB for JPEG output.
                if rotated_image.mode == "RGBA":
                    rotated_image = rotated_image.convert("RGB")
                rotated_image.save(output_path)
                print(
                    f"Rotated: {rotation_angle} [degrees], image saved to"
                    f" {output_path}"
                )

                break
            elif key == ord("r"):  # Rotate right (clockwise)
                rotation_angle = (rotation_angle + 90) % 360
                angle_history.append(rotation_angle)  # Add new angle to history
            elif key == ord("l"):  # Rotate left (counter-clockwise)
                rotation_angle = (rotation_angle - 90) % 360
                angle_history.append(rotation_angle)  # Add new angle to history
            elif key == 8:  # Backspace key
                if (
                    len(angle_history) > 1
                ):  # Ensure there's a previous state to revert to
                    angle_history.pop()  # Remove current angle
                    rotation_angle = angle_history[
                        -1
                    ]  # Revert to previous angle
                    print(f"Reverted to rotation angle: {rotation_angle}°")
                else:
                    print("No previous rotation to revert to.")
                    return False
            elif key == ord("q"):  # Quit without saving
                print("Exiting without saving.")
                break
            else:
                continue  # Ignore other keys

            # Update displayed image
            pil_image_rotated = pil_image.rotate(-rotation_angle, expand=True)
            if pil_image_rotated.mode == "RGBA":
                cv_image = cv2.cvtColor(
                    np.array(pil_image_rotated), cv2.COLOR_RGBA2BGR
                )
            else:
                cv_image = cv2.cvtColor(
                    np.array(pil_image_rotated), cv2.COLOR_RGB2BGR
                )
            display_image = resize_to_fit(cv_image, max_width, max_height)
            # Update window size if image dimensions change after rotation
            cv2.resizeWindow(
                "Image", display_image.shape[1], display_image.shape[0]
            )

    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    finally:
        # Clean up OpenCV windows
        cv2.destroyAllWindows()
    return rotation_angle


import json
import os
from pathlib import Path
from typing import List

from typeguard import typechecked


@typechecked
def rotate_images(
    *, raw_receipt_img_filepaths: List[str], config: "Config"
) -> None:
    """Rotate images and save metadata with rotation angle, skipping already rotated images if rotated image exists."""
    current_index = 0
    receipt_img_filenames: ReceiptImgConfig = config.file_names.receipt_img
    while current_index < len(raw_receipt_img_filepaths):
        raw_receipt_img_filepath = raw_receipt_img_filepaths[current_index]
        metadata_path = os.path.join(
            config.dir_paths.get_path(
                "receipt_images_processed_dir", absolute=True
            ),
            f"{Path(raw_receipt_img_filepath).stem}{receipt_img_filenames.processing_metadata_ext}",
        )
        rotated_path = os.path.join(
            config.dir_paths.get_path(
                "receipt_images_processed_dir", absolute=True
            ),
            f"{Path(raw_receipt_img_filepath).stem}{receipt_img_filenames.rotate}{receipt_img_filenames.rotate_ext}",
        )

        # Check if metadata exists
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = json.load(f)
            # Check if rotation was applied
            rotation_applied = any(
                op["type"] == "rotate" and op["applied"]
                for op in metadata["operations"]
            )
            # If rotation was applied, verify the rotated image exists
            if rotation_applied and os.path.exists(rotated_path):
                current_index += 1
                continue
            elif rotation_applied:
                # Rotated image is missing, remove metadata to allow re-rotation
                os.remove(metadata_path)
                print(
                    f"Rotated image {rotated_path} missing, removed metadata to"
                    " reprocess."
                )

        print(f"rotated_path={rotated_path}")
        rotation_result = rotate_and_save_image(
            image_path=raw_receipt_img_filepath, output_path=rotated_path
        )

        if rotation_result is False and current_index > 0:
            current_index -= 1
            # Remove metadata and processed image to allow reprocessing
            prev_filepath = raw_receipt_img_filepaths[current_index]
            prev_metadata_path = os.path.join(
                config.dir_paths.get_path(
                    "receipt_images_processed_dir", absolute=True
                ),
                f"{Path(prev_filepath).stem}{receipt_img_filenames.processing_metadata_ext}",
            )
            prev_rotated_path = os.path.join(
                config.dir_paths.get_path(
                    "receipt_images_processed_dir", absolute=True
                ),
                f"{Path(prev_filepath).stem}{receipt_img_filenames.rotate}{receipt_img_filenames.rotate_ext}",
            )
            if os.path.exists(prev_metadata_path):
                os.remove(prev_metadata_path)
            if os.path.exists(prev_rotated_path):
                os.remove(prev_rotated_path)
            print(f"Going back to previous image: {prev_filepath}")
        else:
            # Save metadata if image was saved
            if rotation_result is not False:
                metadata = {
                    "operations": [
                        {
                            "type": "rotate",
                            "applied": True,
                            "angle_degrees": rotation_result,
                        }
                    ],
                    "original_path": raw_receipt_img_filepath,
                    "rotated_path": rotated_path,
                }
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)
            current_index += 1
