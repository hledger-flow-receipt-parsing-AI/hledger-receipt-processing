"""Interactive receipt grouping: one reused window, pairs from the start.

Key presses are scripted through ``plt.pause`` (the loop's wait), so the
tests run headless on the Agg backend.
"""

import json
from pathlib import Path
from typing import List

import pytest
from matplotlib import pyplot as plt
from matplotlib.backend_bases import KeyEvent
from PIL import Image

from hledger_receipt_processing.receipts_to_objects import group_images
from hledger_receipt_processing.receipts_to_objects.edit_images import (
    gui_environment,
)

from test_receipt_not_mine import _config


@pytest.fixture
def config(tmp_path: Path):
    return _config(tmp_path)


@pytest.fixture(autouse=True)
def headless(monkeypatch):
    backend = plt.get_backend()
    plt.switch_backend("agg")
    monkeypatch.setattr(
        gui_environment, "assert_grouping_environment", lambda: None
    )
    monkeypatch.setattr(plt, "show", lambda **kwargs: None)
    yield
    plt.close("all")
    plt.switch_backend(backend)


def _images(config, names: List[str]) -> List[str]:
    """Distinct (so never hash-grouped) images in the input folder."""
    folder = Path(
        config.dir_paths.get_path("receipt_images_input_dir", absolute=True)
    )
    paths = []
    for i, name in enumerate(names):
        path = folder / f"{name}.jpg"
        Image.new("RGB", (8, 8), (i * 40, 0, 0)).save(path)
        paths.append(str(path))
    return paths


def _press(monkeypatch, keys: List[str]) -> List[dict]:
    """Answer each question with the next key; record what was shown."""
    keys = list(keys)
    questions: List[dict] = []

    def pause(_interval: float) -> None:
        fig = plt.gcf()
        questions.append(
            {
                "figures": plt.get_fignums(),
                "titles": [ax.get_title() for ax in fig.axes],
            }
        )
        key = keys.pop(0)
        if key == "ctrl-c":
            raise KeyboardInterrupt
        fig.canvas.callbacks.process(
            "key_press_event", KeyEvent("key_press_event", fig.canvas, key)
        )

    monkeypatch.setattr(plt, "pause", pause)
    return questions


def test_first_question_compares_first_two_images(config, monkeypatch):
    a, b, c, d = _images(config, ["a", "b", "c", "d"])
    questions = _press(monkeypatch, ["n", "g", "x"])

    groups = group_images.interactive_group_images(
        config=config, image_paths=[a, b, c, d]
    )

    assert groups == [[a], [b, c]]
    first = questions[0]["titles"]
    assert len(first) == 2
    assert "a.jpg" in first[0] and "b.jpg" in first[1]
    # Every question is asked in the same, single window.
    assert {tuple(q["figures"]) for q in questions} == {
        tuple(questions[0]["figures"])
    }
    assert len(questions[0]["figures"]) == 1
    assert plt.get_fignums() == []


def test_prime_and_group_makes_right_image_the_prime(config, monkeypatch):
    a, b = _images(config, ["a", "b"])
    _press(monkeypatch, ["p"])

    assert group_images.interactive_group_images(
        config=config, image_paths=[a, b]
    ) == [[b, a]]


def test_single_image_is_its_own_receipt_without_a_window(
    config, monkeypatch
):
    (a,) = _images(config, ["a"])
    questions = _press(monkeypatch, [])

    assert group_images.interactive_group_images(
        config=config, image_paths=[a]
    ) == [[a]]
    assert questions == []


def _save_existing(config, names: List[List[str]]) -> List[List[str]]:
    groups = [_images(config, group) for group in names]
    group_images.save_image_grouping(config=config, groups=groups)
    return groups


def test_quitting_at_once_does_not_duplicate_saved_groups(
    config, monkeypatch
):
    existing = _save_existing(config, [["old1"], ["old2", "old3"]])
    new = _images(config, ["a", "b"])
    _press(monkeypatch, ["q"])

    # What the callers do: saved groups + the newly grouped images.
    saved = group_images.load_image_grouping(config=config)
    merged = saved + group_images.group_receipt_images(
        config=config, image_paths=new
    )

    assert merged == existing + [[new[0]]]


def test_interrupted_grouping_keeps_saved_groups_on_disk(config, monkeypatch):
    existing = _save_existing(config, [["old1"], ["old2", "old3"]])
    a, b, c = _images(config, ["a", "b", "c"])
    _press(monkeypatch, ["n", "ctrl-c"])

    with pytest.raises(KeyboardInterrupt):
        group_images.group_receipt_images(config=config, image_paths=[a, b, c])

    assert group_images.load_image_grouping(config=config) == existing + [
        [a],
        [b],
    ]


def test_load_keeps_each_image_in_its_first_group_only(config):
    a, b, c = _images(config, ["a", "b", "c"])
    doubled = [[a, b], [c], [a, b], [c]]
    Path(group_images._grouping_filepath(config=config)).write_text(
        json.dumps(doubled)
    )

    assert group_images.load_image_grouping(config=config) == [[a, b], [c]]
