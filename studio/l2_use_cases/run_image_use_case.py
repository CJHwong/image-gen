"""Make one image of a batch.

A batch is a chain of requests, one per image, each carrying what the next one
needs. The server holds no batch state apart from the reference images, so a
page reload ends the batch instead of leaving the server generating into a void.
Batches are sequential because no engine here has batched inference: N images
cost N times one.
"""

import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from studio.l1_entities.capabilities import ModeSpec
from studio.l1_entities.errors import BackendChanged, Cancelled, InvalidJob, MissingPrompt, ReferenceExpired
from studio.l1_entities.image_job import ImageJob, ImageResult, ReferenceImage
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway
from studio.l2_use_cases.boundaries.reference_store_gateway import ReferenceStoreGateway


@dataclass(frozen=True)
class RunImageRequest:
    mode: str
    prompt: str
    seed: str  # blank draws one
    options: Mapping[str, str]  # raw form values, checked against the mode
    references: tuple[ReferenceImage, ...] = field(default=())  # sent with the first image only
    reference_token: str = ""  # what the later images of a batch carry instead
    total: int = 1
    index: int = 1
    backend: str = ""  # the backend the page was built for; blank skips the check


@dataclass(frozen=True)
class NextRun:
    """What the page posts for the next image of the batch: the same job at seed + 1."""

    mode: str
    prompt: str
    seed: int
    options: Mapping[str, str]
    total: int
    index: int
    reference_token: str
    backend: str


@dataclass(frozen=True)
class RunImageResponse:
    image: ImageResult
    mode: str
    prompt: str
    position: str  # "2 of 4", or "1 image"
    elapsed: float  # seconds, loads included
    next_run: NextRun | None


class RunImageUseCase:
    def __init__(
        self,
        catalog: BackendCatalogGateway,
        progress: ProgressGateway,
        references: ReferenceStoreGateway,
        seed_source: Callable[[], int] = lambda: random.randint(0, 1_000_000_000),
        clock: Callable[[], float] = time.time,
        engine_lock: "threading.Lock | None" = None,
    ):
        self._catalog = catalog
        self._progress = progress
        self._references = references
        self._seed_source = seed_source
        self._clock = clock
        # One run at a time: the GPU is saturated by one, and two only slow each other.
        # A switch takes the same lock, so the backend cannot change under a run.
        self._engine_lock = engine_lock or threading.Lock()

    def execute(self, request: RunImageRequest) -> RunImageResponse:
        started = self._clock()
        with self._engine_lock:
            return self._execute(request, started)

    def _execute(self, request: RunImageRequest, started: float) -> RunImageResponse:
        backend_id = self._catalog.active_id()
        if request.backend and request.backend != backend_id:
            raise BackendChanged("The model changed in another tab. Reload the page.")
        backend = self._catalog.get(backend_id)
        capabilities = backend.capabilities()
        mode = capabilities.mode(request.mode)
        if not 1 <= request.total <= capabilities.max_batch:
            raise InvalidJob(f"count must be between 1 and {capabilities.max_batch}")
        images, token = self._load_references(request, mode)
        job = ImageJob(
            mode=mode.id,
            prompt=request.prompt.strip(),
            seed=self._seed(request.seed),
            options=mode.parse_options(request.options),
            references=images,
        )
        if request.index == 1:
            self._progress.clear_cancel()  # a fresh batch, so a stale cancel goes
        if not job.prompt:
            raise MissingPrompt(mode.prompt_required)
        label = f"{request.index} of {request.total}" if request.total > 1 else ""
        try:
            image = self._run(backend, job, label)
        except Exception:
            self._drop(token)  # either way the batch ends here
            raise
        next_run = self._next_run(request, mode, job, image, token, backend_id)
        if next_run is None:
            self._drop(token)
        return RunImageResponse(
            image=image,
            mode=job.mode,
            prompt=job.prompt,
            position=label or "1 image",
            elapsed=self._clock() - started,
            next_run=next_run,
        )

    def _load_references(self, request: RunImageRequest, mode: ModeSpec) -> tuple[tuple[ReferenceImage, ...], str]:
        if request.reference_token:
            images = self._references.get(request.reference_token)
            if images is None:
                raise ReferenceExpired("The reference image expired. Pick it again.")
            mode.check_references(len(images))
            return images, request.reference_token
        mode.check_references(len(request.references))
        if not request.references:
            return (), ""
        return request.references, self._references.add(request.references)

    def _seed(self, raw: str) -> int:
        text = raw.strip()
        if not text:
            return self._seed_source()
        if not text.isdigit():
            raise InvalidJob("seed must be a whole number")
        return int(text)

    def _run(self, backend: ImageBackendGateway, job: ImageJob, label: str) -> ImageResult:
        if self._progress.consume_cancel():
            raise Cancelled("stopped before this image started")
        self._progress.begin(label)
        try:
            return backend.run(job, self._progress.set_step, self._progress.cancel_requested)
        except Cancelled:
            # Only a cancel this run obeyed is spent. One that lands after the
            # engine's last look must still stop the next image of the batch.
            self._progress.clear_cancel()
            raise
        finally:
            self._progress.finish()

    @staticmethod
    def _next_run(
        request: RunImageRequest, mode: ModeSpec, job: ImageJob, image: ImageResult, token: str, backend_id: str
    ) -> NextRun | None:
        if request.index >= request.total:
            return None
        # The raw values, not the parsed ones, so the next request parses the same way.
        declared = {param.id for param in mode.params}
        options = {key: value for key, value in request.options.items() if key in declared}
        return NextRun(
            mode=job.mode,
            prompt=job.prompt,
            seed=image.seed + 1,
            options=options,
            total=request.total,
            index=request.index + 1,
            reference_token=token,
            backend=backend_id,
        )

    def _drop(self, token: str) -> None:
        if token:
            self._references.drop(token)
