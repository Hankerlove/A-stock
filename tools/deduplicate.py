"""数据去重脚本：删除各表中主键重复的行。"""
from astock.data.store.db import DataStore

s = DataStore('data/astock.duckdb', 'data/')

tables = [
    ('stock_basic', ['ts_code']),
    ('trade_cal', ['cal_date', 'exchange']),
    ('daily', ['ts_code', 'trade_date']),
    ('adj_factor', ['ts_code', 'trade_date']),
    ('daily_basic', ['ts_code', 'trade_date']),
    ('suspend_d', ['ts_code', 'trade_date', 'suspend_type']),
    ('tech_indicator', ['ts_code', 'trade_date']),
]

for t, cols in tables:
    removed = s.deduplicate(t, subset=cols)
    print(f'{t}: 删除 {removed:,} 行, 剩余 {s.row_count(t):,} 行')
