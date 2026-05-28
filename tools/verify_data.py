"""数据完整性校验脚本。检查本地数据库是否存在缺失、重复、异常等问题。"""
import sys
from pathlib import Path
import duckdb


def verify(conn):
    all_ok = True

    # ---- 1. 各表行数与日期范围 ----
    print("=" * 60)
    print("1. 各表概览")
    print("=" * 60)
    tables = {
        "stock_basic": ("ts_code", None),
        "trade_cal": ("cal_date, exchange", "cal_date"),
        "daily": ("ts_code, trade_date", "trade_date"),
        "adj_factor": ("ts_code, trade_date", "trade_date"),
        "daily_basic": ("ts_code, trade_date", "trade_date"),
        "suspend_d": ("ts_code, trade_date, suspend_type", "trade_date"),
    }
    for tbl, (keys, date_col) in tables.items():
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM read_parquet('data/{tbl}/*.parquet')"
            ).fetchone()[0]
            unique = conn.execute(
                f"SELECT COUNT(DISTINCT ({keys})) FROM read_parquet('data/{tbl}/*.parquet')"
            ).fetchone()[0]
            dupes = total - unique
            dup_flag = " ⚠️ 重复!" if dupes > 0 else ""
            date_info = ""
            if date_col:
                mn, mx = conn.execute(
                    f"SELECT MIN({date_col}), MAX({date_col}) FROM read_parquet('data/{tbl}/*.parquet')"
                ).fetchone()
                date_info = f" 日期范围: {mn} ~ {mx}"
            print(f"  {tbl:<16} {unique:>10,} 行  重复: {dupes:>8,}{dup_flag}{date_info}")
            if dupes > 0:
                all_ok = False
        except Exception as e:
            print(f"  {tbl:<16} 读取失败: {e}")
            all_ok = False

    # ---- 2. 检查 daily 日期连续性（与 trade_cal 对比） ----
    print()
    print("=" * 60)
    print("2. daily 日期连续性（与 trade_cal 对比）")
    print("=" * 60)
    try:
        missing = conn.execute("""
            SELECT c.cal_date
            FROM read_parquet('data/trade_cal/*.parquet') c
            WHERE c.is_open = 1
              AND c.cal_date NOT IN (
                SELECT DISTINCT trade_date FROM read_parquet('data/daily/*.parquet')
              )
            ORDER BY c.cal_date
        """).fetchall()
        if missing:
            # 只显示最近 20 个缺失日期
            recent = [r[0] for r in missing[-20:]]
            print(f"  缺失交易日: {len(missing)} 个")
            print(f"  最近缺失: {recent}")
            # 检查是否有连续大段缺失
            gaps = []
            streak_start = missing[0][0]
            prev = missing[0][0]
            for r in missing[1:]:
                if r[0] > prev:  # 不连续则断开
                    gaps.append((streak_start, prev))
                    streak_start = r[0]
                prev = r[0]
            gaps.append((streak_start, prev))
            large_gaps = [(s, e) for s, e in gaps if s != e]
            if large_gaps:
                print(f"  大段缺失区间 (起始~结束):")
                for s, e in large_gaps[:5]:
                    print(f"    {s} ~ {e}")
            all_ok = False
        else:
            print("  无缺失交易日 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")
        all_ok = False

    # ---- 3. 检查每日股票数量是否合理 ----
    print()
    print("=" * 60)
    print("3. daily 每日股票数量抽样")
    print("=" * 60)
    try:
        samples = conn.execute("""
            SELECT trade_date, COUNT(DISTINCT ts_code) as n
            FROM read_parquet('data/daily/*.parquet')
            GROUP BY trade_date
            ORDER BY trade_date
        """).fetchall()
        if samples:
            # 打印每年第一个交易日的股票数，观察增长趋势
            yearly = {}
            for d, n in samples:
                year = d[:4]
                if year not in yearly:
                    yearly[year] = (d, n)
            print(f"  {'年份':<6} {'日期':<12} {'股票数':>8}")
            for year in sorted(yearly.keys()):
                d, n = yearly[year]
                print(f"  {year:<6} {d:<12} {n:>8}")
            # 最近日期的股票数
            latest_date, latest_n = samples[-1]
            print(f"  最新日期: {latest_date}, 股票数: {latest_n}")
            if latest_n < 5000:
                print(f"  ⚠️ 最新日期股票数偏少 (期望 ~5500，实际 {latest_n})")
                all_ok = False
    except Exception as e:
        print(f"  检查失败: {e}")
        all_ok = False

    # ---- 4. 检查 adj_factor / daily_basic 是否与 daily 日期对齐 ----
    print()
    print("=" * 60)
    print("4. adj_factor / daily_basic 对齐检查（最近 60 天）")
    print("=" * 60)
    for tbl in ["adj_factor", "daily_basic"]:
        try:
            missing = conn.execute(f"""
                SELECT d.trade_date
                FROM (SELECT DISTINCT trade_date FROM read_parquet('data/daily/*.parquet')) d
                WHERE d.trade_date >= '20260401'
                  AND d.trade_date NOT IN (
                    SELECT DISTINCT trade_date FROM read_parquet('data/{tbl}/*.parquet')
                  )
                ORDER BY d.trade_date
            """).fetchall()
            if missing:
                dates = [r[0] for r in missing]
                print(f"  {tbl}: 缺失 {len(missing)} 个日期: {dates}")
                all_ok = False
            else:
                print(f"  {tbl}: 与 daily 对齐 ✓")
        except Exception as e:
            print(f"  {tbl}: 检查失败: {e}")
            all_ok = False

    # ---- 5. 检查异常涨跌幅（A股 ±10% / 创业板科创板 ±20%） ----
    print()
    print("=" * 60)
    print("5. 异常涨跌幅检查（最近 60 天）")
    print("=" * 60)
    try:
        anomalies = conn.execute("""
            SELECT ts_code, trade_date, pct_chg
            FROM read_parquet('data/daily/*.parquet')
            WHERE trade_date >= '20260401'
              AND (
                (SUBSTR(ts_code, 1, 2) IN ('60', '00') AND ABS(pct_chg) > 10.5)
                OR
                (SUBSTR(ts_code, 1, 2) IN ('30', '68') AND ABS(pct_chg) > 20.5)
              )
            ORDER BY trade_date DESC
            LIMIT 20
        """).fetchall()
        if anomalies:
            print(f"  发现 {len(anomalies)} 条异常涨跌幅（可能含新股首日）:")
            for ts_code, trade_date, pct_chg in anomalies[:10]:
                print(f"    {trade_date} {ts_code} pct_chg={pct_chg}%")
        else:
            print("  无异常涨跌幅 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")

    # ---- 总结 ----
    print()
    if all_ok:
        print("✅ 数据校验通过，未发现问题")
    else:
        print("⚠️ 发现上述问题，建议处理")
    return all_ok


if __name__ == "__main__":
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/astock.duckdb")
    conn = duckdb.connect(str(db_path))
    try:
        ok = verify(conn)
        sys.exit(0 if ok else 1)
    finally:
        conn.close()
