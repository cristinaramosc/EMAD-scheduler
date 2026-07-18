from __future__ import annotations

import pytest

from backend.services.session_decomposer import SessionDecomposer, SessionDecompositionError


def test_decompose_5_to_2p5_2p5():
    dec = SessionDecomposer()
    result = dec.decompose(5.0, [2.5, 3.0])
    assert sorted(result) == [2.5, 2.5]


def test_decompose_5_to_3_and_2_when_2p5_not_allowed():
    dec = SessionDecomposer()
    result = dec.decompose(5.0, [2.0, 3.0])
    assert sorted(result) == [2.0, 3.0]


def test_decompose_6_to_3_3():
    dec = SessionDecomposer()
    result = dec.decompose(6.0, [1.0, 2.0, 3.0])
    assert sorted(result) == [3.0, 3.0]


def test_invalid_parameters():
    dec = SessionDecomposer()
    with pytest.raises(SessionDecompositionError):
        dec.decompose(None, [2.0, 3.0])
    with pytest.raises(SessionDecompositionError):
        dec.decompose(2.0, [])


def test_no_valid_decomposition():
    dec = SessionDecomposer()
    with pytest.raises(SessionDecompositionError):
        dec.decompose(5.0, [1.5])
