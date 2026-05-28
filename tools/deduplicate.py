from astock.data.store.db import DataStore
s = DataStore('data/astock.duckdb', 'data/')
for t, cols in [('daily', ['ts_code','trade_date']),
                ('adj_factor', ['ts_code','trade_date']),
                ('daily_basic', ['ts_code','trade_date']),
                ('suspend_d', ['ts_code','trade_date','suspend_type'])]:
    removed = s.deduplicate(t, subset=cols)
    print(f'{t}: 删除 {removed:,} 行, 剩余 {s.row_count(t):,} 行')