"""Focused lookup failures a reviewer can distinguish at the source."""

import pytest

from comparative_evidence.normalize import path_value


@pytest.mark.parametrize(
    ("path", "error"),
    [
        pytest.param("$.replicates[0].unit", KeyError, id="absent-field"),
        pytest.param("$.replicates[1]", IndexError, id="absent-position"),
        pytest.param("$.replicates.value", TypeError, id="field-on-array"),
        pytest.param("$.replicates[0][0]", TypeError, id="index-on-object"),
        pytest.param("$.replicates[00]", ValueError, id="noncanonical-index"),
    ],
)
def test_path_lookup_error(path: str, error: type[Exception]) -> None:
    observation = {"replicates": [{"value": None}]}
    with pytest.raises(error):
        path_value(observation, path)
