"""Public Video plugin types; outputs cross the boundary as MP4 bytes."""

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode, VideoShape
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoReference, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway

__all__ = [
    "Cancelled",
    "InvalidJob",
    "VideoAdapter",
    "VideoAudio",
    "VideoBackendGateway",
    "VideoCapabilities",
    "VideoEdit",
    "VideoJob",
    "VideoMode",
    "VideoReference",
    "VideoResult",
    "VideoShape",
]
