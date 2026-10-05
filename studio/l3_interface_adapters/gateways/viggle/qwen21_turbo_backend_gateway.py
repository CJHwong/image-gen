from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.viggle.capabilities import viggle_turbo_capabilities
from studio.l3_interface_adapters.gateways.viggle_schedule import viggle_schedule

# Where the adapter comes from, in the README's words. The message names the whole
# command, because a user who enabled this backend without it has nothing else to
# go on: the base weights are already cached, so nothing else downloads.
#
# `hf`, not `huggingface-cli`: huggingface_hub 2.x deprecated the old name and the
# old name now exits without downloading anything. Measured 2026-10-05.
ADAPTER = "Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r256.safetensors"
RECIPE = f"hf download Viggle/Qwen-Image-2.1-viggle-turbo {ADAPTER} --local-dir <the folder in studio.toml>"


class Qwen21TurboBackendGateway(ImageBackendGateway):
    """Viggle Turbo: Viggle's distilled Qwen-Image-2.1, six steps, no guidance.

    One of Viggle's models, so it lives in the package named for the publisher:
    a second Viggle model adds a module here rather than another package.

    The two models it drives are qwen21's, built with Viggle's adapter, so this
    package holds no model code: the composition root builds them and hands them
    in. They do not both fit on a 64 GB machine, so each run frees the other.

    The generate half samples the turbo schedule through an argument its command
    takes. The edit half cannot: mflux's edit call is given no way to choose a
    scheduler, so that call runs inside `viggle_schedule`, which supplies it for
    the length of the call.
    """

    def __init__(self, generator, edit, badge: str, lora_path: str):
        self._generator = generator
        self._edit = edit
        self._badge = badge
        self._lora_path = lora_path

    def capabilities(self):
        return viggle_turbo_capabilities(self._badge)

    def load(self):
        """Refuse here rather than in the composition root.

        A backend is built whether or not it is used, and the stub builds every
        one, so a check at build time would stop page work on a machine that never
        asked for this model. It fails when the model is actually asked for.
        """
        if not Path(self._lora_path).is_file():
            raise StudioError(
                f"Viggle Turbo needs its adapter, and {self._lora_path} does not hold it. "
                f"It is 1.3 GB and the base weights are already cached: {RECIPE}"
            )
        self._generator.load()

    def run(self, job: ImageJob, on_step, should_stop):
        if job.mode == "edit":
            self._generator.release()
            with viggle_schedule():
                return self._edit.run(job, on_step, should_stop)
        self._edit.release()
        return self._generator.run(job, on_step, should_stop)

    def release(self):
        self._generator.release()
        self._edit.release()
