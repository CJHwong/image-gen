"""One backend, two engines that cannot share the memory of this machine."""

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from tests.support.images import png


def job(mode="generate", references=(), **options):
    defaults = {
        "generate": {"size": "1024x1024", "steps": 8, "guidance": 1.0, "strength": 0.4, "negative": ""},
        "edit": {"resolution": "match", "steps": 8, "cfg": 1.0, "negative": ""},
    }[mode]
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


class Recorder:
    def __init__(self, name, log):
        self.name, self.log = name, log

    def run(self, the_job, on_step, should_stop):
        self.log.append(f"{self.name} run")
        return ImageResult(png=b"", width=1, height=1, seed=the_job.seed, steps=1)

    def release(self):
        self.log.append(f"{self.name} release")

    def load(self):
        self.log.append(f"{self.name} load")


def test_only_one_engine_holds_memory_at_a_time():
    log = []
    backend = Qwen21BackendGateway(Recorder("mflux", log), Recorder("edit", log), badge="bf16")
    backend.run(job("edit", references=(png(8, 8),)), None, None)
    backend.run(job(), None, None)
    assert log == ["mflux release", "edit run", "edit release", "mflux run"]


def test_load_starts_the_generate_engine_only():
    """The edit engine needs 38.7 GiB on MPS against mflux's 30.7 GB peak, so a load
    starts one of them and the first run of the other one frees it."""
    log = []
    backend = Qwen21BackendGateway(Recorder("mflux", log), Recorder("edit", log), badge="bf16")
    backend.load()
    assert log == ["mflux load"]


def test_release_frees_both_engines():
    log = []
    backend = Qwen21BackendGateway(Recorder("mflux", log), Recorder("edit", log), badge="bf16")
    backend.release()
    assert log == ["mflux release", "edit release"]


def test_the_precision_badge_the_backend_loaded_reaches_the_page():
    caps = Qwen21BackendGateway(None, None, badge="int8").capabilities()
    assert (caps.backend_id, caps.name, caps.badge) == ("qwen21", "Qwen-Image-2.1", "int8")
