"""Group duplicate receipt images before labelling.

Auto-groups byte-identical images (SHA256 hash), then optionally lets the
user interactively group remaining images via a matplotlib preview.

Images that already have a label are skipped entirely.
Grouping state is saved after every user decision so progress survives
interruption.
"""

import json
import logging
import os
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from typeguard import typechecked

from hledger_config.config.Config import Config
from hledger_config.config.load_config import raw_receipt_img_filepath_to_cropped
from hledger_config.dir_reading_and_writing import get_receipt_folder_name
from hledger_core.file_reading_and_writing import get_image_hash
from hledger_core.generics.enums import ClassifierType, LogicType

log = logging.getLogger(__name__)

GROUPING_FILENAME = "image_grouping.json"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@typechecked
def _label_filename() -> str:
    return (
        f"{ClassifierType.RECEIPT_IMAGE_TO_OBJ.value}"
        f"_{LogicType.LABEL.value}.json"
    )


@typechecked
def build_labelled_raw_paths(*, config: Config) -> Dict[str, str]:
    """Scan all label JSONs and return a mapping of raw image path →
    label filepath.

    This handles the case where a cropped image was re-created (changing
    its hash) so the hash-based lookup in ``image_has_label`` would fail.
    No caching — always returns a fresh result.
    """
    labels_dir = config.dir_paths.get_path("receipt_labels_dir", absolute=True)
    if not os.path.isdir(labels_dir):
        return {}
    fname = _label_filename()
    result: Dict[str, str] = {}
    for entry in os.listdir(labels_dir):
        label_path = os.path.join(labels_dir, entry, fname)
        if not os.path.isfile(label_path):
            continue
        try:
            with open(label_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            raw_paths = data.get("raw_img_filepaths", [])
            if isinstance(raw_paths, str):
                raw_paths = [raw_paths]
            for p in raw_paths:
                result[p] = label_path
        except (json.JSONDecodeError, OSError):
            continue
    return result


@typechecked
def image_has_label(*, config: Config, raw_img_filepath: str) -> bool:
    """Return True if a label JSON already exists for this raw image."""
    # Fast path: hash-based lookup.
    cropped = raw_receipt_img_filepath_to_cropped(
        config=config, raw_receipt_img_filepath=raw_img_filepath
    )
    if os.path.isfile(cropped):
        receipt_folder_name = get_receipt_folder_name(
            cropped_receipt_img_filepath=cropped
        )
        labels_dir = config.dir_paths.get_path(
            "receipt_labels_dir", absolute=True
        )
        label_path = os.path.join(
            labels_dir, receipt_folder_name, _label_filename()
        )
        if os.path.isfile(label_path):
            return True

    # Slow path: the cropped image may have been re-created (hash
    # changed).  Fall back to scanning label JSONs for raw_img_filepaths.
    return raw_img_filepath in build_labelled_raw_paths(config=config)


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


@typechecked
def _grouping_filepath(*, config: Config) -> str:
    return os.path.join(
        config.dir_paths.get_path("receipt_images_processed_dir", absolute=True),
        GROUPING_FILENAME,
    )


@typechecked
def save_image_grouping(*, config: Config, groups: List[List[str]]) -> None:
    filepath = _grouping_filepath(config=config)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=2)
    log.info("Saved image grouping (%d groups) to %s", len(groups), filepath)


@typechecked
def load_image_grouping(*, config: Config) -> Optional[List[List[str]]]:
    filepath = _grouping_filepath(config=config)
    if not os.path.isfile(filepath):
        return None
    with open(filepath, encoding="utf-8") as f:
        groups: List[List[str]] = json.load(f)
    # Filter out files that no longer exist instead of discarding the
    # entire grouping.  This preserves valid groups when only some
    # images have been removed.
    cleaned: List[List[str]] = []
    stale_count = 0
    repeated_count = 0
    seen: set = set()
    for group in groups:
        valid = [p for p in group if os.path.isfile(p)]
        removed = len(group) - len(valid)
        if removed:
            stale_count += removed
            for p in group:
                if not os.path.isfile(p):
                    log.warning("Stale grouping entry removed: %s", p)
        # An image belongs to one receipt: keep its first group only.
        unseen = [p for p in valid if p not in seen]
        repeated_count += len(valid) - len(unseen)
        seen.update(unseen)
        if unseen:
            cleaned.append(unseen)
    if stale_count:
        log.info(
            "Removed %d stale path(s) from saved grouping.", stale_count
        )
    if repeated_count:
        log.warning(
            "Removed %d path(s) already listed in an earlier group.",
            repeated_count,
        )
    if not cleaned:
        return None
    log.info(
        "Loaded saved image grouping (%d groups) from %s",
        len(cleaned),
        filepath,
    )
    return cleaned


# ------------------------------------------------------------------
# Auto-grouping (byte-identical via SHA256)
# ------------------------------------------------------------------


@typechecked
def auto_group_by_hash(
    *, config: Config, image_paths: List[str]
) -> Tuple[List[List[str]], List[str]]:
    """Group byte-identical images by SHA256 hash of the cropped version.

    Hashing the cropped image means that two different raw photos which
    produce the same crop are correctly identified as duplicates.

    Returns
    -------
    groups : List[List[str]]
        Groups that contain >1 image (true duplicates).  Index 0 is the
        primary (first alphabetically).
    unique : List[str]
        Images that had no duplicates.
    """
    hash_to_paths: Dict[str, List[str]] = OrderedDict()
    for path in image_paths:
        cropped = raw_receipt_img_filepath_to_cropped(
            config=config, raw_receipt_img_filepath=path
        )
        # Use cropped image for hashing if it exists, else fall back to raw.
        hash_target = cropped if os.path.isfile(cropped) else path
        h = get_image_hash(image_path=hash_target)
        hash_to_paths.setdefault(h, []).append(path)

    groups: List[List[str]] = []
    unique: List[str] = []
    for h, paths in hash_to_paths.items():
        if len(paths) > 1:
            log.info(
                "Auto-grouped %d identical images (hash %s…): %s",
                len(paths),
                h[:12],
                [os.path.basename(p) for p in paths],
            )
            groups.append(paths)
        else:
            unique.append(paths[0])
    return groups, unique


# ------------------------------------------------------------------
# Interactive grouping (matplotlib preview with keyboard on figure)
# ------------------------------------------------------------------


class _GroupingAborted(Exception):
    """Raised when the user quits the interactive grouping session.

    ``groups`` holds the groups decided before quitting.
    """

    def __init__(self, groups: List[List[str]]) -> None:
        super().__init__("grouping aborted")
        self.groups = groups


@typechecked
def interactive_group_images(
    *,
    config: Config,
    image_paths: List[str],
    keep_groups: Optional[List[List[str]]] = None,
) -> List[List[str]]:
    """Show images in pairs and let the user group them interactively.

    The first image starts the first group, so the first question already
    compares two images: the current group's prime (left) and the next
    image (right).  Every question reuses one window, so a maximised or
    resized window keeps its size, position and focus.

    Keyboard shortcuts are captured directly on the matplotlib figure
    window so the user does not need to alt-tab to the terminal.

    Keys
    ----
    n — new receipt (the right image starts a new group as its prime)
    g — group with previous (add the right image to the current group)
    p — prime & group (add it to the current group AND make it the prime)
    x — exclude the right image (skip it)
    q / Escape — quit (stop grouping, keep the decisions made so far)

    After every decision ``keep_groups`` plus the groups so far are saved,
    so progress survives interruption (Ctrl-C).

    Returns a list of groups.  Index 0 in each group is the prime image.

    Raises ``_GroupingAborted`` (carrying the groups so far) if the user
    presses q/Escape or closes the window.
    """
    from matplotlib import pyplot as plt
    from PIL import Image

    from hledger_receipt_processing.receipts_to_objects.edit_images.gui_environment import (  # noqa: E501
        assert_grouping_environment,
    )

    if not image_paths:
        return []
    groups: List[List[str]] = []
    current_group: List[str] = [image_paths[0]]
    if len(image_paths) == 1:
        # Nothing to compare it with: it is its own receipt.
        return [current_group]
    assert_grouping_environment()

    def _display_path(raw_path: str) -> str:
        """Return the cropped image path if available, else the raw path."""
        cropped = raw_receipt_img_filepath_to_cropped(
            config=config, raw_receipt_img_filepath=raw_path
        )
        return cropped if os.path.isfile(cropped) else raw_path

    def _show(ax, raw_path: str, title: str) -> None:
        with Image.open(_display_path(raw_path)) as img:
            ax.imshow(img)
        ax.set_title(title, color="white", fontsize=10)
        ax.axis("off")

    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor("black")
    help_text = "  |  ".join(
        [
            "(n)ew receipt",
            "(g)roup with prev",
            "(p)rime & group",
            "e(x)clude  |  (q)uit",
        ]
    )

    key_result: List[Optional[str]] = [None]

    def _on_key(event) -> None:
        key = event.key.lower() if event.key else ""
        if key == "escape":
            key = "q"
        if key in ("n", "g", "p", "x", "q"):
            key_result[0] = key

    fig.canvas.mpl_connect("key_press_event", _on_key)

    # The window stays open between questions, so matplotlib's own
    # p (pan mode) and g (grid) shortcuts would otherwise stick.
    try:
        with plt.rc_context({"keymap.pan": [], "keymap.grid": []}):
            for idx in range(1, len(image_paths)):
                img_path = image_paths[idx]
                fig.clf()
                ax_prev, ax_new = fig.subplots(1, 2)
                _show(
                    ax_prev,
                    current_group[0],
                    f"Current group prime ({len(current_group)} img(s))\n"
                    f"{os.path.basename(current_group[0])}",
                )
                _show(
                    ax_new,
                    img_path,
                    f"[{idx + 1}/{len(image_paths)}]"
                    f" {os.path.basename(img_path)}",
                )
                fig.text(
                    0.5, 0.02, help_text,
                    ha="center", va="bottom", fontsize=14,
                    color="yellow", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.4", fc="black", alpha=0.8),
                )
                fig.tight_layout(rect=[0, 0.06, 1, 1])
                fig.canvas.draw_idle()
                if idx == 1:
                    plt.show(block=False)

                # Block until the user presses a valid key.
                key_result[0] = None
                while key_result[0] is None and plt.fignum_exists(
                    fig.number
                ):
                    plt.pause(0.05)
                choice = key_result[0]

                if choice is None:  # window closed (Alt-F4, X button)
                    print("\nGrouping aborted (window closed).")
                    raise _GroupingAborted(groups + [current_group])
                if choice == "q":
                    print("\nGrouping aborted by user.")
                    raise _GroupingAborted(groups + [current_group])

                if choice == "n":
                    groups.append(current_group)
                    current_group = [img_path]
                elif choice == "g":
                    current_group.append(img_path)
                elif choice == "p":
                    current_group.insert(0, img_path)
                elif choice == "x":
                    log.info("Excluded: %s", os.path.basename(img_path))
                    print(f"  Excluded: {os.path.basename(img_path)}")

                # Save after every decision so progress survives Ctrl-C
                save_image_grouping(
                    config=config,
                    groups=(keep_groups or []) + groups + [current_group],
                )
    finally:
        plt.close(fig)

    return groups + [current_group]


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


@typechecked
def group_receipt_images(
    *, config: Config, image_paths: List[str]
) -> List[List[str]]:
    """Group receipt images: auto-deduplicate then interactive grouping.

    Images that already have a label are skipped (not shown at all).

    Returns a list of groups where each group is a ``List[str]`` of image
    paths.  Index 0 in each group is the *prime* image used for cropping
    and labelling.
    """
    if not image_paths:
        return []

    # Phase 0: filter out images that already have a label
    unlabelled: List[str] = []
    already_labelled: List[str] = []
    for img_path in image_paths:
        if image_has_label(config=config, raw_img_filepath=img_path):
            already_labelled.append(img_path)
        else:
            unlabelled.append(img_path)

    if already_labelled:
        print(
            f"\nSkipping {len(already_labelled)} image(s) that already have"
            " a label."
        )

    if not unlabelled:
        print("All images already labelled. Nothing to group.")
        return [[img] for img in already_labelled]

    # Phase 1: auto-group byte-identical images among unlabelled
    duplicate_groups, unique_images = auto_group_by_hash(
        config=config, image_paths=unlabelled
    )

    if duplicate_groups:
        print(
            f"\nAuto-grouped {sum(len(g) for g in duplicate_groups)} images "
            f"into {len(duplicate_groups)} duplicate group(s)."
        )
        for i, group in enumerate(duplicate_groups):
            print(
                f"  Group {i + 1}: {[os.path.basename(p) for p in group]}"
            )

    # Saved groups of images outside this run stay in the file, also in
    # the saves made after every interactive decision.
    being_grouped = set(image_paths)
    kept_groups = [
        kept
        for kept in (
            [p for p in group if p not in being_grouped]
            for group in load_image_grouping(config=config) or []
        )
        if kept
    ]
    decided_groups = [[img] for img in already_labelled] + duplicate_groups

    # Phase 2: interactive grouping of remaining unique images
    interactive_groups: List[List[str]] = []
    aborted = False
    if unique_images:
        print(
            f"\n{len(unique_images)} unique image(s) to review interactively."
        )
        print("Keys on the image window: (n)ew receipt, (g)roup with prev,")
        print("  (p)rime & group, e(x)clude, (q)uit/Esc.\n")
        try:
            interactive_groups = interactive_group_images(
                config=config,
                image_paths=unique_images,
                keep_groups=kept_groups + decided_groups,
            )
        except _GroupingAborted as aborted_grouping:
            aborted = True
            interactive_groups = aborted_grouping.groups

    # Combine: already-labelled as singletons + auto-groups + interactive
    all_groups = decided_groups + interactive_groups

    # Persist final result
    save_image_grouping(config=config, groups=kept_groups + all_groups)

    n_new = len(duplicate_groups) + len(interactive_groups)
    status = " (aborted early)" if aborted else ""
    print(
        f"\nFinal: {n_new} new group(s) to label"
        f" ({len(already_labelled)} already labelled).{status}"
    )
    for i, group in enumerate(duplicate_groups + interactive_groups):
        prime = os.path.basename(group[0])
        others = [os.path.basename(p) for p in group[1:]]
        suffix = f" + {others}" if others else ""
        print(f"  {i + 1}. [prime] {prime}{suffix}")

    return all_groups
