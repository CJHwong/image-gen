"""The page's form, turned into use case calls."""

import base64
import binascii
import io
import json
from collections.abc import Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase, StudioView
from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l2_use_cases.run_image_use_case import RunImageRequest, RunImageResponse, RunImageUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase


class FormController:
    def __init__(
        self,
        describe: DescribeStudioUseCase,
        run: RunImageUseCase,
        read_progress: ReadProgressUseCase,
        cancel: CancelRunUseCase,
        switch: SwitchBackendUseCase,
    ):
        self._describe = describe
        self._run = run
        self._read_progress = read_progress
        self._cancel = cancel
        self._switch = switch

    def page(self) -> StudioView:
        return self._describe.execute()

    def run(self, form: Mapping[str, str]) -> RunImageResponse:
        return self._run.execute(run_request(form))

    def progress(self) -> RunProgress:
        return self._read_progress.execute()

    def cancel(self) -> None:
        self._cancel.execute()

    def switch(self, form: Mapping[str, str]) -> None:
        self._switch.execute(form.get("backend", ""))


def run_request(form: Mapping[str, str]) -> RunImageRequest:
    """The first request of a batch carries the images as base64 in a JSON array,
    and `count`. Every later one carries `total`, `index` and the token instead."""
    return RunImageRequest(
        mode=form.get("mode") or "generate",
        prompt=form.get("prompt", ""),
        seed=form.get("seed", ""),
        options=form,
        references=_references(form.get("references") or "[]"),
        reference_token=form.get("reference_token", "").strip(),
        total=_whole(form.get("total") or form.get("count") or "1", "count"),
        index=_whole(form.get("index") or "1", "index"),
        backend=form.get("backend", "").strip(),
    )


def _whole(text: str, name: str) -> int:
    if not text.strip().isdigit():
        raise InvalidJob(f"{name} must be a whole number")
    return int(text)


def _references(raw: str) -> tuple[ReferenceImage, ...]:
    try:
        blobs = json.loads(raw)
    except json.JSONDecodeError:
        raise InvalidJob("references must be a JSON array") from None
    return tuple(_reference(blob) for blob in blobs)


def _reference(blob: str) -> ReferenceImage:
    """Any image the browser sends becomes an upright RGB or RGBA PNG here, so every
    engine gets one kind. A phone photo stores its turn in EXIF, and the sizes the
    page offers follow the reference, so the turn is applied first. Every image is
    encoded again, which also drops the text a PNG can carry, such as a prompt."""
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(blob))))
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as error:
        raise UnreadableImage(f"Could not read that reference image: {error}") from None
    return ReferenceImage(png=buffer.getvalue(), width=image.width, height=image.height)
