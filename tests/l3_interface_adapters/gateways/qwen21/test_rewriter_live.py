"""The real rewriter: one rewrite left alone, and one stopped while it writes.

Nothing here is mocked. The unit test beside this file stubs mlx-vlm through
`heavy_modules`, and the streaming call this repo now iterates is the one thing
that stub cannot vouch for: the real stream hands over word-sized segments and
the answer parses only when every one of them is joined. This is the test that
tells a break in that apart from a break this repo caused, which is the same gap
`PORTABILITY.md` named for the image engines.

It needs the rewriter's own weights, which are a separate 18.84 GB per mode, so a
machine without them skips rather than fails.
"""

from pathlib import Path

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.qwen21.rewriter import Qwen21Rewriter

CACHE = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen-Image-2.1-PE-T2I/snapshots"


def local_weights() -> bool:
    return CACHE.is_dir() and any(CACHE.iterdir())


@pytest.mark.live
@pytest.mark.skipif(not local_weights(), reason="no local PE-T2I rewriter")
def test_live_one_rewrite_and_one_stopped_between_segments():
    """Two claims, both about the stream rather than about the wording.

    The first rewrite proves the assembly: the model answers in segments and only
    the joined text is the JSON this repo parses. The second proves the stop: the
    flag is read at the top of the loop, so the answer never reaches the parser and
    the model is left for the caller to free.
    """
    rewriter = Qwen21Rewriter({"generate": "Qwen/Qwen-Image-2.1-PE-T2I"})
    phases: list[str] = []
    typed = "a cat on a table"
    answer = rewriter.rewrite(typed, "generate", (), lambda: phases.append("writing"), lambda: False)

    assert phases == ["writing"]  # once, once the weights are resident
    assert answer.prompt.strip() and answer.prompt != typed
    assert len(answer.prompt) > len(typed)  # a rewriter lengthens

    # The stop lands within one segment. The model writes hundreds of them, so a
    # flag that turns true on the third read is read a third time.
    asked: list[bool] = []

    def stop_after_two():
        asked.append(True)
        return len(asked) > 2

    with pytest.raises(Cancelled):
        rewriter.rewrite(typed, "generate", (), lambda: None, stop_after_two)
    assert len(asked) == 3

    # Freeing is what the page's cancel does with the answer and the memory, and it
    # has to be safe once the loop has stopped, which is where this leaves it.
    rewriter.release()
