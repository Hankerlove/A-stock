def test_charts_directory_is_ignored():
    assert "charts/" in open(".gitignore", encoding="utf-8").read().splitlines()
