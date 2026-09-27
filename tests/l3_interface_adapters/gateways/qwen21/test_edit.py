"""The edit half of qwen21: the payload the child receives, and the child's life."""

import base64
from collections.abc import Callable

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.qwen21.edit import Qwen21Edit, edit_payload
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from tests.support.images import png


def job(mode="edit", references=(), **options):
    defaults = {"resolution": "match", "steps": 8, "cfg": 1.0, "negative": ""}
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def test_edit_sends_pngs_and_sizes_from_the_last_reference():
    payload = edit_payload(job(references=(png(32, 32), png(2560, 1440))))
    assert payload["output_resolution"] == 1328  # the cap, not 1920
    assert len(payload["images"]) == 2 and base64.b64decode(payload["images"][0])[:4] == b"\x89PNG"
    assert payload["seed"] == 5 and payload["true_cfg_scale"] == 1.0 and payload["negative_prompt"] is None
    assert edit_payload(job(references=(png(32, 32),), resolution="768"))["output_resolution"] == 768


class FakeChild(StdioChild):
    """A StdioChild stand-in: it records the payload and the two callbacks it was given.

    It keeps StdioChild as its base, so the adapter's own annotation stays honest.
    """

    def __init__(self, reply: dict):
        self.reply = reply
        self.lifecycle: list[str] = []
        self.seen: tuple[dict, Callable[[int, int], None], Callable[[], bool]] | None = None

    def ensure(self) -> None:
        self.lifecycle.append("ensure")

    def stop(self) -> None:
        self.lifecycle.append("stop")

    def request(self, payload: dict, on_step: Callable[[int, int], None], should_stop: Callable[[], bool]) -> dict:
        self.seen = (payload, on_step, should_stop)
        return self.reply


def test_load_starts_the_child_and_release_stops_it():
    """The child stays up between edits: building the pipeline costs 20 to 36 seconds."""
    child = FakeChild({})
    edit = Qwen21Edit(child)
    edit.load()
    edit.release()
    assert child.lifecycle == ["ensure", "stop"]


def test_a_run_answers_with_the_childs_image_and_seed():
    source = png(24, 16)
    reply = {"image": base64.b64encode(source.png).decode("ascii"), "seed": 7}
    child = FakeChild(reply)
    edit = Qwen21Edit(child)
    the_job = job(references=(source,), steps=12)

    def on_step(step, total):
        pass

    def stop():
        return False

    result = edit.run(the_job, on_step, stop)

    assert child.seen is not None
    payload, passed_on_step, passed_stop = child.seen
    assert payload == edit_payload(the_job)
    assert passed_on_step is on_step and passed_stop is stop
    assert result.png == source.png
    assert (result.width, result.height, result.seed, result.steps) == (24, 16, 7, 12)
