from simon.capabilities import available_capability_ids, capability_catalog_for_model


def test_runtime_exposes_user_ask_and_process_run_as_available() -> None:
    assert available_capability_ids() == frozenset({"user.ask", "process.run"})


def test_capability_catalog_distinguishes_known_from_available() -> None:
    catalog = capability_catalog_for_model()
    by_id = {str(item["id"]): item for item in catalog}

    assert by_id["user.ask"]["available_now"] is True
    assert by_id["user.perform"]["available_now"] is False
    assert by_id["file.read"]["available_now"] is False
    assert by_id["process.run"]["available_now"] is True
    assert by_id["unknown"]["available_now"] is False
