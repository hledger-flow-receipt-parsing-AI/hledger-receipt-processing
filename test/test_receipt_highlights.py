"""Thin light-green boxes on the receipt preview around the text behind the
question in focus (the evidence of the AI suggestion).

The boxes come from hledger-ai through the labeller; this draws them on the
matplotlib preview and lets the user turn them off. The photo is rendered
once; the boxes are blitted on top of that, so a box change costs
milliseconds, not a re-render of a multi-megapixel photo. All data is
invented.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

from hledger_receipt_processing.receipts_to_objects import (  # noqa: E402
    make_receipt_labels,
)
from hledger_receipt_processing.receipts_to_objects.receipt_highlights import (  # noqa: E402,E501
    LINE_COLOUR,
    ReceiptHighlighter,
    padded_box,
)

PHOTO = "/finance/proc/a_cropped.jpg"


def _highlight(*, image_path: str = PHOTO, x: float = 10.0) -> SimpleNamespace:
    """What hledger-ai's Highlight looks like here."""
    return SimpleNamespace(
        image_path=image_path,
        box=((x, 20.0), (x + 40.0, 20.0), (x + 40.0, 30.0), (x, 30.0)),
        text="12,34",
    )


class _Preview:
    """A small preview figure, with the renders counted and the rendered
    pixels readable."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.figure = plt.figure(figsize=(2, 2), dpi=100)
        self.axes = self.figure.add_axes([0, 0, 1, 1])
        self.axes.imshow(np.zeros((100, 60, 3), dtype=np.uint8), origin="upper")
        self.axes.axis("off")
        self.renders = 0
        self.figure.canvas.mpl_connect("draw_event", self._rendered)
        self.highlighter = ReceiptHighlighter(
            figure=self.figure,
            axes=self.axes,
            image_path=PHOTO,
            enabled=enabled,
        )

    def _rendered(self, _event: Any) -> None:
        self.renders += 1

    def green_pixels(self) -> int:
        """Clearly green pixels in what the window would show (the thin
        lines are anti-aliased, so their colour varies)."""
        rgba = np.asarray(self.figure.canvas.buffer_rgba()).astype(int)
        r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
        return int(((g > 100) & (g - r > 40) & (g - b > 40)).sum())


def _boxes(highlighter: ReceiptHighlighter) -> List[List[List[float]]]:
    return [patch.get_xy()[:4].tolist() for patch in highlighter.patches]


def test_the_box_is_grown_a_little_so_the_line_surrounds_the_text() -> None:
    box = ((10.0, 20.0), (50.0, 20.0), (50.0, 30.0), (10.0, 30.0))

    assert padded_box(box=box, padding=0.25) == [
        (7.5, 17.5),
        (52.5, 17.5),
        (52.5, 32.5),
        (7.5, 32.5),
    ]


def test_a_tilted_box_grows_along_its_own_edges() -> None:
    # A box standing upright (rotated a quarter turn): its "height" runs
    # along x, so the padding does too.
    box = ((30.0, 10.0), (30.0, 50.0), (20.0, 50.0), (20.0, 10.0))

    assert padded_box(box=box, padding=0.5) == [
        (35.0, 5.0),
        (35.0, 55.0),
        (15.0, 55.0),
        (15.0, 5.0),
    ]


def test_showing_draws_a_thin_light_green_box_per_highlight() -> None:
    preview = _Preview()

    preview.highlighter.show(
        highlights=[_highlight(x=10.0), _highlight(x=100.0)]
    )

    patches = preview.highlighter.patches
    assert len(patches) == 2
    assert _boxes(preview.highlighter)[0] == [
        [7.5, 17.5],
        [52.5, 17.5],
        [52.5, 32.5],
        [7.5, 32.5],
    ]
    assert all(not patch.get_fill() for patch in patches)
    assert all(
        matplotlib.colors.to_hex(patch.get_edgecolor()) == LINE_COLOUR
        for patch in patches
    )
    assert all(patch.get_linewidth() <= 1.5 for patch in patches)
    assert preview.green_pixels() > 100


def test_boxes_are_blitted_the_photo_is_rendered_once() -> None:
    # Re-rendering a photo of several megapixels takes a second or more;
    # that used to happen on every question.
    preview = _Preview()

    for x in (10.0, 100.0, 200.0):
        preview.highlighter.show(highlights=[_highlight(x=x)])

    assert preview.renders == 1
    assert list(preview.axes.patches) == []  # never added to the axes


def test_a_photo_already_rendered_is_not_rendered_again() -> None:
    # The preview is painted while the user reads "Can you see ...".
    preview = _Preview()
    preview.figure.canvas.draw()
    assert preview.renders == 1

    preview.highlighter.show(highlights=[_highlight()])
    preview.highlighter.show(highlights=[_highlight(x=15.0)])

    assert preview.renders == 1
    assert preview.green_pixels() > 100


def test_boxes_come_back_after_the_window_rendered_again() -> None:
    # A resize or a toolbar zoom renders the whole figure (without the
    # boxes, which are not part of it); the boxes are put back on top.
    preview = _Preview()
    preview.highlighter.show(highlights=[_highlight()])

    preview.figure.canvas.draw()

    assert preview.green_pixels() > 100


def test_showing_again_replaces_the_boxes() -> None:
    preview = _Preview()
    preview.highlighter.show(
        highlights=[_highlight(x=10.0), _highlight(x=100.0)]
    )

    preview.highlighter.show(highlights=[_highlight(x=200.0)])

    assert len(preview.highlighter.patches) == 1
    assert _boxes(preview.highlighter)[0][0] == [197.5, 17.5]


def test_showing_nothing_clears_the_photo() -> None:
    preview = _Preview()
    preview.highlighter.show(highlights=[_highlight()])

    preview.highlighter.show(highlights=[])

    assert preview.highlighter.patches == []
    assert preview.green_pixels() == 0


def test_boxes_of_another_photo_are_not_drawn_here() -> None:
    preview = _Preview()

    preview.highlighter.show(
        highlights=[_highlight(image_path="/finance/proc/b_cropped.jpg")]
    )

    assert preview.highlighter.patches == []


def test_the_photo_path_is_compared_as_a_path() -> None:
    preview = _Preview()

    preview.highlighter.show(
        highlights=[
            _highlight(image_path="/finance/proc/../proc/a_cropped.jpg")
        ]
    )

    assert len(preview.highlighter.patches) == 1


def test_toggling_off_clears_and_toggling_on_brings_the_boxes_back() -> None:
    preview = _Preview()
    highlighter = preview.highlighter
    highlighter.show(highlights=[_highlight()])

    assert highlighter.toggle() is False
    assert highlighter.enabled is False
    assert highlighter.patches == []
    assert preview.green_pixels() == 0

    highlighter.show(highlights=[_highlight(x=15.0)])  # while off
    assert highlighter.patches == []

    assert highlighter.toggle() is True
    assert _boxes(highlighter)[0][0] == [12.5, 17.5]
    assert preview.green_pixels() > 100


def test_a_highlighter_started_off_draws_nothing_until_toggled() -> None:
    preview = _Preview(enabled=False)

    preview.highlighter.show(highlights=[_highlight()])

    assert preview.highlighter.patches == []
    assert preview.highlighter.toggle() is True
    assert len(preview.highlighter.patches) == 1


def test_a_closed_window_does_not_stop_the_labelling() -> None:
    preview = _Preview()
    plt.close(preview.figure)

    def broken_flush() -> None:
        raise RuntimeError("window gone")

    preview.figure.canvas.flush_events = broken_flush

    preview.highlighter.show(highlights=[_highlight()])  # must not raise


# ------------------------------------------------- make_receipt_label


class _QuestionsAsked(Exception):
    pass


def test_headless_labelling_passes_no_highlighter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_receipt_not_mine import _config

    config = _config(tmp_path)
    cropped = tmp_path / "receipt_cropped.jpg"
    cropped.write_bytes(b"not shown in headless mode")
    monkeypatch.setenv("HLEDGER_PREPROCESSOR_HEADLESS", "1")
    monkeypatch.setattr("builtins.input", lambda *_args: "")
    asked_with: Dict[str, Any] = {}

    def fake_ask_questions(**kwargs: Any) -> None:
        asked_with.update(kwargs)
        raise _QuestionsAsked

    monkeypatch.setattr(
        make_receipt_labels, "ask_questions", fake_ask_questions
    )

    with pytest.raises(_QuestionsAsked):
        make_receipt_labels.make_receipt_label(
            config=config,
            raw_receipt_img_filepaths=[str(tmp_path / "receipt.jpg")],
            cropped_receipt_img_filepath=str(cropped),
            receipt_nr=0,
            total_nr_of_receipts=1,
            labelled_receipts=[],
        )

    assert asked_with["highlighter"] is None


def test_a_detached_highlighter_leaves_the_window_alone() -> None:
    """The preview window outlives the photo: the next receipt gets its own
    highlighter, and the boxes of the previous one must not come back when
    the window renders itself again (a resize, the next photo)."""
    preview = _Preview()
    preview.highlighter.show(highlights=[_highlight()])
    assert preview.green_pixels() > 0

    preview.highlighter.detach()
    preview.figure.canvas.draw()  # the window rendered itself again

    assert preview.highlighter.patches == []
    assert preview.green_pixels() == 0
    listeners = preview.figure.canvas.callbacks.callbacks["draw_event"]
    assert len(listeners) == 1  # only the test's own render counter is left
