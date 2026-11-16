"""Tests for taskbits.single_instance."""

import uuid

from taskbits.single_instance import SingleInstance


def test_second_holder_sees_already_running() -> None:
    name = f"Local\\taskbits-test-{uuid.uuid4()}"  # unique: never clashes with a real instance
    first = SingleInstance(name)
    second = SingleInstance(name)
    assert not first.already_running
    assert second.already_running
