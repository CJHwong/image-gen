from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.qwen21_turbo.capabilities import qwen21_turbo_capabilities

CHECKPOINT_FILES = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "processor/preprocessor_config.json",
    "processor/tokenizer.json",
    "vae/config.json",
    "transformer/config.json",
    "text_encoder/config.json",
)
WEIGHT_DIRECTORIES = ("vae", "transformer", "text_encoder")


class OfficialQwenTurboBackendGateway(ImageBackendGateway):
    def __init__(self, generator, edit, badge: str, model_dir: str):
        self._generator = generator
        self._edit = edit
        self._badge = badge
        self._model_dir = Path(model_dir).expanduser()

    def capabilities(self):
        return qwen21_turbo_capabilities(self._badge)

    def load(self) -> None:
        missing = missing_checkpoint_files(self._model_dir)
        if missing:
            paths = ", ".join(missing)
            raise StudioError(
                f"The official Qwen Turbo local checkpoint is missing or incomplete at {self._model_dir}: {paths}. "
                "Set model_dir under [qwen21_turbo]. This backend does not download weights."
            )
        self._generator.load()

    def run(self, job: ImageJob, on_step, should_stop):
        if job.mode == "edit":
            self._generator.release()
            return self._edit.run(job, on_step, should_stop)
        self._edit.release()
        return self._generator.run(job, on_step, should_stop)

    def release(self) -> None:
        self._generator.release()
        self._edit.release()


def missing_checkpoint_files(model_dir: Path) -> list[str]:
    if not model_dir.is_dir():
        return ["checkpoint directory"]
    missing = [relative for relative in CHECKPOINT_FILES if not (model_dir / relative).is_file()]
    missing.extend(
        f"{directory}/*.safetensors"
        for directory in WEIGHT_DIRECTORIES
        if not any((model_dir / directory).glob("*.safetensors"))
    )
    return missing
