"""
东方财富网 A 股行情数据爬虫

功能:
1. 从东方财富网获取所有 A 股实时行情数据
2. 支持解析并返回结构化数据
3. 支持保存到数据库

接口说明:
- 东方财富网行情接口返回的字段含义:
  f1: 未知
  f2: 最新价
  f3: 涨跌幅
  f4: 涨跌额
  f5: 成交量(手)
  f6: 成交额
  f7: 振幅
  f12: 股票代码
  f13: 市场代码(0深市,1沪市)
  f14: 股票名称
  f15: 最高价
  f16: 最低价
  f17: 今开
  f18: 昨收
  f20: 总市值
  f21: 流通市值
  f24: 市盈率(动态)
  f25: 市净率
  f37: 换手率
  f38: 量比
  f39: 市盈率(静态)
  f40: 市销率
  f41: 市现率
  f43: 量比(动态)
  f44: 涨速
  f45: 5分钟涨跌
  f62: 净资产收益率
  f115: 市盈率(TTM)
  f128: 市净率(市净率)
  f140: 总股本
  f141: 流通股本
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from django.db import transaction

logger = logging.getLogger(__name__)


class EastmoneySpider:
    """东方财富网行情数据爬虫"""

    # A股行情接口 URL
    QUOTE_URL = "http://push2.eastmoney.com/api/qt/clist/get"

    # 接口参数
    DEFAULT_PARAMS = {
        "pn": 1,  # 页码
        "pz": 5000,  # 每页数量
        "po": 1,  # 排序方向
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "wbp2u": "|0|0|0|web",
        "fid": "f3",  # 排序字段(涨跌幅)
        # 市场类型: m:0+t:6深市A股, m:0+t:80深市创业板, m:1+t:2沪市A股, m:1+t:23沪市科创板
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        # 返回字段
        "fields": "f1,f2,f3,f4,f5,f6,f7,f12,f13,f14,f15,f16,f17,f18,f20,f21,f24,f25,f37,f38,f39,f40,f41,f43,f44,f45,f62,f115,f128,f140,f141"
    }

    # 字段映射: API字段 -> 数据库字段/业务字段
    FIELD_MAPPING = {
        'f2': 'price',           # 最新价
        'f3': 'pct_chg',         # 涨跌幅
        'f4': 'change',          # 涨跌额
        'f5': 'volume',          # 成交量(手)
        'f6': 'amount',          # 成交额
        'f7': 'amplitude',       # 振幅
        'f12': 'symbol',         # 股票代码
        'f13': 'market_code',    # 市场代码
        'f14': 'name',           # 股票名称
        'f15': 'high',           # 最高价
        'f16': 'low',            # 最低价
        'f17': 'open',           # 今开
        'f18': 'pre_close',      # 昨收
        'f20': 'total_mv',       # 总市值
        'f21': 'circ_mv',        # 流通市值
        'f24': 'pe_ttm',         # 市盈率(动态)
        'f25': 'pb',             # 市净率
        'f37': 'turnover_rate',  # 换手率
        'f38': 'volume_ratio',   # 量比
        'f39': 'pe',             # 市盈率(静态)
        'f40': 'ps_ttm',         # 市销率
        'f41': 'pcf',            # 市现率
        'f43': 'volume_ratio_dyn',  # 量比(动态)
        'f44': 'up_speed',       # 涨速
        'f45': 'min5_chg',       # 5分钟涨跌
        'f62': 'roe',            # 净资产收益率
        'f115': 'pe_ttm2',       # 市盈率(TTM)
        'f128': 'pb2',           # 市净率(备用)
        'f140': 'total_share',   # 总股本
        'f141': 'float_share',   # 流通股本
    }

    # 市场代码映射
    MARKET_MAPPING = {
        0: 'SZ',  # 深市
        1: 'SH',  # 沪市
    }

    def __init__(self, timeout: int = 30):
        """
        初始化爬虫

        Args:
            timeout: 请求超时时间(秒)
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        })

    def fetch_quote_data(self, page: int = 1, page_size: int = 5000) -> Optional[Dict[str, Any]]:
        """
        获取行情数据

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            接口返回的原始数据字典，失败返回 None
        """
        params = self.DEFAULT_PARAMS.copy()
        params['pn'] = page
        params['pz'] = page_size

        try:
            response = self.session.get(
                self.QUOTE_URL,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            if data.get('data') and data['data'].get('diff'):
                return data

            logger.warning(f"接口返回数据为空: {data}")
            return None

        except requests.RequestException as e:
            logger.error(f"请求东方财富网接口失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"解析接口返回数据失败: {str(e)}")
            return None

    def parse_quote_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        解析行情数据

        Args:
            raw_data: 接口返回的原始数据

        Returns:
            解析后的股票行情列表
        """
        if not raw_data or not raw_data.get('data'):
            return []

        diff = raw_data['data'].get('diff', [])
        total = raw_data['data'].get('total', 0)

        logger.info(f"解析行情数据，共 {total} 条记录")

        parsed_data = []
        for item in diff:
            parsed_item = self._parse_single_quote(item)
            if parsed_item:
                parsed_data.append(parsed_item)

        return parsed_data

    def _parse_single_quote(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析单条行情数据

        Args:
            item: 单条原始数据

        Returns:
            解析后的行情字典
        """
        try:
            parsed = {}

            # 转换字段名
            for api_field, db_field in self.FIELD_MAPPING.items():
                value = item.get(api_field)
                # 处理特殊值 '-' 表示空值
                if value == '-' or value is None:
                    parsed[db_field] = None
                else:
                    parsed[db_field] = value

            # 生成 ts_code (格式: 000001.SZ)
            market_code = item.get('f13', 0)
            symbol = item.get('f12', '')
            if symbol:
                market = self.MARKET_MAPPING.get(market_code, 'SZ')
                parsed['ts_code'] = f"{symbol}.{market}"

            # 添加数据获取时间
            parsed['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            return parsed

        except Exception as e:
            logger.error(f"解析单条行情数据失败: {str(e)}, 原始数据: {item}")
            return None

    def get_all_quotes(self) -> List[Dict[str, Any]]:
        """
        获取所有 A 股行情数据

        Returns:
            所有股票行情列表
        """
        all_quotes = []
        page = 1

        while True:
            logger.info(f"正在获取第 {page} 页行情数据...")
            raw_data = self.fetch_quote_data(page=page)

            if not raw_data:
                break

            parsed_data = self.parse_quote_data(raw_data)
            if not parsed_data:
                break

            all_quotes.extend(parsed_data)

            # 检查是否还有更多数据
            total = raw_data.get('data', {}).get('total', 0)
            if len(all_quotes) >= total:
                break

            page += 1

        logger.info(f"共获取 {len(all_quotes)} 条行情数据")
        return all_quotes

    def close(self):
        """关闭会话"""
        self.session.close()


def fetch_all_a_stock_quotes(timeout: int = 30) -> List[Dict[str, Any]]:
    """
    获取所有 A 股实时行情数据(便捷函数)

    Args:
        timeout: 请求超时时间(秒)

    Returns:
        股票行情列表
    """
    spider = EastmoneySpider(timeout=timeout)
    try:
        return spider.get_all_quotes()
    finally:
        spider.close()


def sync_stock_quotes_to_db(
    quotes: Optional[List[Dict[str, Any]]] = None,
    model_class: Optional[Any] = None,
    batch_size: int = 500
) -> Dict[str, int]:
    """
    同步股票行情数据到数据库

    Args:
        quotes: 行情数据列表，如果为 None 则自动获取
        model_class: Django 模型类，用于存储数据
        batch_size: 批量处理大小

    Returns:
        同步结果统计 {'success': 成功数量, 'failed': 失败数量, 'total': 总数量}
    """
    # 如果未提供数据，自动获取
    if quotes is None:
        logger.info("开始获取股票行情数据...")
        quotes = fetch_all_a_stock_quotes()

    if not quotes:
        logger.warning("没有可同步的行情数据")
        return {'success': 0, 'failed': 0, 'total': 0}

    # 如果未提供模型类，返回数据供调用方处理
    if model_class is None:
        logger.info(f"获取到 {len(quotes)} 条行情数据，未指定存储模型，返回原始数据")
        return {'success': len(quotes), 'failed': 0, 'total': len(quotes), 'data': quotes}

    # 批量同步到数据库
    success_count = 0
    failed_count = 0

    try:
        with transaction.atomic():
            for i in range(0, len(quotes), batch_size):
                batch = quotes[i:i + batch_size]
                for quote in batch:
                    try:
                        # 根据 ts_code 更新或创建记录
                        model_class.objects.update_or_create(
                            ts_code=quote.get('ts_code'),
                            defaults=quote
                        )
                        success_count += 1
                    except Exception as e:
                        logger.error(f"同步股票 {quote.get('ts_code')} 失败: {str(e)}")
                        failed_count += 1

                logger.info(f"已处理 {min(i + batch_size, len(quotes))}/{len(quotes)} 条记录")

    except Exception as e:
        logger.error(f"批量同步失败: {str(e)}")
        raise

    logger.info(f"同步完成: 成功 {success_count}, 失败 {failed_count}, 总计 {len(quotes)}")
    return {
        'success': success_count,
        'failed': failed_count,
        'total': len(quotes)
    }


# Celery 任务版本
def run_eastmoney_sync_task():
    """
    Celery 任务: 同步东方财富网行情数据
    可在 tasks.py 中引用此函数
    """
    logger.info("开始执行东方财富网行情同步任务")
    result = sync_stock_quotes_to_db()
    logger.info(f"东方财富网行情同步任务完成: {result}")
    return result


if __name__ == "__main__":
    # 测试代码
    import json

    print("测试东方财富网行情爬虫...")

    # 获取行情数据
    quotes = fetch_all_a_stock_quotes()

    # 打印前5条数据
    print(f"\n获取到 {len(quotes)} 条行情数据")
    print("\n前5条数据:")
    for i, quote in enumerate(quotes[:5]):
        print(f"{i+1}. {quote.get('symbol')} {quote.get('name')} "
              f"价格: {quote.get('price')} 涨跌幅: {quote.get('pct_chg')}%")

    # 保存到文件
    with open('eastmoney_quotes.json', 'w', encoding='utf-8') as f:
        json.dump(quotes, f, ensure_ascii=False, indent=2)
    print("\n数据已保存到 eastmoney_quotes.json")
