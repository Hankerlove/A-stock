"""技术指标计算模块。纯 numpy 实现，无外部依赖。"""
import numpy as np
import pandas as pd


def _ema(arr: np.ndarray, n: int) -> np.ndarray:
    """指数移动平均。跳过前导 NaN，用首个完整非 NaN 窗口初始化。"""
    if len(arr) < n:
        return np.full(len(arr), np.nan)
    alpha = 2.0 / (n + 1)
    result = np.full(len(arr), np.nan)
    # 找到第一个连续 n 个非 NaN 的窗口
    idx = n - 1
    while idx < len(arr):
        if not np.any(np.isnan(arr[idx - n + 1:idx + 1])):
            break
        idx += 1
    if idx >= len(arr):
        return result
    result[idx] = np.mean(arr[idx - n + 1:idx + 1])
    for i in range(idx + 1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


def _sma(arr: np.ndarray, n: int) -> np.ndarray:
    """简单移动平均。O(n) cumsum 实现。"""
    if len(arr) < n:
        return np.full(len(arr), np.nan)
    result = np.full(len(arr), np.nan)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    result[n - 1:] = (cumsum[n:] - cumsum[:-n]) / n
    return result


def _rsi(arr: np.ndarray, n: int) -> np.ndarray:
    """相对强弱指数，Wilder 平滑法。"""
    if len(arr) < n + 1:
        return np.full(len(arr), np.nan)
    delta = np.diff(arr)
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    result = np.full(len(arr), np.nan)
    avg_gain = np.mean(up[:n])
    avg_loss = np.mean(down[:n])
    result[n] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) if avg_loss > 0 else 100.0 if avg_gain > 0 else np.nan
    alpha = 1.0 / n
    for i in range(n + 1, len(arr)):
        avg_gain = alpha * up[i - 1] + (1 - alpha) * avg_gain
        avg_loss = alpha * down[i - 1] + (1 - alpha) * avg_loss
        if avg_loss > 0:
            result[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
        elif avg_gain > 0:
            result[i] = 100.0
        else:
            result[i] = np.nan
    return result


def _kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """KDJ 随机指标。返回 (K, D, J)。"""
    length = len(close)
    k_vals = np.full(length, np.nan)
    d_vals = np.full(length, np.nan)
    j_vals = np.full(length, np.nan)
    if length < n:
        return k_vals, d_vals, j_vals
    # 初始 K=50, D=50
    k_vals[n - 1] = 50.0
    d_vals[n - 1] = 50.0
    j_vals[n - 1] = 50.0
    for i in range(n, length):
        hh = np.max(high[i - n:i])
        ll = np.min(low[i - n:i])
        rsv = (close[i] - ll) / (hh - ll) * 100.0 if hh != ll else 50.0
        k_vals[i] = 2.0 / 3.0 * k_vals[i - 1] + 1.0 / 3.0 * rsv
        d_vals[i] = 2.0 / 3.0 * d_vals[i - 1] + 1.0 / 3.0 * k_vals[i]
        j_vals[i] = 3.0 * k_vals[i] - 2.0 * d_vals[i]
    return k_vals, d_vals, j_vals


def _bollinger(arr: np.ndarray, n: int = 20, k: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """布林带。返回 (upper, mid, lower)。"""
    mid = _sma(arr, n)
    if len(arr) < n:
        return np.full(len(arr), np.nan), mid, np.full(len(arr), np.nan)
    upper = np.full(len(arr), np.nan)
    lower = np.full(len(arr), np.nan)
    for i in range(n - 1, len(arr)):
        std = np.std(arr[i - n + 1:i + 1], ddof=0)
        upper[i] = mid[i] + k * std
        lower[i] = mid[i] - k * std
    return upper, mid, lower


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    """平均真实波幅，Wilder 平滑法。"""
    length = len(close)
    if length < 2:
        return np.full(length, np.nan)
    tr = np.zeros(length)
    tr[0] = high[0] - low[0]
    for i in range(1, length):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    result = np.full(length, np.nan)
    if length <= n:
        return result
    result[n - 1] = np.mean(tr[:n])
    alpha = 1.0 / n
    for i in range(n, length):
        result[i] = alpha * tr[i] + (1 - alpha) * result[i - 1]
    return result


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """对单只股票计算所有技术指标。

    df 需包含: trade_date (已升序), adj_open, adj_high, adj_low, adj_close, vol
    返回: ts_code, trade_date, dif, dea, macd_hist, k, d, j,
           rsi6, rsi14, rsi24, ma5, ma10, ma20, ma60,
           boll_upper, boll_mid, boll_lower, atr14
    """
    ts_code = df["ts_code"].iloc[0]
    close = df["adj_close"].to_numpy(dtype=float)
    high = df["adj_high"].to_numpy(dtype=float)
    low = df["adj_low"].to_numpy(dtype=float)

    # MACD (12/26/9)
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    macd_hist = 2.0 * (dif - dea)

    # KDJ (9/3/3)
    k, d, j = _kdj(high, low, close, 9)

    # RSI
    rsi6 = _rsi(close, 6)
    rsi14 = _rsi(close, 14)
    rsi24 = _rsi(close, 24)

    # MA
    ma5 = _sma(close, 5)
    ma10 = _sma(close, 10)
    ma20 = _sma(close, 20)
    ma60 = _sma(close, 60)

    # Bollinger (20, 2)
    boll_upper, boll_mid, boll_lower = _bollinger(close, 20, 2.0)

    # ATR (14)
    atr14 = _atr(high, low, close, 14)

    return pd.DataFrame({
        "ts_code": ts_code,
        "trade_date": df["trade_date"].values,
        "dif": dif,
        "dea": dea,
        "macd_hist": macd_hist,
        "k": k,
        "d": d,
        "j": j,
        "rsi6": rsi6,
        "rsi14": rsi14,
        "rsi24": rsi24,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "boll_upper": boll_upper,
        "boll_mid": boll_mid,
        "boll_lower": boll_lower,
        "atr14": atr14,
    })
