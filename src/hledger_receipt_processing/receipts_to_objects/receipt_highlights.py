"""Thin boxes on the receipt preview around the text behind the question in
focus: the evidence of the AI suggestion, so the user checks it at a glance.

The boxes come from hledger-ai (a ``Highlight``: the photo, four corners in
its pixels, the text read there) through the labeller's AI session, which
calls ``show`` whenever the focus moves to another question. ``toggle``
(Alt+h in the TUI) and ``--no-receipt-highlights`` turn them off.

Rendering a phone photo on a maximised window takes a second or more, so
the photo is rendered once and a copy of that render is kept; the boxes are
not part of the figure but drawn on top of the copy and blitted, which
takes milliseconds. When the window renders itself again (first paint,
resize, toolbar zoom) the copy is refreshed and the boxes put back. Kept
apart from the rest of the labelling on purpose.
"""

import logging
import math
import os
from typing import Any, List, Sequence, Tuple

from matplotlib.patches import Polygon
from typeguard import typechecked

logger = logging.getLogger(__name__)

LINE_COLOUR = "#90ee90"  # light green
LINE_WIDTH = 1.2
# A box is grown by this share of its height on every side, so the line
# surrounds the text instead of touching it.
PADDING = 0.25

Point = Tuple[float, float]


@typechecked
def padded_box(
    *, box: Sequence[Point], padding: float = PADDING
) -> List[Point]:
    """The four corners of *box* (clockwise from the top left) moved
    outwards by *padding* of the box height, along the box's own edges."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = [
        (float(x), float(y)) for x, y in box
    ]
    top = math.hypot(x1 - x0, y1 - y0) or 1.0
    left = math.hypot(x3 - x0, y3 - y0) or 1.0
    right = math.hypot(x2 - x1, y2 - y1)
    pad = padding * (left + right) / 2.0
    across = ((x1 - x0) / top * pad, (y1 - y0) / top * pad)
    down = ((x3 - x0) / left * pad, (y3 - y0) / left * pad)
    return [
        (x0 - across[0] - down[0], y0 - across[1] - down[1]),
        (x1 + across[0] - down[0], y1 + across[1] - down[1]),
        (x2 + across[0] + down[0], y2 + across[1] + down[1]),
        (x3 - across[0] + down[0], y3 - across[1] + down[1]),
    ]


class ReceiptHighlighter:
    """Draws the boxes on the preview of one photo (a matplotlib figure)."""

    @typechecked
    def __init__(
        self, *, figure: Any, axes: Any, image_path: str, enabled: bool = True
    ) -> None:
        self.figure = figure
        self.axes = axes
        self._image_path = os.path.abspath(image_path)
        self._enabled = enabled
        self._shown: List[Any] = []  # the highlights given last
        self._patches: List[Polygon] = []
        self._background: Any = None  # the rendered photo, without boxes
        self._draw_cid: Any = figure.canvas.mpl_connect(
            "draw_event", self._rendered
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def patches(self) -> List[Polygon]:
        """The boxes on the photo now (drawn on top of it, not part of the
        figure)."""
        return list(self._patches)

    @typechecked
    def show(self, *, highlights: Sequence[Any]) -> None:
        """Box *highlights* (those on this photo) instead of the previous
        ones; none clears the photo."""
        self._shown = list(highlights)
        self._update()

    @typechecked
    def toggle(self) -> bool:
        """Turn the boxes off, or back on; returns whether they are on."""
        self._enabled = not self._enabled
        self._update()
        return self._enabled

    def detach(self) -> None:
        """Stop drawing on the figure. The preview window outlives the
        photo (the next receipt gets its own highlighter), so this one's
        boxes must not come back when the window renders itself again."""
        self._shown = []
        self._patches = []
        if self._draw_cid is not None:
            self.figure.canvas.mpl_disconnect(self._draw_cid)
            self._draw_cid = None

    def _update(self) -> None:
        self._patches = []
        if self._enabled:
            for highlight in self._shown:
                if os.path.abspath(highlight.image_path) != self._image_path:
                    continue
                patch = Polygon(
                    padded_box(box=highlight.box),
                    closed=True,
                    fill=False,
                    edgecolor=LINE_COLOUR,
                    linewidth=LINE_WIDTH,
                )
                patch.set_figure(self.figure)
                patch.axes = self.axes
                patch.set_transform(self.axes.transData)
                self._patches.append(patch)
        self._blit()

    def _rendered(self, _event: Any) -> None:
        """The figure rendered itself (first paint, resize, zoom): keep a
        copy without the boxes and put the boxes back on top."""
        try:
            self._background = self.figure.canvas.copy_from_bbox(
                self.figure.bbox
            )
            self._draw_boxes()
        except Exception:  # matplotlib would print it on the terminal
            logger.exception("Receipt highlight boxes not drawn")

    def _draw_boxes(self) -> None:
        for patch in self._patches:
            self.axes.draw_artist(patch)

    def _blit(self) -> None:
        """Have the window show the boxes now (the TUI, not matplotlib,
        owns the event loop while labelling)."""
        canvas = self.figure.canvas
        try:
            if self._background is None:
                # Not rendered yet (normally the preview was painted while
                # the user read "Can you see"): render once, which also
                # keeps the copy and draws the boxes (_rendered).
                canvas.draw()
            else:
                canvas.restore_region(self._background)
                self._draw_boxes()
            canvas.blit(self.figure.bbox)
            canvas.flush_events()
        except Exception:  # the user may have closed the window
            logger.debug("Receipt preview not updated", exc_info=True)
