def pytest_configure(config):
    config.addinivalue_line("markers", "pending_operator: menunggu putusan operator (isu terbuka)")


# Klien Spark M0.1: pembatas laju bersifat per proses, jadi dikosongkan sebelum dan sesudah tiap test.
import pytest  # noqa: E402

from backend.spark import ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_spark_limiters():
    ratelimit.reset_registry()
    yield
    ratelimit.reset_registry()
