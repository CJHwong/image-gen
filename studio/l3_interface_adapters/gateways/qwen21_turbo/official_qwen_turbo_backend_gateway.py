import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from safetensors import safe_open

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.qwen21_turbo.capabilities import qwen21_turbo_capabilities

CHECKPOINT_FILES = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "processor/processor_config.json",
    "processor/tokenizer.json",
    "vae/config.json",
    "transformer/config.json",
    "text_encoder/config.json",
    "text_encoder/model.safetensors",
)
WEIGHT_DIRECTORIES = ("vae", "transformer")
MODEL_REPOSITORY = "Qwen/Qwen-Image-2.1-Turbo"


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
            download_official_checkpoint(self._model_dir)
            missing = missing_checkpoint_files(self._model_dir)
            if missing:
                paths = ", ".join(missing)
                raise StudioError(f"The official Qwen Turbo download at {self._model_dir} is incomplete: {paths}.")
        ensure_text_encoder_index(self._model_dir)
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


def ensure_text_encoder_index(model_dir: Path) -> None:
    """Give mflux's sharded text loader an index for the official single-file encoder."""
    text_encoder_dir = model_dir / "text_encoder"
    index_path = text_encoder_dir / "model.safetensors.index.json"
    weights_path = text_encoder_dir / "model.safetensors"
    with safe_open(weights_path, framework="np", device="cpu") as safetensors_file:
        weight_map = dict.fromkeys(safetensors_file.keys(), weights_path.name)
    if not weight_map:
        raise StudioError(f"The official Qwen Turbo text encoder has no weights at {weights_path}.")
    if text_encoder_index_matches(index_path, weight_map):
        return
    write_text_encoder_index(index_path, weight_map)


def text_encoder_index_matches(index_path: Path, expected_weight_map: dict[str, str]) -> bool:
    if index_path.is_symlink() or not index_path.is_file():
        return False
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(index, dict):
        return False
    return index.get("weight_map") == expected_weight_map


def write_text_encoder_index(index_path: Path, weight_map: dict[str, str]) -> None:
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=index_path.parent,
        prefix=f".{index_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as staged_index:
        staged_index.write(json.dumps({"weight_map": weight_map}))
        staged_path = Path(staged_index.name)
    try:
        staged_path.replace(index_path)
    finally:
        staged_path.unlink(missing_ok=True)


def download_official_checkpoint(model_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=MODEL_REPOSITORY, local_dir=str(model_dir))
    except Exception as error:
        raise StudioError(f"Could not download official Qwen Turbo from {MODEL_REPOSITORY}: {error}") from error
