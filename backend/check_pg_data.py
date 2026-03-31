#!/usr/bin/env python3
"""检查 PostgreSQL 数据库中的 stock_kline 数据"""

import os
from sqlalchemy import create_engine, text

# 数据库连接配置
db_host = os.getenv("DB_HOST", "192.168.1.207")
db_port = int(os.getenv("DB_PORT", "5432"))
db_user = os.getenv("DB_USER", "datadriver")
db_password = os.getenv("DB_PASSWORD", "datadriver")
db_name = os.getenv("DB_NAME", "datadriver")

engine = create_engine(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

# 1. 查询各周期的数据量
print("="*80)
print("各周期数据量统计:")
print("="*80)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT period, COUNT(*) as cnt
        FROM stock_kline
        GROUP BY period
        ORDER BY period
    """))
    for row in result:
        print(f"  {row[0]:<15} : {row[1]:>10} 条")

# 2. 查询是否有季线数据
print("\n" + "="*80)
print("季线数据检查 (period='quarterly'):")
print("="*80)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT ts_code, COUNT(*) as cnt,
               MIN(trade_time) as earliest,
               MAX(trade_time) as latest
        FROM stock_kline
        WHERE period = 'quarterly'
        GROUP BY ts_code
        ORDER BY cnt DESC
        LIMIT 10
    """))
    rows = result.fetchall()
    if rows:
        print(f"  共找到季线数据：{len(rows)} 只股票")
        for row in rows:
            print(f"    {row[0]:<12} : {row[1]:>5} 条, {row[2]} ~ {row[3]}")
    else:
        print("  ⚠️  没有找到季线数据！")

# 3. 查询是否有年线数据
print("\n" + "="*80)
print("年线数据检查 (period='yearly'):")
print("="*80)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT ts_code, COUNT(*) as cnt,
               MIN(trade_time) as earliest,
               MAX(trade_time) as latest
        FROM stock_kline
        WHERE period = 'yearly'
        GROUP BY ts_code
        ORDER BY cnt DESC
        LIMIT 10
    """))
    rows = result.fetchall()
    if rows:
        print(f"  共找到年线数据：{len(rows)} 只股票")
        for row in rows:
            print(f"    {row[0]:<12} : {row[1]:>5} 条, {row[2]} ~ {row[3]}")
    else:
        print("  ⚠️  没有找到年线数据！")

# 4. 检查上证指数的季线数据
print("\n" + "="*80)
print("上证指数 (000001.SH) 各周期数据量:")
print("="*80)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT period, COUNT(*) as cnt,
               MIN(trade_time) as earliest,
               MAX(trade_time) as latest
        FROM stock_kline
        WHERE ts_code = '000001.SH'
        GROUP BY period
        ORDER BY period
    """))
    for row in result:
        print(f"  {row[0]:<15} : {row[1]:>5} 条, {row[2]} ~ {row[3]}")

print("\n" + "="*80)
print("检查完成")
print("="*80)
