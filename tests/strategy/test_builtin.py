import pandas as pd

from astock.strategy.factors import active_universe, adjusted_prices, target_weights
from astock.strategy import get_strategy, list_strategies


def _market_frame() -> dict[str, pd.DataFrame]:
    dates = ["20240102", "20240103", "20240104", "20240105"]
    daily_rows = []
    closes = {
        "000001.SZ": [10.0, 10.1, 10.2, 10.3],
        "000002.SZ": [10.0, 12.0, 9.0, 13.0],
        "600000.SH": [10.0, 10.0, 10.1, 10.1],
    }
    for code, values in closes.items():
        for date, close in zip(dates, values):
            daily_rows.append({
                "ts_code": code,
                "trade_date": date,
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "pre_close": close - 0.1,
                "pct_chg": 1.0,
                "vol": 10000.0,
                "amount": 5000.0 if code != "600000.SH" else 2000.0,
            })

    daily_basic = pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
        "trade_date": ["20240105", "20240105", "20240105"],
        "dv_ratio": [5.0, 5.5, 1.0],
        "pb": [1.0, 2.0, 0.8],
        "pe_ttm": [8.0, 30.0, 9.0],
        "total_mv": [100000.0, 200000.0, 80000.0],
        "turnover_rate": [1.0, 1.0, 1.0],
    })
    adj_factor = pd.DataFrame({
        "ts_code": [row["ts_code"] for row in daily_rows],
        "trade_date": [row["trade_date"] for row in daily_rows],
        "adj_factor": [1.0 for _ in daily_rows],
    })
    stock_basic = pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
        "name": ["低波红利", "高波红利", "低估值"],
        "industry": ["银行", "科技", "银行"],
        "list_status": ["L", "L", "L"],
        "list_date": ["20000101", "20000101", "20000101"],
        "delist_date": [None, None, None],
    })
    return {
        "daily": pd.DataFrame(daily_rows),
        "daily_basic": daily_basic,
        "adj_factor": adj_factor,
        "stock_basic": stock_basic,
    }


def _price_only_market_frame() -> dict[str, pd.DataFrame]:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108", "20240109"]
    closes = {
        "000001.SZ": [10.0, 11.0, 12.0, 13.0, 12.5, 12.4],
        "000002.SZ": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
        "600000.SH": [10.0, 9.0, 8.0, 8.1, 8.2, 8.3],
    }
    volumes = {
        "000001.SZ": [100.0, 100.0, 110.0, 120.0, 130.0, 140.0],
        "000002.SZ": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "600000.SH": [100.0, 90.0, 80.0, 80.0, 80.0, 80.0],
    }
    daily_rows = []
    for code, values in closes.items():
        for i, (date, close) in enumerate(zip(dates, values)):
            pre_close = values[i - 1] if i > 0 else close
            daily_rows.append({
                "ts_code": code,
                "trade_date": date,
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "pre_close": pre_close,
                "pct_chg": (close / pre_close - 1.0) * 100.0 if pre_close else 0.0,
                "vol": volumes[code][i],
                "amount": volumes[code][i] * close * 100.0,
            })
    adj_factor = pd.DataFrame({
        "ts_code": [row["ts_code"] for row in daily_rows],
        "trade_date": [row["trade_date"] for row in daily_rows],
        "adj_factor": [1.0 for _ in daily_rows],
    })
    stock_basic = pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
        "list_status": ["L", "L", "L"],
        "list_date": ["20000101", "20000101", "20000101"],
        "delist_date": [None, None, None],
    })
    return {
        "daily": pd.DataFrame(daily_rows),
        "adj_factor": adj_factor,
        "stock_basic": stock_basic,
    }


def _breakout_market_frame() -> dict[str, pd.DataFrame]:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108"]
    closes = {
        "000001.SZ": [10.0, 10.2, 10.1, 10.3, 11.0],
        "000002.SZ": [10.0, 10.1, 10.2, 10.25, 10.26],
        "600000.SH": [10.0, 10.1, 10.2, 10.1, 10.0],
    }
    volumes = {
        "000001.SZ": [100.0, 100.0, 100.0, 100.0, 300.0],
        "000002.SZ": [100.0, 100.0, 100.0, 100.0, 110.0],
        "600000.SH": [100.0, 100.0, 100.0, 100.0, 300.0],
    }
    daily_rows = []
    for code, values in closes.items():
        for i, (date, close) in enumerate(zip(dates, values)):
            pre_close = values[i - 1] if i > 0 else close
            daily_rows.append({
                "ts_code": code,
                "trade_date": date,
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "pre_close": pre_close,
                "pct_chg": (close / pre_close - 1.0) * 100.0 if pre_close else 0.0,
                "vol": volumes[code][i],
                "amount": volumes[code][i] * close * 100.0,
            })
    adj_factor = pd.DataFrame({
        "ts_code": [row["ts_code"] for row in daily_rows],
        "trade_date": [row["trade_date"] for row in daily_rows],
        "adj_factor": [1.0 for _ in daily_rows],
    })
    return {
        "daily": pd.DataFrame(daily_rows),
        "adj_factor": adj_factor,
    }


def test_registry_lists_builtin_strategies():
    names = list_strategies()

    assert "dividend-low-vol" in names
    assert "value-low-vol" in names
    assert "momentum-reversal" in names
    assert "volume-price-breakout" in names


def test_get_strategy_rejects_unknown_name():
    try:
        get_strategy("missing-strategy")
    except ValueError as exc:
        assert "missing-strategy" in str(exc)
    else:
        raise AssertionError("missing strategy should raise ValueError")


def test_dividend_low_vol_selects_high_dividend_low_volatility():
    strategy = get_strategy(
        "dividend-low-vol",
        top_n=1,
        lookback_days=3,
        min_amount=1000.0,
        dividend_weight=0.7,
        volatility_weight=0.3,
    )

    signal = strategy.generate(_market_frame(), "20240105")

    assert signal.trade_date == "20240105"
    assert signal.weights.to_dict() == {"000001.SZ": 1.0}
    assert signal.scores.iloc[0]["ts_code"] == "000001.SZ"


def test_strategy_parameters_filter_by_liquidity_and_top_n():
    strategy = get_strategy(
        "dividend-low-vol",
        top_n=2,
        lookback_days=3,
        min_amount=4000.0,
    )

    signal = strategy.generate(_market_frame(), "20240105")

    assert list(signal.weights.index) == ["000001.SZ", "000002.SZ"]
    assert signal.weights.sum() == 1.0


def test_dividend_low_vol_accepts_pre_adjusted_daily_from_loader():
    market = _market_frame()
    market["daily"] = adjusted_prices(market["daily"], market["adj_factor"])
    strategy = get_strategy(
        "dividend-low-vol",
        top_n=1,
        lookback_days=3,
        min_amount=1000.0,
    )

    signal = strategy.generate(market, "20240105")

    assert signal.weights.to_dict() == {"000001.SZ": 1.0}


def test_active_universe_accepts_integer_delist_date():
    stock_basic = pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ"],
        "list_status": ["L", "L"],
        "list_date": ["20000101", "20000101"],
        "delist_date": pd.Series([pd.NA, 20200101], dtype="Int32"),
    })

    assert active_universe(stock_basic, "20240105") == {"000001.SZ"}


def test_value_low_vol_uses_value_fields():
    strategy = get_strategy(
        "value-low-vol",
        top_n=1,
        lookback_days=3,
        min_amount=1000.0,
        pb_weight=0.5,
        pe_weight=0.3,
        volatility_weight=0.2,
    )

    signal = strategy.generate(_market_frame(), "20240105")

    assert signal.weights.to_dict() == {"600000.SH": 1.0}


def test_momentum_reversal_selects_medium_momentum_recent_pullback():
    strategy = get_strategy(
        "momentum-reversal",
        top_n=1,
        momentum_window=3,
        reversal_window=2,
        skip_days=0,
        min_amount=1000.0,
        momentum_weight=0.7,
        reversal_weight=0.3,
    )

    signal = strategy.generate(_price_only_market_frame(), "20240109")

    assert signal.weights.to_dict() == {"000001.SZ": 1.0}
    assert signal.scores.iloc[0]["ts_code"] == "000001.SZ"


def test_volume_price_breakout_selects_price_and_volume_breakout():
    strategy = get_strategy(
        "volume-price-breakout",
        top_n=1,
        breakout_window=3,
        volume_window=3,
        volume_multiplier=2.0,
        min_pct_chg=1.0,
        min_amount=1000.0,
    )

    signal = strategy.generate(_breakout_market_frame(), "20240108")

    assert signal.weights.to_dict() == {"000001.SZ": 1.0}
    assert signal.scores.iloc[0]["volume_ratio"] >= 2.0


def test_strategy_returns_empty_signal_when_no_trade_date_data():
    strategy = get_strategy("dividend-low-vol", top_n=3)

    signal = strategy.generate(_market_frame(), "20240109")

    assert signal.weights.empty
    assert signal.scores.empty


def test_target_weights_respects_max_weight_cap():
    scores = pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
        "score": [100.0, 1.0, 1.0],
    })

    weights = target_weights(scores, "score", top_n=3, max_weight_per_stock=0.6)

    assert weights.max() <= 0.6
    assert weights.sum() == 1.0
