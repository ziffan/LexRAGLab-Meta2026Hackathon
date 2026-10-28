"""H-101 Q-B3: `factor_bp` per profil dari pilot (config/header_b `[factor_bp]`), dipakai bila lebih besar dari gerbang global."""

import pytest

from backend import config as cfgmod
from backend.header_b.compare_store import factor_bp_for, validate_compare_cfg
from backend.spark.errors import ConfigInvalid

MC = {"profiles": {"baseten_open": {}, "glimmer_local": {}}}


def test_factor_bp_per_profile_takes_the_larger():
    hc = {"factor_bp": {"baseten_open": 16553}}
    validate_compare_cfg(hc, MC)
    assert factor_bp_for(hc, "baseten_open", 15700) == 16553
    assert factor_bp_for(hc, "baseten_open", 17000) == 17000  # gerbang global lebih besar menang
    assert factor_bp_for(hc, "glimmer_local", 15700) == 15700  # tanpa entri = gerbang global
    assert factor_bp_for({}, "baseten_open", 15700) == 15700


@pytest.mark.parametrize("bad", [9999, 0, -1, True, "16553", 16553.0])
def test_factor_bp_invalid_values(bad):
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg({"factor_bp": {"baseten_open": bad}}, MC)


def test_factor_bp_unknown_profile_or_not_table():
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg({"factor_bp": {"nope": 16553}}, MC)
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg({"factor_bp": 16553}, MC)


def test_real_config_factor_bp_from_pilot():
    hc, mc = cfgmod.load("header_b"), cfgmod.load("model")
    validate_compare_cfg(hc, mc)
    assert factor_bp_for(hc, "baseten_open", 15700) == 16553  # pilot: 413.717 / 249.935 dibulatkan ke atas
