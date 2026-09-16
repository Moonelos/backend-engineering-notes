from kafka_notes.effect_store import apply_once, initialize


def test_duplicate_returns_the_first_durable_result(tmp_path):
    store = str(tmp_path / "effects.sqlite")
    initialize(store)
    assert apply_once(store, "evt-101", "charge-ok-1") == ("charge-ok-1", True)
    assert apply_once(store, "evt-101", "charge-ok-2") == ("charge-ok-1", False)
