"""The receipt preview window keeps its place from receipt to receipt.

Each receipt used to get a fresh matplotlib window that was closed after
its questionnaire, so the next receipt opened wherever the window manager
put it, at the default size, and the user had to snap it next to the
terminal again for every receipt. One preview window now stays open for
the whole labelling run; only the photo in it changes.

These tests drive the real labelling loop with a real TkAgg window in an
Xvfb display (in a subprocess, like test_receipt_window.py of the
preprocessor). The questionnaire is replaced by "This receipt is not mine",
which takes the same way out of make_receipt_label as a finished label.
Nothing is displayed on the user's screen; the data is invented.
"""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict

import pytest

TEST_DIR = Path(__file__).resolve().parent

ENV = {
    **{
        k: v
        for k, v in os.environ.items()
        if k not in ("WAYLAND_DISPLAY", "HLEDGER_PREPROCESSOR_HEADLESS")
    },
    "MPLBACKEND": "TkAgg",
}

pytestmark = pytest.mark.skipif(
    shutil.which("xvfb-run") is None, reason="needs xvfb-run"
)

# "The user" snaps the preview next to the terminal.
SNAPPED = "700x900+500+150"

DRIVER_PREAMBLE = textwrap.dedent(f"""
    import json, sys
    sys.path.insert(0, {str(TEST_DIR)!r})
    import hledger_preprocessor  # noqa: F401  resolves the import cycle
    from pathlib import Path
    from PIL import Image
    from matplotlib import pyplot as plt
    from test_receipt_not_mine import _config
    from hledger_receipt_processing.receipts_to_objects import (
        make_receipt_labels,
    )
    from hledger_receipt_processing.receipts_to_objects import (
        receipt_not_mine,
    )

    ReceiptNotMine = receipt_not_mine.ReceiptNotMine

    SNAPPED = {SNAPPED!r}
    tmp = Path(sys.argv[1])
    config = _config(tmp)
    root = Path(config.dir_paths.root_finance_path)

    def make_receipt(stem, size):
        original = root / "receipt_images_input" / f"{{stem}}.jpg"
        Image.new("RGB", size, "white").save(original)
        processed = root / "receipt_images_processed"
        Image.new("RGB", size, "white").save(
            processed / f"{{stem}}_cropped.jpg"
        )
        return str(original)

    # A portrait and a landscape photo: the second must really be shown.
    receipts = [make_receipt("photo_a", (300, 500)),
                make_receipt("photo_b", (500, 300))]

    def window():
        return plt.gcf().canvas.manager.window

    def preview():
        \"\"\"The preview window as the user sees it now; None if closed.\"\"\"
        from matplotlib._pylab_helpers import Gcf

        shown = [
            manager.canvas.figure
            for manager in Gcf.get_all_fig_managers()
            if manager.canvas.figure.axes
            and manager.canvas.figure.axes[0].images
        ]
        if not shown:
            return None
        figure = shown[-1]
        w = figure.canvas.manager.window
        w.update()  # apply pending moves/resizes before measuring
        axes = figure.axes[0]
        return {{
            "id": w.winfo_id(),
            "geometry": w.geometry(),
            "image": list(axes.images[0].get_array().shape),
            "draw_callbacks": len(
                figure.canvas.callbacks.callbacks.get("draw_event", {{}})
            ),
            "figures": len(shown),
        }}

    result = {{"seen": [], "open_after": None}}

    def fake_input(prompt=""):
        assert "Can you see" in prompt, prompt
        at_prompt(len(result["seen"]))
        result["seen"].append(preview())
        return ""

    def not_mine(**_kwargs):
        raise ReceiptNotMine(partial_answers={{}})

    make_receipt_labels.input = fake_input
    make_receipt_labels.ask_questions = not_mine
    """)

DRIVER_EPILOGUE = textwrap.dedent("""
    result["open_after"] = bool(plt.get_fignums())
    print("RESULT=" + json.dumps(result))
    """)


def _run_driver(tmp_path: Path, *parts: str) -> Dict[str, Any]:
    script = tmp_path / "driver.py"
    script.write_text(
        DRIVER_PREAMBLE
        + "".join(textwrap.dedent(part) for part in parts)
        + DRIVER_EPILOGUE
    )
    out = subprocess.run(
        [
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1920x1080x24",
            sys.executable,
            str(script),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=ENV,
        timeout=240,
    )
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("RESULT=")]
    assert lines, f"driver failed:\n{out.stdout[-3000:]}\n{out.stderr[-3000:]}"
    return json.loads(lines[-1][len("RESULT=") :])


def _label_all() -> str:
    return """
    make_receipt_labels.manually_make_receipt_labels(
        config=config,
        image_groups=[[path] for path in receipts],
        labelled_receipts=[],
        verbose=False,
    )
    """


def test_window_keeps_user_geometry_across_receipts(tmp_path: Path) -> None:
    """The window the user snapped shows the next receipt, where it is."""
    result = _run_driver(
        tmp_path,
        """
        def at_prompt(n):
            if n == 0:
                window().geometry(SNAPPED)
        """,
        _label_all(),
    )
    first, second = result["seen"]
    assert first["geometry"] == SNAPPED
    assert second["id"] == first["id"]
    assert second["geometry"] == SNAPPED
    assert second["image"] != first["image"]  # the next photo is shown
    assert second["figures"] == 1
    # The highlighter of the first receipt no longer listens to the window.
    assert second["draw_callbacks"] == first["draw_callbacks"]
    assert result["open_after"] is False


def test_closed_window_comes_back_where_it_was(tmp_path: Path) -> None:
    """A window the user closed reopens at its last place and size."""
    result = _run_driver(
        tmp_path,
        """
        def at_prompt(n):
            if n == 0:
                w = window()
                w.geometry(SNAPPED)
                w.update()
                w.tk.call(w.protocol("WM_DELETE_WINDOW"))  # the user closes it
                w.update()
        """,
        _label_all(),
    )
    first, second = result["seen"]
    assert first is None
    assert second["geometry"] == SNAPPED
    assert second["figures"] == 1
    assert result["open_after"] is False


def test_single_receipt_closes_its_window(tmp_path: Path) -> None:
    """Editing one receipt (no labelling loop) still cleans up after itself."""
    result = _run_driver(
        tmp_path,
        """
        def at_prompt(n):
            pass

        try:
            make_receipt_labels.make_receipt_label(
                config=config,
                raw_receipt_img_filepaths=[receipts[0]],
                cropped_receipt_img_filepath=str(
                    root / "receipt_images_processed" / "photo_a_cropped.jpg"
                ),
                hledger_account_infos=set(),
                receipt_nr=0,
                total_nr_of_receipts=1,
                labelled_receipts=[],
            )
        except ReceiptNotMine:
            pass
        """,
    )
    assert len(result["seen"]) == 1
    assert result["seen"][0]["figures"] == 1
    assert result["open_after"] is False


def test_closed_window_is_not_mistaken_for_a_new_figure(
    tmp_path: Path,
) -> None:
    """Once the user closed the preview, another figure may get its number
    again; the next receipt must still get a window of its own."""
    result = _run_driver(
        tmp_path,
        """
        others = []

        def at_prompt(n):
            if n == 0:
                w = window()
                w.geometry(SNAPPED)
                w.update()
                w.tk.call(w.protocol("WM_DELETE_WINDOW"))  # the user closes it
                w.update()
                others.append(plt.figure())  # reuses the number
        """,
        _label_all(),
    )
    first, second = result["seen"]
    assert second is not None
    assert second["geometry"] == SNAPPED
    assert second["image"] == [300, 500, 3]  # the landscape photo
