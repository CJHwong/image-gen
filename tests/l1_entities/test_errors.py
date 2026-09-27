"""The failures the studio tells the user about, as one family.

The page catches StudioError once and renders its message in one line. A failure
declared outside the family reaches the user as a traceback instead.
"""

import pytest

from studio.l1_entities import errors


def test_every_declared_failure_belongs_to_the_studio_error_family():
    # The page has one handler, `except StudioError`. A new failure that skips the
    # family would show the user a traceback rather than the one line it wrote.
    family = vars(errors).values()
    declared = [value for value in family if isinstance(value, type) and issubclass(value, Exception)]
    assert errors.InvalidJob in declared
    assert all(issubclass(member, errors.StudioError) for member in declared)


def test_a_refused_job_is_also_a_value_error():
    # ParamSpec.parse raises InvalidJob out of a form value, and the caller above
    # it already treats a bad value as a ValueError. Both handlers stay correct.
    assert issubclass(errors.InvalidJob, ValueError)


def test_an_unsupported_mode_is_a_refused_job():
    # Capabilities.mode raises where every other refusal raises, so the caller
    # needs no second handler for a mode the backend does not declare.
    assert issubclass(errors.UnsupportedMode, errors.InvalidJob)


@pytest.mark.parametrize(
    "failure, message",
    [
        (errors.StudioError, "the engine is gone"),
        (errors.MissingPrompt, "A prompt is required."),
        (errors.UnreadableImage, "That image cannot be read."),
        (errors.ReferenceExpired, "Pick the image again."),
        (errors.Cancelled, "stopped at step 3"),
        (errors.BackendBusy, "Wait for the run in flight."),
        (errors.UnknownBackend, "No backend is registered under that id."),
        (errors.BackendChanged, "The page was built for another backend."),
    ],
)
def test_the_message_reaches_the_page_unchanged(failure, message):
    # The page prints str(error) as the whole explanation, so the wording the
    # raiser chose is the wording the user reads.
    assert str(failure(message)) == message
