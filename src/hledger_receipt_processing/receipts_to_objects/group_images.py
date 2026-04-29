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
def image_has_label(*, config: Config, raw_img_filepath: str) -> bool:
    """Return True if a label JSON already exists for this raw image."""
    cropped = raw_receipt_img_filepath_to_cropped(
        config=config, raw_receipt_img_filepath=raw_img_filepath
    )
    if not os.path.isfile(cropped):
        return False
    receipt_folder_name = get_receipt_folder_name(
        cropped_receipt_img_filepath=cropped
    )
    labels_dir = config.dir_paths.get_path("receipt_labels_dir", absolute=True)
    label_path = os.path.join(labels_dir, receipt_folder_name, _label_filename())
    return os.path.isfile(label_path)


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
    for group in groups:
        valid = [p for p in group if os.path.isfile(p)]
        removed = len(group) - len(valid)
        if removed:
            stale_count += removed
            for p in group:
                if not os.path.isfile(p):
                    log.warning("Stale grouping entry removed: %s", p)
        if valid:
            cleaned.append(valid)
    if stale_count:
        log.info(
            "Removed %d stale path(s) from saved grouping.", stale_count
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
    """Raised when the user quits the interactive grouping session."""


@typechecked
def interactive_group_images(
    *, config: Config, image_paths: List[str]
) -> List[List[str]]:
    """Show images one-by-one and let the user group them interactively.

    Keyboard shortcuts are captured directly on the matplotlib figure
    window so the user does not need to alt-tab to the terminal.

    Keys
    ----
    n — new receipt (start a new group with this image as prime)
    g — group with previous (add to current group as secondary)
    p — prime & group (add to current group AND make this image the prime)
    x — skip / exclude this image
    q / Escape — quit (abort grouping, save progress so far)

    Grouping is saved to disk after every decision so progress survives
    interruption (Ctrl-C).

    Returns a list of groups.  Index 0 in each group is the prime image.

    Raises ``_GroupingAborted`` if the user presses q/Escape or closes
    the window.
    """
    from matplotlib import pyplot as plt
    from PIL import Image

    if not image_paths:
        return []

    groups: List[List[str]] = []
    current_group: List[str] = []

    def _display_path(raw_path: str) -> str:
        """Return the cropped image path if available, else the raw path."""
        cropped = raw_receipt_img_filepath_to_cropped(
            config=config, raw_receipt_img_filepath=raw_path
        )
        return cropped if os.path.isfile(cropped) else raw_path

    for idx, img_path in enumerate(image_paths):
        display_file = _display_path(img_path)
        img = Image.open(display_file)

        fig, axes = plt.subplots(1, 2 if current_group else 1, figsize=(16, 10))
        fig.patch.set_facecolor("black")

        if current_group:
            # Show current group's prime (cropped) on the left
            ax_prev = axes[0]
            prime_display = _display_path(current_group[0])
            prime_img = Image.open(prime_display)
            ax_prev.imshow(prime_img)
            ax_prev.set_title(
                f"Current group prime ({len(current_group)} img(s))\n"
                f"{os.path.basename(current_group[0])}",
                color="white",
                fontsize=10,
            )
            ax_prev.axis("off")
            ax_new = axes[1]
        else:
            ax_new = axes if not hasattr(axes, '__len__') else axes[0]

        ax_new.imshow(img)
        ax_new.set_title(
            f"[{idx + 1}/{len(image_paths)}] {os.path.basename(img_path)}",
            color="white",
            fontsize=10,
        )
        ax_new.axis("off")

        # Build help text overlay on the figure
        help_parts = ["(n)ew receipt"]
        if current_group:
            help_parts += ["(g)roup with prev", "(p)rime & group"]
        help_parts.append("e(x)clude  |  (q)uit")
        help_text = "  |  ".join(help_parts)

        fig.text(
            0.5, 0.02, help_text,
            ha="center", va="bottom", fontsize=14,
            color="yellow", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc="black", alpha=0.8),
        )

        plt.tight_layout(rect=[0, 0.06, 1, 1])

        # Capture key press on the matplotlib figure window directly —
        # no need to alt-tab to the terminal.
        key_result: List[Optional[str]] = [None]

        def _on_key(event, _current_group=current_group):
            key = event.key.lower() if event.key else ""
            # q and escape always quit
            if key in ("q", "escape"):
                key_result[0] = "q"
                plt.close(fig)
                return
            valid = {"n", "x"}
            if _current_group:
                valid |= {"g", "p"}
            if key in valid:
                key_result[0] = key
                plt.close(fig)

        fig.canvas.mpl_connect("key_press_event", _on_key)

        plt.ion()
        plt.show()

        # Block until the user presses a valid key (closes the figure)
        while key_result[0] is None and plt.fignum_exists(fig.number):
            plt.pause(0.05)

        plt.ioff()

        # Window closed without a key press (Alt-F4, X button) → abort
        if key_result[0] is None:
            if current_group:
                groups.append(current_group)
            print("\nGrouping aborted (window closed).")
            raise _GroupingAborted()

        choice = key_result[0]

        # q/Escape → abort
        if choice == "q":
            if current_group:
                groups.append(current_group)
            print("\nGrouping aborted by user.")
            raise _GroupingAborted()

        if choice == "n":
            if current_group:
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
        partial = groups + ([current_group] if current_group else [])
        save_image_grouping(config=config, groups=partial)

    # Don't forget the last group
    if current_group:
        groups.append(current_group)

    return groups


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
                config=config, image_paths=unique_images
            )
        except _GroupingAborted:
            aborted = True
            # interactive_group_images saves partial progress via
            # save_image_grouping on every step, so whatever the user
            # completed is already on disk.  Reload it.
            saved = load_image_grouping(config=config)
            if saved is not None:
                # Return saved partial progress as-is (includes any
                # already-labelled singletons that were persisted).
                print(f"Returning {len(saved)} group(s) from partial save.")
                return saved

    # Combine: already-labelled as singletons + auto-groups + interactive
    all_groups = (
        [[img] for img in already_labelled]
        + duplicate_groups
        + interactive_groups
    )

    # Persist final result
    save_image_grouping(config=config, groups=all_groups)

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
