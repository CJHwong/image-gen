from studio.l1_entities.video_job import VideoJob, VideoReference, VideoResult


def test_video_job_keeps_prompt_settings_and_keyframes():
    reference = VideoReference(name="frame.png", png=b"png", frame_index=24, strength=0.8)
    job = VideoJob(
        prompt="A kite rises above the beach",
        width=960,
        height=544,
        num_frames=145,
        frame_rate=24,
        seed=42,
        references=(reference,),
    )

    assert job.references == (reference,)
    assert (job.width, job.height, job.num_frames, job.frame_rate, job.seed) == (960, 544, 145, 24, 42)


def test_video_result_can_hold_an_mp4_or_a_stub_record():
    result = VideoResult(mp4=None, width=768, height=768, num_frames=145, frame_rate=24, seed=None, stub=True)

    assert result.mp4 is None and result.stub is True
