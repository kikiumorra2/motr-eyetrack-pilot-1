import random

import pytest

from motr_char_events import ALPHABET, CharEventsError, unzigzag, vlq_decode, vlq_encode, zigzag


def test_alphabet():
    assert len(ALPHABET) == 64 and len(set(ALPHABET)) == 64


@pytest.mark.parametrize("v,z", [(0, 0), (-1, 1), (1, 2), (-2, 3), (2, 4), (-16, 31), (16, 32)])
def test_zigzag(v, z):
    assert zigzag(v) == z and unzigzag(z) == v


def test_fixed_vectors():
    assert vlq_encode([0]) == "A"
    assert vlq_encode([-1]) == "B"
    assert vlq_encode([1]) == "C"
    assert vlq_encode([15]) == "e"
    assert vlq_encode([16]) == "gB"
    assert vlq_encode([-16]) == "f"
    assert vlq_encode([50]) == "kD"
    assert vlq_encode([812, 121, 190]) == "4yByH8L"
    assert vlq_decode("4yByH8L") == [812, 121, 190]
    assert vlq_encode([]) == "" and vlq_decode("") == []


def test_extremes_and_fuzz():
    vals = [0, 1, -1, 31, 32, -32, 2 ** 31, -(2 ** 31), 2 ** 40, -(2 ** 40), 2 ** 52 - 1, -(2 ** 52)]
    assert vlq_decode(vlq_encode(vals)) == vals
    rnd = random.Random(42)
    for _ in range(5000):
        arr = [rnd.randint(-lim, lim) for lim in (rnd.choice([16, 1000, 10 ** 6, 2 ** 40]) for _ in range(rnd.randint(0, 12)))]
        assert vlq_decode(vlq_encode(arr)) == arr


def test_errors():
    with pytest.raises(CharEventsError, match="invalid VLQ character"):
        vlq_decode("A!B")
    with pytest.raises(CharEventsError, match="dangling"):
        vlq_decode("4")
    with pytest.raises(ValueError, match="too large"):
        vlq_encode([2 ** 53])
    with pytest.raises(TypeError):
        vlq_encode([1.5])
