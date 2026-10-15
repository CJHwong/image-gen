from studio.l1_entities.video_job import VideoJob
from studio.l3_interface_adapters.gateways.stub_video_backend_gateway import StubVideoBackendGateway


def test_stub_video_gateway_returns_metadata_without_fake_video_bytes():
    job = VideoJob("moving clouds", 960, 544, 145, 24, 7)

    result = StubVideoBackendGateway().run(job)

    assert result.mp4 is None
    assert result.stub is True
    assert (result.width, result.height, result.num_frames, result.seed) == (960, 544, 145, 7)
