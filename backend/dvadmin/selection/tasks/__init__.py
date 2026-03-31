# tasks package
from .eastmoney_spider import EastmoneySpider, fetch_all_a_stock_quotes, sync_stock_quotes_to_db

__all__ = ['EastmoneySpider', 'fetch_all_a_stock_quotes', 'sync_stock_quotes_to_db']
