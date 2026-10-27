def pytest_configure(config):
    config.addinivalue_line("markers", "pending_operator: menunggu putusan operator (isu terbuka)")
