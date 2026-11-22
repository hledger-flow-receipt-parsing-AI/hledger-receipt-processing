"""Pre-flight check that receipt images can be shown in interactive windows.

Rotating and cropping receipt images opens OpenCV windows; grouping them
opens a matplotlib window. Both need a GUI-capable build and a display.
Without them the labeller used to crash deep inside ``cv2.namedWindow``.
These checks run before the first window is needed and say how to fix the
environment.
"""

import json
import os
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Collection, List, Mapping, Optional, Set

from typeguard import typechecked

from hledger_config.config.Config import Config
from hledger_config.config.ReceiptImgConfig import ReceiptImgConfig

# Headless pip builds of OpenCV and the GUI build that replaces each one.
_GUI_REPLACEMENT = {
    "opencv-python-headless": "opencv-python",
    "opencv-contrib-python-headless": "opencv-contrib-python",
}
# Every pip distribution that provides ``cv2``. They all install into the
# same ``cv2`` folder, so whichever was installed last wins.
OPENCV_DISTRIBUTIONS = (
    "opencv-python",
    "opencv-contrib-python",
    *_GUI_REPLACEMENT,
)

# Toolkit lines in the GUI section of older OpenCV build information.
_TOOLKIT_KEY = re.compile(
    r"^(QT|GTK|Win32 UI|Cocoa|Wayland|Framebuffer)", re.IGNORECASE
)

_NON_INTERACTIVE_MPL_BACKENDS = {
    "agg",
    "cairo",
    "pdf",
    "pgf",
    "ps",
    "svg",
    "template",
}

_MAX_LISTED_IMAGES = 5


class GuiEnvironmentError(RuntimeError):
    """The environment cannot open the receipt image windows."""


@typechecked
def opencv_gui_backend(*, build_information: Optional[str] = None) -> str:
    """Return the GUI toolkit OpenCV was built with, or "" if it has none.

    Build information without a recognisable GUI section returns "unknown",
    so a format change in a future OpenCV never blocks a working setup.
    """
    if build_information is None:
        import cv2

        build_information = cv2.getBuildInformation()

    lines = build_information.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("GUI:"):
            continue
        value = stripped[len("GUI:") :].strip()
        if value:
            return "" if value.upper() == "NONE" else value
        # Older builds list each toolkit on its own, deeper indented line.
        indent = len(line) - len(line.lstrip())
        for sub_line in lines[index + 1 :]:
            if not sub_line.strip():
                break
            if len(sub_line) - len(sub_line.lstrip()) <= indent:
                break
            key, _, sub_value = sub_line.strip().partition(":")
            key = key.strip()
            if _TOOLKIT_KEY.match(key) and sub_value.strip().upper().startswith(
                "YES"
            ):
                return key
        return ""
    return "unknown"


@typechecked
def has_display(
    *,
    environ: Optional[Mapping[str, str]] = None,
    platform: Optional[str] = None,
) -> bool:
    """Return whether a window can be shown (always true on macOS/Windows)."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if platform.startswith(("win32", "darwin")):
        return True
    return bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


@typechecked
def installed_opencv_distributions() -> List[str]:
    """Return the pip OpenCV distributions installed in this environment."""
    found: List[str] = []
    for name in OPENCV_DISTRIBUTIONS:
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        found.append(name)
    return found


def _applied_operations(*, metadata_path: str) -> Set[str]:
    try:
        with open(metadata_path) as f:
            operations = json.load(f).get("operations", [])
    except (OSError, ValueError):
        return set()
    return {op.get("type") for op in operations if op.get("applied")}


@typechecked
def images_needing_manual_editing(
    *,
    raw_receipt_img_filepaths: List[str],
    processed_dir: str,
    receipt_img_config: ReceiptImgConfig,
) -> List[str]:
    """Return the images that rotate_images/crop_images would still show.

    Mirrors their skip rules: an image is done once its metadata records an
    applied rotation and an applied crop, and the rotated image exists.
    """
    pending: List[str] = []
    for raw_filepath in raw_receipt_img_filepaths:
        stem = Path(raw_filepath).stem
        metadata_path = os.path.join(
            processed_dir,
            f"{stem}{receipt_img_config.processing_metadata_ext}",
        )
        rotated_path = os.path.join(
            processed_dir,
            f"{stem}{receipt_img_config.rotate}{receipt_img_config.rotate_ext}",
        )
        applied = _applied_operations(metadata_path=metadata_path)
        if {"rotate", "crop"} <= applied and os.path.exists(rotated_path):
            continue
        pending.append(raw_filepath)
    return pending


def _display_fix_lines() -> List[str]:
    return [
        "No display found (neither DISPLAY nor WAYLAND_DISPLAY is set).",
        "Run this from a terminal inside your desktop session, or connect"
        " with `ssh -X`, so the windows can open.",
    ]


def _opencv_fix_lines(
    *, installed_opencv: Collection[str], python_executable: str
) -> List[str]:
    installed = [d for d in OPENCV_DISTRIBUTIONS if d in installed_opencv]
    if not installed:
        return [
            "OpenCV (cv2) was built without GUI support, and it is not a pip"
            " package this check recognises (conda or system OpenCV?).",
            "Remove that OpenCV and install the GUI build, e.g.:",
            f"  {python_executable} -m pip install opencv-python",
        ]
    replacement = (
        "opencv-contrib-python"
        if any("contrib" in d for d in installed)
        else "opencv-python"
    )
    headless = [d for d in installed if d in _GUI_REPLACEMENT]
    if headless:
        reason = (
            f"OpenCV is the headless build ({', '.join(headless)}), which has"
            " no GUI support."
        )
    else:
        reason = "OpenCV (cv2) was built without GUI support."
    return [
        reason,
        "Replace it with the GUI build. Uninstall first: all OpenCV builds"
        " share one cv2 folder.",
        f"  {python_executable} -m pip uninstall -y {' '.join(installed)}",
        f"  {python_executable} -m pip install {replacement}",
    ]


@typechecked
def image_editing_environment_problem(
    *,
    pending_images: List[str],
    gui_backend: str,
    display_available: bool,
    installed_opencv: Collection[str],
    python_executable: str,
    input_dir: str,
) -> Optional[str]:
    """Return fix instructions if pending images cannot be edited, else None."""
    if not pending_images or (gui_backend and display_available):
        return None

    count = len(pending_images)
    noun = "image" if count == 1 else "images"
    lines = [
        f"{count} receipt {noun} still need to be rotated and cropped in an"
        " OpenCV window, but this environment cannot open one.",
        "",
    ]
    if not gui_backend:
        lines += _opencv_fix_lines(
            installed_opencv=installed_opencv,
            python_executable=python_executable,
        )
    if not display_available:
        lines += _display_fix_lines()
    lines += [
        "",
        "Or label the already processed images first: move these out of"
        f" {input_dir} and add them back once the environment is fixed:",
    ]
    lines += [
        f"  {os.path.basename(p)}" for p in pending_images[:_MAX_LISTED_IMAGES]
    ]
    if count > _MAX_LISTED_IMAGES:
        lines.append(f"  ... and {count - _MAX_LISTED_IMAGES} more")
    return "\n".join(lines)


@typechecked
def grouping_environment_problem(
    *,
    matplotlib_backend: str,
    display_available: bool,
    mplbackend_env: Optional[str],
) -> Optional[str]:
    """Return fix instructions if the grouping window cannot open, else None."""
    backend = matplotlib_backend.lower()
    non_interactive = backend in _NON_INTERACTIVE_MPL_BACKENDS or (
        backend.startswith("module://matplotlib_inline")
    )
    if display_available and not non_interactive:
        return None

    lines = [
        "Grouping receipt images opens a matplotlib window, but this"
        " environment cannot open one.",
        "",
    ]
    if not display_available:
        lines += _display_fix_lines()
    if mplbackend_env and non_interactive:
        lines.append(
            f"MPLBACKEND={mplbackend_env} selects the non-interactive"
            f" '{matplotlib_backend}' backend: run `unset MPLBACKEND`."
        )
    elif non_interactive and display_available:
        lines += [
            f"matplotlib uses the non-interactive '{matplotlib_backend}'"
            " backend because no GUI toolkit is available.",
            "Install Tk for this Python, e.g. `conda install tk` (conda env)"
            " or `sudo apt install python3-tk` (system Python).",
        ]
    return "\n".join(lines)


@typechecked
def assert_image_editing_environment(
    *, raw_receipt_img_filepaths: List[str], config: Config
) -> None:
    """Raise GuiEnvironmentError if pending images cannot be rotated/cropped."""
    pending = images_needing_manual_editing(
        raw_receipt_img_filepaths=raw_receipt_img_filepaths,
        processed_dir=config.dir_paths.get_path(
            "receipt_images_processed_dir", absolute=True
        ),
        receipt_img_config=config.file_names.receipt_img,
    )
    if not pending:
        return
    problem = image_editing_environment_problem(
        pending_images=pending,
        gui_backend=opencv_gui_backend(),
        display_available=has_display(),
        installed_opencv=installed_opencv_distributions(),
        python_executable=sys.executable,
        input_dir=config.dir_paths.get_path(
            "receipt_images_input_dir", absolute=True
        ),
    )
    if problem:
        raise GuiEnvironmentError(problem)


@typechecked
def assert_grouping_environment() -> None:
    """Raise GuiEnvironmentError if the grouping window cannot open."""
    import matplotlib

    problem = grouping_environment_problem(
        matplotlib_backend=matplotlib.get_backend(),
        display_available=has_display(),
        mplbackend_env=os.environ.get("MPLBACKEND"),
    )
    if problem:
        raise GuiEnvironmentError(problem)
