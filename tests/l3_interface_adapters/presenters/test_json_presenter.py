"""Transport links are added to a copy, without entering retained operation state."""

import pytest

from studio.l3_interface_adapters.presenters.json_presenter import operation_document


@pytest.mark.parametrize("retained", [False, True])
def test_operation_links_keep_the_existing_wire_contract_without_mutating_storage(retained):
    record = {"id": "owned", "status": "running", "result_retained": retained}
    document = operation_document(record)

    assert document == {
        "id": "owned",
        "status": "running",
        "status_url": "/api/v1/operations/owned",
        "result_url": "/api/v1/operations/owned/result" if retained else None,
    }
    assert record == {"id": "owned", "status": "running", "result_retained": retained}
