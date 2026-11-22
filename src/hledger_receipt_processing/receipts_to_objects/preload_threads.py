"""Start the labeller's background preload threads safely next to Tk.

Closed matplotlib (TkAgg) windows, such as those of the grouping step,
leave Tk objects behind as garbage. If the garbage collector frees them
inside a background thread, every one of them fails with "main thread is
not in main loop", and Tk can even abort the process with
"Tcl_AsyncDelete: async handler deleted by the wrong thread". Collecting
that garbage on the main thread before starting the threads avoids both.
"""

import gc
import threading
from typing import Callable, List

from typeguard import typechecked


@typechecked
def start_preload_threads(
    *targets: Callable[[], None],
) -> List[threading.Thread]:
    """Free GUI garbage on this (main) thread, then start daemon threads."""
    gc.collect()
    threads = [
        threading.Thread(target=target, daemon=True) for target in targets
    ]
    for thread in threads:
        thread.start()
    return threads
