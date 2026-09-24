"""A backend that makes no image, for testing the core without a model."""

from studio.l1_entities.capabilities import Capabilities, ModeSpec, ParamSpec
from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway

STEPS = ParamSpec(id="steps", kind="number", default=3, minimum=1, maximum=50, integer=True)
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0)


def fake_capabilities(backend_id="fake", name="Fake"):
    return Capabilities(
        backend_id=backend_id,
        name=name,
        badge="bf16",
        max_batch=4,
        modes=(
            ModeSpec(id="generate", label="Generate", params=(STEPS, GUIDANCE), max_references=1),
            ModeSpec(
                id="edit",
                label="Edit",
                params=(STEPS,),
                min_references=1,
                max_references=10,
                prompt_required="An edit instruction is required.",
            ),
        ),
    )


class FakeBackendGateway(ImageBackendGateway):
    def __init__(self, backend_id="fake", name="Fake", fail_with=None, stop_check=None):
        self.caps = fake_capabilities(backend_id, name)
        self.jobs = []
        self.events = []
        self.fail_with = fail_with
        self.stop_check = stop_check  # called at each step, to act mid-run

    def capabilities(self):
        return self.caps

    def load(self):
        self.events.append("load")

    def run(self, job, on_step, should_stop):
        self.jobs.append(job)
        if self.fail_with:
            raise self.fail_with
        total = job.options["steps"]
        for step in range(1, total + 1):
            if self.stop_check:
                self.stop_check(step)
            if should_stop():
                raise Cancelled(f"stopped at step {step}")
            on_step(step, total)
        return ImageResult(png=b"png", width=8, height=8, seed=job.seed, steps=total)

    def release(self):
        self.events.append("release")
