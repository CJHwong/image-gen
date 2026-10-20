from collections.abc import Callable
from dataclasses import replace

from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.mlx_video.capabilities import ltx25_mlx_capabilities


class StubVideoBackendGateway(VideoBackendGateway):
    """Return output metadata without an encoded file or a model call."""

    def __init__(self, capabilities: VideoCapabilities):
        self._capabilities = capabilities

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        return VideoResult(
            mp4=None,
            width=job.width,
            height=job.height,
            num_frames=job.num_frames,
            frame_rate=job.frame_rate,
            seed=job.seed,
            stub=True,
        )

    def release(self) -> None:
        pass


def editing_video_capabilities() -> VideoCapabilities:
    """A stub model that offers Edit, so the suite can drive that form.

    No real video pack offers Edit today: 2.5 has no task IC-LoRAs and 2.3's are control
    models. The form, the adapter menu and the clip post still exist, so the suite keeps
    them covered here rather than losing the checks with the PyTorch engine.
    """
    base = ltx25_mlx_capabilities()
    return replace(
        base,
        backend_id="video_edit_stub",
        name="LTX-2.5",
        modes=(
            base.modes[0],
            VideoMode(
                "edit",
                "Edit",
                needs_clip=True,
                prompt_label="What to change",
                placeholder="Pick an effect, then describe the change.",
                run_label="Edit clip",
            ),
        ),
        adapters=(
            VideoAdapter(
                id="day-to-night",
                label="Day to night",
                hint="Relight a daylight clip as the same shot at night",
                mode="edit",
                file="stub.safetensors",
                prompt=(
                    "A realistic nighttime scene of the same place: deep blue moonlight, warm "
                    "street lamps and lit shop windows, deep natural shadows. Only the lighting "
                    "changes from day to night; identical composition, framing, camera movement "
                    "and motion."
                ),
                strength=1.0,
                stage_2_conditioning=True,
            ),
        ),
    )
