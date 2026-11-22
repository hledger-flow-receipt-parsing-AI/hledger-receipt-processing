"""One OpenCV window shared by every receipt image while rotating/cropping.

A fresh window per image lost its position, size and keyboard focus, so the
user had to click and re-arrange the window for every next image. The
window now stays open for a whole editing session and only its image and
title change, so it keeps whatever place (or screen-half snap) the user
gave it. If it is closed and reopened later in the same run, the next image
is shown where the previous one was.
"""

from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np

WINDOW_NAME = "Receipt image"

_session_depth = 0
# Whether this module opened the window (and has not closed it since).
_window_opened = False
# Screen rectangle (x, y, width, height) of the last shown image.
_last_image_rect: Optional[Tuple[int, int, int, int]] = None


def _window_is_open() -> bool:
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:  # the window does not exist (any more)
        return False


def _image_rect() -> Tuple[int, int, int, int]:
    x, y, width, height = cv2.getWindowImageRect(WINDOW_NAME)
    return (x, y, width, height)


def _process_gui_events() -> None:
    """Let the GUI apply pending moves and resizes before measuring."""
    for _ in range(20):
        cv2.waitKey(10)


def _open_window(*, image: np.ndarray) -> None:
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    if _last_image_rect is None:
        cv2.resizeWindow(WINDOW_NAME, image.shape[1], image.shape[0])
        return

    x, y, width, height = _last_image_rect
    cv2.resizeWindow(WINDOW_NAME, width, height)
    cv2.moveWindow(WINDOW_NAME, x, y)
    cv2.imshow(WINDOW_NAME, image)
    _process_gui_events()
    # moveWindow positions the window frame, not the image inside it:
    # shift by the difference so the image lands where the last one was.
    shown_x, shown_y, _, _ = _image_rect()
    cv2.moveWindow(WINDOW_NAME, x - (shown_x - x), y - (shown_y - y))


def show_receipt_image(*, image: np.ndarray, title: str) -> None:
    """Show image in the shared receipt window, opening it if needed.

    An open window is never moved or resized here: its geometry is the
    user's.
    """
    global _window_opened
    if not (_window_opened and _window_is_open()):
        _open_window(image=image)
        _window_opened = True
    cv2.setWindowTitle(WINDOW_NAME, title)
    cv2.imshow(WINDOW_NAME, image)


def close_receipt_window() -> None:
    """Close the receipt window, remembering where its image was."""
    global _last_image_rect, _window_opened
    if not _window_opened:
        return
    _window_opened = False
    if not _window_is_open():  # the user already closed it
        return
    _last_image_rect = _image_rect()
    cv2.destroyWindow(WINDOW_NAME)
    cv2.waitKey(1)  # let the GUI actually remove it


@contextmanager
def receipt_window_session() -> Iterator[None]:
    """Keep the receipt window open until the outermost session ends.

    Nest freely: rotate/crop functions open their own session, and callers
    that rotate *and* crop wrap both in one, so the window (and its focus)
    survives from the first image to the last.
    """
    global _session_depth
    _session_depth += 1
    try:
        yield
    finally:
        _session_depth -= 1
        if _session_depth == 0:
            close_receipt_window()
