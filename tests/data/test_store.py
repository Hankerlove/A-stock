import os
import pandas as pd
import pytest
from astock.data.store.db import DataStore
from astock.core.exceptions import StoreError


class TestDataStore:
    def test_save_and_load_append(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        assert store.table_exists("daily")
        assert store.row_count("daily") == 2

        df = store.load("daily")
        assert len(df) == 2
        assert "000001.SZ" in df["ts_code"].values

    def test_save_replace_overwrites(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        store.save("daily", sample_daily_df.head(1), mode="replace")
        assert store.row_count("daily") == 1

    def test_save_empty_df_is_noop(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", pd.DataFrame(), mode="append")
        assert not store.table_exists("daily")

    def test_load_with_filters(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        df = store.load("daily", ts_code="000001.SZ")
        assert len(df) == 1
        assert df.iloc[0]["ts_code"] == "000001.SZ"

    def test_get_latest_date(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        latest = store.get_latest_date("daily", "trade_date")
        assert latest == "20240102"

    def test_get_latest_date_empty_table(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.get_latest_date("daily", "trade_date") is None

    def test_table_exists(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert not store.table_exists("daily")
        store.save("daily", sample_daily_df, mode="append")
        assert store.table_exists("daily")

    def test_is_trade_day(self, temp_data_dir, sample_trade_cal_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("trade_cal", sample_trade_cal_df, mode="append")
        assert not store.is_trade_day("20240101")  # holiday
        assert store.is_trade_day("20240102")       # trading day
        assert not store.is_trade_day("20991231")   # not in db

    def test_get_suspended_stocks(self, temp_data_dir, sample_suspend_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("suspend_d", sample_suspend_df, mode="append")
        suspended = store.get_suspended_stocks("20240102")
        assert "000003.SZ" in suspended

    def test_get_suspended_stocks_no_data(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.get_suspended_stocks("20240102") == []

    def test_row_count(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.row_count("daily") == 0
        store.save("daily", sample_daily_df, mode="append")
        assert store.row_count("daily") == 2

    def test_parquet_files_created(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        table_dir = os.path.join(temp_data_dir, "daily")
        parquet_files = [f for f in os.listdir(table_dir) if f.endswith(".parquet")]
        assert len(parquet_files) > 0
