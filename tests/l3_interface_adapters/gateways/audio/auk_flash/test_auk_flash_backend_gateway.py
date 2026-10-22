"""Pin model identity and preserve the shared engine's callbacks and batch lifecycle."""

from unittest.mock import Mock

from studio.l3_interface_adapters.gateways.audio.auk_flash import auk_flash_backend_gateway as module


def test_the_gateway_has_a_fixed_model_identity_without_loading_weights():
    child = Mock()
    gateway = module.AukFlashBackendGateway(child)

    assert gateway.capabilities().backend_id == "auk"
    child.wait_ready.assert_not_called()


def test_the_gateway_forwards_loading_batching_rendering_and_release(monkeypatch):
    engine = Mock()
    factory = Mock(return_value=engine)
    monkeypatch.setattr(module, "AukEngine", factory)
    child, job, progress, cancelled = (Mock() for _ in range(4))
    gateway = module.AukFlashBackendGateway(child)
    gateway.load()
    gateway.prepare_batch([job], cancelled)
    assert gateway.run(job, progress, cancelled) is engine.run.return_value
    gateway.release()

    factory.assert_called_once_with(child, "flash")
    engine.load.assert_called_once_with()
    engine.prepare_batch.assert_called_once_with([job], cancelled)
    engine.run.assert_called_once_with(job, progress, cancelled)
    engine.release.assert_called_once_with()
