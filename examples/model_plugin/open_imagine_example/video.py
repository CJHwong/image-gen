"""A tiny FFmpeg test clip demonstrates video generation without a trained model."""

import shutil
import tempfile
from pathlib import Path

from studio.plugins import ModelPlugin
from studio.plugins.video import InvalidJob, VideoBackendGateway, VideoCapabilities, VideoResult, VideoShape

CAPABILITIES = VideoCapabilities(
    backend_id="example_video",
    name="Example Video",
    badge="CPU",
    description="Plugin example: an FFmpeg test clip, without a trained model.",
    shapes=(VideoShape("1:1", 256, 256),),
    default_shape_ratio="1:1",
    min_frames=9,
    max_frames=65,
    frame_step=8,
    duration_presets=(17, 33),
    default_frames=17,
    frame_rate=8,
    max_references=0,
    min_reference_strength=0,
    max_reference_strength=1,
    reference_strength_step=0.05,
    default_reference_strength=1,
    min_seed=0,
    max_seed=2147483647,
    min_dimension=256,
    max_dimension=256,
    dimension_step=16,
    precision="CPU",
)


class ExampleVideoGateway(VideoBackendGateway):
    def __init__(self, context):
        self.context = context

    def capabilities(self):
        return CAPABILITIES

    def run(self, job, progress=None, cancelled=None):
        executable = shutil.which("ffmpeg")
        if not executable:
            raise InvalidJob("Install ffmpeg to run the Example Video plugin.")
        with tempfile.TemporaryDirectory(prefix="example-video-") as temporary:
            output = Path(temporary) / "clip.mp4"
            self.context.run_process(
                [
                    executable,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=size={job.width}x{job.height}:rate={job.frame_rate}",
                    "-frames:v",
                    str(job.num_frames),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(output),
                ],
                cancelled=cancelled,
                failure_message=lambda code, lines: f"Example Video failed ({code}): " + "\n".join(lines),
                timeout_seconds=30,
            )
            data = output.read_bytes()
        if progress:
            progress(1, 1, job.seed or 0)
        return VideoResult(data, job.width, job.height, job.num_frames, job.frame_rate, job.seed)

    def release(self):
        pass


plugin = ModelPlugin(CAPABILITIES, ExampleVideoGateway)
