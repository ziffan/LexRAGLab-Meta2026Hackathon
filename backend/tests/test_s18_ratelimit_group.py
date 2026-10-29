"""M3.2-effort-sweep S18: pembatas laju bersama `rate_group` dan kunci lintas proses `model_api_meta.lock` (P9). Jam disuntik."""

import pytest

from backend.spark import ratelimit, rpmlock
from backend.spark.ratelimit import get_limiter, reset_registry

from .spark_fakes import Clock

KEY = "synthetic-key-0123456789"


@pytest.fixture(autouse=True)
def _reset():
    reset_registry()
    yield
    reset_registry()


def test_s18_a_group_shares_one_140_rpm_window():
    clk = Clock(0.0)
    main = get_limiter("meta", KEY, None, 140)
    sweep = get_limiter("sweep_meta_medium", KEY, "meta", 140)
    assert main is sweep  # kunci registri (rate_group, sidik key)
    starts = [main.acquire(140, clk.now, clk.sleep) for _ in range(100)]
    starts += [sweep.acquire(140, clk.now, clk.sleep) for _ in range(40)]
    assert starts == [0.0] * 140 and clk.sleeps == []
    t141 = sweep.acquire(140, clk.now, clk.sleep)  # ke-141 menunggu sampai awal pertama keluar jendela
    assert t141 == 60.0 and clk.sleeps == [60.0]


def test_s18_a_without_group_each_profile_has_its_own_window_bug_control():
    clk = Clock(0.0)
    a = get_limiter("meta", KEY)
    b = get_limiter("sweep_meta_medium", KEY)  # tanpa kelompok: dua pembatas (280 RPM efektif)
    assert a is not b
    for lim, n in ((a, 100), (b, 41)):
        for _ in range(n):
            lim.acquire(140, clk.now, clk.sleep)
    assert clk.sleeps == []


def test_s18_b_different_key_or_group_do_not_share():
    meta = get_limiter("meta", KEY)
    assert get_limiter("sweep_meta_medium", "other-key-0123456789", "meta", 140) is not meta
    bt = get_limiter("baseten_open", KEY)
    assert get_limiter("sweep_baseten_high", KEY, "baseten_open", 140) is bt
    assert get_limiter("sweep_baseten_high", KEY, "baseten_open", 140) is not get_limiter("sweep_meta_high", KEY, "meta", 140)


def test_s18_c_no_group_keeps_profile_key():
    get_limiter("meta", KEY)
    assert [k[0] for k in ratelimit._registry] == ["meta"]


def test_s18_e_group_max_rpm_is_minimum_of_members():
    clk = Clock(0.0)
    lim = get_limiter("p1", KEY, "grp", 140)
    assert get_limiter("p2", KEY, "grp", 70) is lim
    for _ in range(70):
        lim.acquire(140, clk.now, clk.sleep)
    assert clk.sleeps == []
    assert lim.acquire(140, clk.now, clk.sleep) == 60.0  # ke-71 menunggu: 70 berlaku untuk kelompok


def test_s18_e_group_max_rpm_minimum_in_reverse_order():
    clk = Clock(0.0)
    lim = get_limiter("p1", KEY, "grp2", 70)
    assert get_limiter("p2", KEY, "grp2", 140) is lim and lim.group_max_rpm == 70


def test_s18_client_uses_rate_group_for_sweep_meta(tmp_path):
    from .sweep_helpers import make_client
    c, _ = make_client(tmp_path, "sweep_meta_medium")
    m, _ = make_client(tmp_path / "m", "meta")
    assert c._limiter is m._limiter
    b, _ = make_client(tmp_path / "b", "baseten_open")
    sb, _ = make_client(tmp_path / "sb", "sweep_baseten_high")
    assert sb._limiter is b._limiter and sb._limiter is not c._limiter


# ---- kunci lintas proses
def alive(_pid):
    return True


def dead(_pid):
    return False


def test_s18_d_second_sweep_runner_refused_busy(tmp_path):
    runs = tmp_path / "runs"
    lock = rpmlock.acquire(runs, "sweep-b", pid=4242, pid_alive=alive)
    assert rpmlock.lock_path(runs).name == "model_api_meta.lock" and rpmlock.lock_path(runs).parent.name == "locks"
    with pytest.raises(rpmlock.RpmLockBusy) as ei:
        rpmlock.acquire(runs, "sweep-a", pid=4343, pid_alive=alive)
    assert ei.value.code == "rpm_lock_busy" and "sweep-b" in str(ei.value) and "4242" in str(ei.value)
    lock.release()
    rpmlock.acquire(runs, "sweep-a", pid=4343, pid_alive=alive).release()
    assert not rpmlock.lock_path(runs).exists()


def test_s18_d_released_on_exception_and_keyboard_interrupt(tmp_path):
    runs = tmp_path / "runs"
    for exc in (RuntimeError, KeyboardInterrupt):
        with pytest.raises(exc):
            with rpmlock.acquire(runs, "sweep-b", pid=1, pid_alive=alive):
                raise exc()
        assert not rpmlock.lock_path(runs).exists()


def test_s18_d_stale_not_removed_unless_break_flag(tmp_path):
    runs = tmp_path / "runs"
    rpmlock.acquire(runs, "sweep-b", pid=999, pid_alive=alive)
    with pytest.raises(rpmlock.RpmLockStale) as ei:
        rpmlock.acquire(runs, "sweep-a", pid=5, pid_alive=dead)
    assert ei.value.code == "rpm_lock_stale" and rpmlock.lock_path(runs).exists()
    lk = rpmlock.acquire(runs, "sweep-a", pid=5, pid_alive=dead, break_stale=True)
    assert lk.broke_stale and lk.broke_stale["pid"] == 999
    lk.release()


def test_s18_lock_dir_is_outside_hashed_dirs(tmp_path):
    p = rpmlock.lock_path(tmp_path / "runs")
    assert p.relative_to(tmp_path / "runs").parts[0] == "locks"
