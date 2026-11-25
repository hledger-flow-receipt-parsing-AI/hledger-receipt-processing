"""One matplotlib window shared by every receipt while labelling.

A fresh window per receipt, closed after its questionnaire, lost the place
and size the user gave it: the next receipt opened wherever the window
manager put a new window, at the default size, so the user had to snap it
next to the terminal again for every receipt. The window now stays open for
a whole labelling session and only the photo in it changes, so it keeps
whatever place (or screen-half snap) the user gave it. A window the user
closed is reopened for the next receipt at its last place and size.

The same design as edit_images/receipt_window.py, the OpenCV window of
rotating and cropping. matplotlib is imported on first use only: headless
runs never open the window.
"""

import sys
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Tuple

from typeguard import typechecked

TITLE = "Answer the questions about this receipt in the CLI/TUI"

_session_depth = 0
# The preview figure and its axes while this module has the window open.
_figure: Any = None
_axes: Any = None
# Tk geometry ("WIDTHxHEIGHT+X+Y") of the window as last seen: when the
# user closed it, or when the session closed it. Its maximised state is not
# kept: Tk keeps reporting "-zoomed" after the window was resized, so the
# real place and size are what count.
_last_geometry: Optional[str] = None


def _is_open() -> bool:
    """Whether the preview figure is still alive. Compared by identity: once
    the user closed it, a new figure elsewhere gets its number again."""
    if _figure is None:
        return False
    from matplotlib._pylab_helpers import Gcf

    manager = _figure.canvas.manager
    return manager is not None and Gcf.figs.get(_figure.number) is manager


def _maximise(window: Any) -> None:
    # Tk on Windows has no "-zoomed" attribute (TclError); it uses state.
    if sys.platform == "win32":
        window.state("zoomed")
    else:
        window.attributes("-zoomed", True)


def _remember(window: Any) -> None:
    """Keep the window's place and size for a later reopen."""
    global _last_geometry
    try:
        window.update_idletasks()
        _last_geometry = window.geometry()
    except Exception:  # the window is already gone
        pass


def _open() -> None:
    global _figure, _axes
    from matplotlib import pyplot as plt

    plt.style.use("dark_background")
    plt.ion()
    figure = plt.figure()
    axes = figure.gca()
    # Known before anything below can fail, so the session still closes it.
    _figure, _axes = figure, axes
    figure.subplots_adjust(bottom=0, top=1, left=0, right=1)

    window = figure.canvas.manager.window
    if _last_geometry is None:
        _maximise(window)  # the first receipt: as before
    else:
        # Where the user had it. The window manager may still place a
        # reopened window itself (Wayland); an open one is never moved.
        window.geometry(_last_geometry)

    def closed_by_user() -> None:
        _remember(window)
        plt.close(figure)

    window.protocol("WM_DELETE_WINDOW", closed_by_user)


@typechecked
def show_receipt_preview(
    *, image_path: str, title: str = TITLE
) -> Tuple[Any, Any]:
    """Show the photo in the shared preview window, opening it if needed.

    An open window is never moved or resized here: its geometry is the
    user's. Returns the figure and its axes (for the highlight boxes).
    """
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as pil_img:
        image = np.asarray(pil_img.convert("RGB"))

    if not _is_open():
        _open()
    _axes.clear()
    _axes.imshow(image, origin="upper")
    _axes.set_title(title)
    _axes.axis("off")
    # Painted by Tk while the user reads "Can you see".
    _figure.canvas.draw_idle()
    return _figure, _axes


def close_receipt_preview() -> None:
    """Close the preview window, remembering where it was."""
    global _figure, _axes
    if _figure is None:
        return
    figure, _figure, _axes = _figure, None, None
    from matplotlib import pyplot as plt

    if plt.fignum_exists(figure.number):  # else the user already closed it
        _remember(figure.canvas.manager.window)
        plt.close(figure)
    plt.ioff()


@contextmanager
def receipt_preview_session() -> Iterator[None]:
    """Keep the preview window open until the outermost session ends.

    Nest freely: make_receipt_label opens its own session, and the
    labelling loop wraps all receipts in one, so the window survives from
    the first receipt to the last.
    """
    global _session_depth
    _session_depth += 1
    try:
        yield
    finally:
        _session_depth -= 1
        if _session_depth == 0:
            close_receipt_preview()
