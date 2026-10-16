"""A backend that makes no image, for testing the core without a model."""

from studio.l1_entities.capabilities import Capabilities, ModeSpec, ParamSpec
from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageResult
from studio.l1_entities.video_capabilities import VideoCapabilities, VideoShape
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway

STEPS = ParamSpec(id="steps", kind="number", default=3, minimum=1, maximum=50, integer=True)
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0)


def fake_capabilities(backend_id="fake", name="Fake", description=""):
    return Capabilities(
        backend_id=backend_id,
        name=name,
        badge="bf16",
        max_batch=4,
        description=description,
        modes=(
            ModeSpec(id="generate", label="Generate", params=(STEPS, GUIDANCE), max_references=1),
            ModeSpec(
                id="edit",
                label="Edit",
                params=(STEPS,),
                min_references=1,
                max_references=10,
                prompt_required="An edit instruction is required.",
                each_reference=True,
            ),
        ),
    )


class FakeBackendGateway(ImageBackendGateway):
    def __init__(self, backend_id="fake", name="Fake", fail_with=None, stop_check=None, description=""):
        self.caps = fake_capabilities(backend_id, name, description)
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


class FakeModelResidencyGateway(ModelResidencyGateway):
    def __init__(self):
        self.current: str | None = None
        self.events: list[str] = []

    def activate(self, backend_id: str) -> None:
        if self.current != backend_id:
            if self.current is not None:
                self.events.append("release " + self.current)
            self.current = backend_id
        self.events.append("activate " + backend_id)

    def release(self) -> None:
        if self.current is None:
            return
        self.events.append("release " + self.current)
        self.current = None


def fake_video_capabilities(backend_id="video-fake", name="Fake video"):
    return VideoCapabilities(
        backend_id=backend_id,
        name=name,
        badge="24 fps",
        description="A fake video model.",
        shapes=(VideoShape("16:9", 960, 544), VideoShape("1:1", 768, 768)),
        default_shape_ratio="16:9",
        min_frames=9,
        max_frames=361,
        frame_step=8,
        duration_presets=(121, 241, 361),
        default_frames=121,
        frame_rate=24,
        max_references=8,
        min_reference_strength=0.05,
        max_reference_strength=1.0,
        reference_strength_step=0.05,
        default_reference_strength=1.0,
        min_seed=0,
        max_seed=2**32 - 1,
        min_dimension=256,
        max_dimension=1280,
        dimension_step=32,
    )


class FakeVideoBackendGateway(VideoBackendGateway):
    def __init__(self, backend_id="video-fake", name="Fake video", failure=None, capabilities=None):
        self._capabilities = capabilities or fake_video_capabilities(backend_id, name)
        self.failure = failure
        self.jobs: list[VideoJob] = []
        self.releases = 0

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

    def run(self, job: VideoJob, progress=None, cancelled=None) -> VideoResult:
        self.jobs.append(job)
        if self.failure:
            raise self.failure
        if progress:
            progress(4, 8, 1)
        return VideoResult(b"mp4", job.width, job.height, job.num_frames, job.frame_rate, job.seed)

    def release(self) -> None:
        self.releases += 1
