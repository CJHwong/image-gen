"""Fetch an effect's weights from Lightricks, when the studio is allowed to.

The seven LTX-2.5 effects live in one collection of small gated repos, about 5.9 GB for
all of them. A person who installed the studio does not have them, and a run that stops on
a missing file is a dead end for a first-time user.

The fetch is opt-in, because a download is a side effect the person did not ask for: the
setting `fetch_loras` says whether a missing adapter is fetched or refused. It names the
repo, so the file that arrives is the one the card names.
"""

from pathlib import Path

from studio.l1_entities.errors import StudioError

# The collection each adapter's card lives in. The repo id is the card's name, and the
# file inside it carries the same name.
REPO_PREFIX = "Lightricks/LTX-2.5-22b-IC-LoRA-"
CARD_NAMES = {
    "day-to-night": "Day-To-Night",
    "water-simulation": "Water-Simulation",
    "clean-plate": "Clean-Plate",
    "deblur": "Deblur",
    "decompression": "Decompression",
    "restore": "Restore",
    "upscale-2x": "Pixel-Spatial-Upscaler",
}


def fetch_lora(adapter_id: str, file_name: str, target_dir: Path) -> Path:
    """Put the adapter's weights in the target directory, and return the path.

    A file that is already there is not fetched again. An effect the studio does not know
    is refused, because a fetch from an unnamed place is not a thing to do on a disk.
    """
    card = CARD_NAMES.get(adapter_id)
    if card is None:
        raise StudioError(f"There is no Lightricks collection for the {adapter_id} effect.")
    target = target_dir / file_name
    if target.is_file() and target.stat().st_size > 0:
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    repo = f"{REPO_PREFIX}{card}"
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise StudioError("huggingface-hub is not installed, so the effect weights cannot be fetched.") from None
    try:
        fetched = hf_hub_download(repo_id=repo, filename=file_name, local_dir=target_dir)
    except Exception as error:
        raise StudioError(
            f"Could not fetch {file_name} from {repo}. Accept that collection's terms on "
            f"Hugging Face, run `uv run hf auth login` once, then try again. "
            f"The library said: {error}"
        ) from error
    return Path(fetched)
