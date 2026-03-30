from datetime import datetime, timedelta
import pytz
import json
import os
from django.db import models
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from dvadmin.selection.models import StockBasic

# TradingView UDF 端点实现
class TradingViewViewSet(viewsets.GenericViewSet):
    """TradingView UDF 端点集合"""
    permission_classes = []  # 允许匿名访问
    
    # 移除固定的__init__数据加载，改为在history方法中动态加载
    
    @action(detail=False, methods=['get'], url_path='config')
    def config(self, request):
        """返回图表配置"""
        return Response({
            "supported_resolutions": ["5", "30", "1D", "1W", "1M", "3M", "1Y"],
            "supports_group_request": False,
            "supports_search": True,
            "supports_time": True,
            "supports_marks": False,
            "supports_timescale_marks": False
        })
    
    @action(detail=False, methods=['get'], url_path='symbols')
    def symbols(self, request):
        """返回单个符号信息"""
        symbol = request.query_params.get('symbol', '')
        
        name = symbol
        description = symbol
        
        symbol_upper = symbol.upper()
        if symbol_upper.endswith(".SH") or symbol_upper.endswith(".SS") or symbol.startswith("6"):
            exchange = "SSE"
        elif symbol_upper.endswith(".BJ") or symbol.startswith("4") or symbol.startswith("8"):
            exchange = "BSE"
        else:
            exchange = "SZSE"
        
        if symbol == "000001.SH":
            name = "上证指数"
            description = "上证指数"
            exchange = "SSE"
        else:
            try:
                # 尝试根据ts_code查找股票信息
                stock = StockBasic.objects.filter(ts_code=symbol).first()
                if stock:
                    name = stock.name
                    description = stock.name
                    ts_code_upper = (stock.ts_code or "").upper()
                    if ts_code_upper.endswith(".SH") or ts_code_upper.endswith(".SS"):
                        exchange = 'SSE'
                    elif ts_code_upper.endswith(".SZ"):
                        exchange = 'SZSE'
                    elif ts_code_upper.endswith(".BJ"):
                        exchange = 'BSE'
                    elif stock.symbol and stock.symbol.startswith('6'):
                        exchange = 'SSE'
                    elif stock.symbol and (stock.symbol.startswith('8') or stock.symbol.startswith('4')):
                        exchange = 'BSE'
                    else:
                        exchange = 'SZSE'
            except Exception:
                pass

        return Response({
            "name": name,
            "full_name": name,
            "description": description,
            "exchange": exchange,
            "listed_exchange": exchange,
            "type": "stock",
            "session": "0900-1131,1300-1501",
            "timezone": "Asia/Shanghai",
            "ticker": symbol,
            "minmov": 1,
            "pricescale": 100,
            "has_intraday": True,
            "has_daily": True,
            "has_weekly": True,
            "has_monthly": True,
            "has_quarterly": True,
            "has_yearly": True,
            "supported_resolutions": ["5","30", "1D", "1W", "1M", "3M", "1Y"],
            "volume_precision": 0,
            "data_status": "streaming",
            "daily_multipliers": ["1", "2"]
        })
    
    @action(detail=False, methods=['get'], url_path='history')
    def history(self, request):
        """返回历史 K 线数据"""
        # 获取请求参数
        from_time = request.query_params.get('from')
        to_time = request.query_params.get('to')
        resolution = request.query_params.get('resolution')
        
        # 根据resolution参数选择不同的mock数据文件
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        if resolution == '1D':
            mock_file_path = os.path.join(base_dir, 'history_601888_日线_all_zsshape.json')
        elif resolution == '30':
            mock_file_path = os.path.join(base_dir, 'history_601888_日线_all_zsshape.json')
        else:
            # 默认返回日线数据
            mock_file_path = os.path.join(base_dir, 'history_601888_日线_all_zsshape.json')
        
        # 加载对应的mock数据
        with open(mock_file_path, 'r', encoding='utf-8') as f:
            mock_data = json.load(f)
        
        # 获取mock数据中的最早时间点
        earliest_time = mock_data['t'][0]
        
        # 检查参数是否存在且有效
        try:
            # 情况1：同时有from和to参数
            if from_time and to_time:
                from_time = int(from_time)
                to_time = int(to_time)
                # 如果请求的时间范围完全早于mock数据中的最早时间，返回no_data
                if to_time < earliest_time:
                    return Response({"s": "no_data"})
            # 情况2：只有to参数
            elif to_time:
                to_time = int(to_time)
                # 如果to时间早于最早时间，返回no_data
                if to_time < earliest_time:
                    return Response({"s": "no_data"})
        except (ValueError, TypeError):
            # 参数无效时，继续返回完整数据
            pass
        
        # 返回对应分辨率的mock数据
        return Response(mock_data)
    
    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        """搜索符号"""
        query = request.query_params.get('query')
        try:
            limit = int(request.query_params.get('limit', 10))
        except (ValueError, TypeError):
            limit = 10
        
        # 构建查询条件
        if query:
            # 当有query参数时，按条件搜索，支持股票代码、股票名称、拼音首字母
            # 注意：某些数据库环境下icontains可能对大小写敏感，额外增加小写匹配以支持"PAYH"搜到"payh"
            stocks = StockBasic.objects.filter(
                models.Q(ts_code__icontains=query) | 
                models.Q(symbol__icontains=query) | 
                models.Q(name__icontains=query) |
                models.Q(cnspell__icontains=query) |
                models.Q(cnspell__contains=query.lower())
            ).order_by('ts_code')[:limit]
        else:
            # 当query为空时，根据limit参数返回数据
            stocks = StockBasic.objects.all().order_by('ts_code')[:limit]
        
        # 判断是否需要包含默认的上证指数
        include_sz_index = False
        if not query:
            include_sz_index = True
        else:
            q_lower = query.lower()
            # 搜索词包含在这些关键词中，或者这些关键词包含在搜索词中
            if (q_lower in "000001.sh" or q_lower in "上证指数" or q_lower in "szzs" 
                or "000001" in q_lower or "上证" in q_lower):
                include_sz_index = True

        # 转换为TradingView需要的格式
        result = []
        if include_sz_index:
            result.append({
                "symbol": "000001.SH",
                "full_name": "上证指数",
                "name": "上证指数",
                "description": "上证指数",
                "type": "index",
                "exchange": "SSE",
                "ticker": "000001.SH"
            })
        
        for stock in stocks:
            # 避免重复添加上证指数
            if stock.ts_code == "000001.SH":
                continue
            # 根据股票代码判断交易所
            ts_code_upper = (stock.ts_code or "").upper()
            if ts_code_upper.endswith('.SH') or ts_code_upper.endswith('.SS'):
                exchange = 'SSE'
            elif ts_code_upper.endswith('.SZ'):
                exchange = 'SZSE'
            elif ts_code_upper.endswith('.BJ'):
                exchange = 'BSE'
            elif stock.symbol and stock.symbol.startswith('6'):
                exchange = 'SSE'
            elif stock.symbol and (stock.symbol.startswith('8') or stock.symbol.startswith('4')):
                exchange = 'BSE'
            else:
                exchange = 'SZSE'
            
            result.append({
                "symbol": stock.ts_code,
                "full_name": stock.name,
                "name": stock.name,
                "description": stock.name,
                "type": "stock",
                "exchange": exchange,
                "ticker": stock.ts_code
            })
        
        return Response(result)
    
    @action(detail=False, methods=['get'], url_path='time')
    def time(self, request):
        """返回服务器时间"""
        return Response(int(datetime.now(pytz.UTC).timestamp()))
