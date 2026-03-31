#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
东方财富网 A股行情数据爬虫

从东方财富网免费接口获取A股所有股票行情数据，保存到本地 SQLite 数据库。

使用方法:
    python eastmoney_spider.py run          # 运行数据抓取
    python eastmoney_spider.py run --full   # 全量更新（清除旧数据重新抓取）
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from typing import Optional

import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 东方财富网 API 配置
EASTMONEY_API_URL = (
    "http://push2.eastmoney.com/api/qt/clist/get"
    "?pn=1&pz=50000&po=1&np=1"
    "&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&wbp2u=%7C0%7C0%7C0%7Cweb"
    "&fid=f3"
    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    "&fields=f1,f2,f3,f4,f5,f6,f7,f12,f13,f14,f15,f16,f17,f18,f20,f21,f24,f25,"
    "f37,f38,f39,f40,f41,f43,f44,f45,f62,f115,f128,f140,f141"
)

# 字段映射：东方财富API字段 -> 数据库字段
FIELD_MAPPING = {
    'f1': None,  # 保留字段，不存储
    'f2': 'latest_price',       # 最新价
    'f3': 'pct_chg',            # 涨跌幅
    'f4': 'change',             # 涨跌额
    'f5': 'volume',             # 成交量（手）
    'f6': 'amount',             # 成交额
    'f7': 'amplitude',          # 振幅
    'f12': 'symbol',            # 股票代码
    'f13': 'market_code',       # 市场代码
    'f14': 'name',              # 股票名称
    'f15': 'high',              # 最高价
    'f16': 'low',               # 最低价
    'f17': 'open',              # 开盘价
    'f18': 'pre_close',         # 昨收价
    'f20': 'total_mv',          # 总市值
    'f21': 'circ_mv',           # 流通市值
    'f24': 'turnover_rate',     # 换手率
    'f25': 'pe_ttm',            # 市盈率TTM
    'f37': 'pb',                # 市净率
    'f38': 'volume_ratio',      # 量比
    'f39': 'high_52week',       # 52周最高
    'f40': 'low_52week',        # 52周最低
    'f41': 'high_52week_date',  # 52周最高日期
    'f43': 'rise_count',        # 上涨家数（用于指数）
    'f44': 'fall_count',        # 下跌家数（用于指数）
    'f45': 'flat_count',        # 平盘家数（用于指数）
    'f62': 'net_asset_ps',      # 每股净资产
    'f115': 'pe_lyr',           # 市盈率LYR
    'f128': 'value',            # 价值（用于某些特殊品种）
    'f140': 'pct_chg_3month',   # 3个月涨跌幅
    'f141': 'pct_chg_6month',   # 6个月涨跌幅
}

# 数据库配置
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db')
DB_PATH = os.path.join(DB_DIR, 'stocks.db')


def ensure_db_dir():
    """确保数据库目录存在"""
    os.makedirs(DB_DIR, exist_ok=True)


def init_database():
    """初始化数据库，创建表结构"""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT,
            market_code INTEGER,
            latest_price REAL,
            pct_chg REAL,
            change REAL,
            volume REAL,
            amount REAL,
            amplitude REAL,
            high REAL,
            low REAL,
            open REAL,
            pre_close REAL,
            total_mv REAL,
            circ_mv REAL,
            turnover_rate REAL,
            pe_ttm REAL,
            pb REAL,
            volume_ratio REAL,
            high_52week REAL,
            low_52week REAL,
            high_52week_date TEXT,
            rise_count INTEGER,
            fall_count INTEGER,
            flat_count INTEGER,
            net_asset_ps REAL,
            pe_lyr REAL,
            value REAL,
            pct_chg_3month REAL,
            pct_chg_6month REAL,
            update_time TEXT NOT NULL,
            UNIQUE(symbol, update_time)
        )
    ''')

    # 创建索引
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_symbol ON stock_quotes(symbol)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_update_time ON stock_quotes(update_time)
    ''')

    conn.commit()
    conn.close()
    logger.info(f"数据库初始化完成: {DB_PATH}")


def fetch_stock_data() -> Optional[list]:
    """从东方财富网API获取股票行情数据"""
    logger.info("正在从东方财富网获取股票行情数据...")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }

        response = requests.get(EASTMONEY_API_URL, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        if data.get('data') and data['data'].get('diff'):
            stock_list = data['data']['diff']
            logger.info(f"成功获取 {len(stock_list)} 条股票数据")
            return stock_list
        else:
            logger.error(f"API返回数据格式异常: {data}")
            return None

    except requests.RequestException as e:
        logger.error(f"网络请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return None


def parse_stock_data(stock_list: list) -> list:
    """解析股票数据，转换为数据库格式"""
    parsed_data = []
    today = datetime.now().strftime('%Y-%m-%d')

    for stock in stock_list:
        record = {'update_time': today}

        for api_field, db_field in FIELD_MAPPING.items():
            if db_field is None:
                continue
            value = stock.get(api_field)
            # 处理 "-" 或空值
            if value == '-' or value == '' or value is None:
                record[db_field] = None
            else:
                record[db_field] = value

        parsed_data.append(record)

    return parsed_data


def save_to_database(parsed_data: list, full_update: bool = False) -> dict:
    """保存数据到SQLite数据库，支持增量更新"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')

    if full_update:
        # 全量更新：删除今天的数据重新插入
        cursor.execute('DELETE FROM stock_quotes WHERE update_time = ?', (today,))
        logger.info(f"全量更新模式：已清除 {today} 的数据")

    # 统计
    stats = {
        'total': len(parsed_data),
        'inserted': 0,
        'updated': 0,
        'skipped': 0
    }

    for record in parsed_data:
        # 检查是否存在
        cursor.execute(
            'SELECT id FROM stock_quotes WHERE symbol = ? AND update_time = ?',
            (record.get('symbol'), record.get('update_time'))
        )
        existing = cursor.fetchone()

        if existing:
            # 更新已存在的记录
            update_fields = []
            update_values = []
            for key, value in record.items():
                if key not in ('symbol', 'update_time'):
                    update_fields.append(f'{key} = ?')
                    update_values.append(value)

            if update_fields:
                update_values.extend([record.get('symbol'), record.get('update_time')])
                sql = f"UPDATE stock_quotes SET {', '.join(update_fields)} WHERE symbol = ? AND update_time = ?"
                cursor.execute(sql, update_values)
                stats['updated'] += 1
            else:
                stats['skipped'] += 1
        else:
            # 插入新记录
            columns = ', '.join(record.keys())
            placeholders = ', '.join(['?' for _ in record])
            sql = f"INSERT INTO stock_quotes ({columns}) VALUES ({placeholders})"
            cursor.execute(sql, list(record.values()))
            stats['inserted'] += 1

    conn.commit()
    conn.close()

    return stats


def get_latest_update_date() -> Optional[str]:
    """获取数据库中最新的更新日期"""
    if not os.path.exists(DB_PATH):
        return None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT MAX(update_time) FROM stock_quotes')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.OperationalError:
        conn.close()
        return None


def run_spider(full_update: bool = False):
    """运行爬虫主流程"""
    logger.info("=" * 60)
    logger.info("东方财富网A股行情数据爬虫启动")
    logger.info("=" * 60)

    # 初始化数据库
    init_database()

    # 检查是否需要更新
    today = datetime.now().strftime('%Y-%m-%d')
    latest_date = get_latest_update_date()

    if not full_update and latest_date == today:
        logger.info(f"今天 ({today}) 的数据已存在，跳过更新。如需强制更新请使用 --full 参数。")
        return

    if latest_date:
        logger.info(f"数据库最新数据日期: {latest_date}")

    # 获取数据
    stock_list = fetch_stock_data()
    if not stock_list:
        logger.error("获取数据失败，程序退出")
        return

    # 解析数据
    parsed_data = parse_stock_data(stock_list)
    logger.info(f"数据解析完成，共 {len(parsed_data)} 条")

    # 保存数据
    stats = save_to_database(parsed_data, full_update)

    # 输出统计结果
    logger.info("-" * 40)
    logger.info("数据更新统计:")
    logger.info(f"  总记录数: {stats['total']}")
    logger.info(f"  新增记录: {stats['inserted']}")
    logger.info(f"  更新记录: {stats['updated']}")
    logger.info(f"  跳过记录: {stats['skipped']}")
    logger.info("=" * 60)
    logger.info("数据抓取完成！")


def query_stock(symbol: str):
    """查询单只股票的最新数据"""
    if not os.path.exists(DB_PATH):
        logger.error("数据库不存在，请先运行数据抓取")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        'SELECT * FROM stock_quotes WHERE symbol = ? ORDER BY update_time DESC LIMIT 1',
        (symbol,)
    )
    result = cursor.fetchone()

    if result:
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, result))
        logger.info(f"股票 {symbol} 最新数据:")
        for key, value in record.items():
            logger.info(f"  {key}: {value}")
    else:
        logger.info(f"未找到股票 {symbol} 的数据")

    conn.close()


def show_stats():
    """显示数据库统计信息"""
    if not os.path.exists(DB_PATH):
        logger.error("数据库不存在，请先运行数据抓取")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 总记录数
    cursor.execute('SELECT COUNT(*) FROM stock_quotes')
    total = cursor.fetchone()[0]

    # 股票数量
    cursor.execute('SELECT COUNT(DISTINCT symbol) FROM stock_quotes')
    stock_count = cursor.fetchone()[0]

    # 更新日期列表
    cursor.execute('SELECT DISTINCT update_time FROM stock_quotes ORDER BY update_time DESC LIMIT 10')
    dates = cursor.fetchall()

    logger.info("数据库统计信息:")
    logger.info(f"  数据库路径: {DB_PATH}")
    logger.info(f"  总记录数: {total}")
    logger.info(f"  股票数量: {stock_count}")
    logger.info(f"  最近更新日期: {', '.join([d[0] for d in dates])}")

    conn.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='东方财富网A股行情数据爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python eastmoney_spider.py run          # 运行数据抓取
  python eastmoney_spider.py run --full   # 全量更新
  python eastmoney_spider.py query 000001 # 查询股票
  python eastmoney_spider.py stats        # 查看统计
        '''
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # run 子命令
    run_parser = subparsers.add_parser('run', help='运行数据抓取')
    run_parser.add_argument('--full', action='store_true', help='全量更新（清除当天旧数据）')

    # query 子命令
    query_parser = subparsers.add_parser('query', help='查询股票数据')
    query_parser.add_argument('symbol', type=str, help='股票代码')

    # stats 子命令
    subparsers.add_parser('stats', help='查看数据库统计')

    args = parser.parse_args()

    if args.command == 'run':
        run_spider(full_update=args.full)
    elif args.command == 'query':
        query_stock(args.symbol)
    elif args.command == 'stats':
        show_stats()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
