"""chanlun.py

独立的缠论 history 接口：
- 不改动既有 TradingViewViewSet（保留原 mock 逻辑）
- 直接迁移 analysis_api.py 的完整逻辑（含 ZS_sig 的核心算法）
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path
from typing import Any

# 强制使用本地开发版 czsc
# 强制使用本地开发版 czsc (backend/czsc)
backend_dir = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(backend_dir / "czsc"))

os.environ["CZSC_USE_PYTHON"] = "1"
import czsc
import pandas as pd
from czsc import Freq
from sqlalchemy import create_engine, text

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from tushare2postgresql import convert_stock_code
from ZS_sig import get_zs_seq, find_B1, find_B2, find_B3, find_S1, find_S2, find_S3


def _dt_to_str(dt) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def _dt_to_ts(dt, is_daily: bool = False, freq: Freq | None = None) -> int | None:
    """将 datetime / 可解析字符串 转为秒级时间戳（int）。
    
    Args:
        dt: 日期时间对象或字符串
        is_daily: 是否为日线/周线/月线数据。日线数据不做时区转换，直接当作 UTC 0:00 处理，
                  避免前端显示时差一天的问题。
        freq: 频率枚举。如果是周线 (Freq.W)，会将周五的日期转换为周一，以匹配 TradingView 的周线约定。
    """
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return int(dt)
    try:
        ts = pd.Timestamp(dt)
        if ts is pd.NaT:
            return None
        
        # 周线特殊处理：数据库存的是周五，TradingView 显示周一为周线起点
        # 将周五日期转换为同一周的周一
        if freq == Freq.W:
            # ts.dayofweek: 0=周一, 1=周二, ..., 4=周五, 5=周六, 6=周日
            # 如果是周五(4)，往前推4天到周一；如果是其他日期，也推到该周周一
            days_since_monday = ts.dayofweek
            ts = ts - pd.Timedelta(days=days_since_monday)
        
        if is_daily:
            # 日线/周线/月线：直接取日期的 UTC 0:00 时间戳，不做时区转换
            # 这样前端按 UTC 解析时显示正确的日期
            return int(pd.Timestamp(ts.date()).timestamp())
        else:
            # 分钟线：假设为北京时间，转换为 UTC 时间戳
            if ts.tz is None:
                ts = ts.tz_localize("Asia/Shanghai")
            return int(ts.timestamp())
    except Exception:
        return None


def _normalize_ts_code(symbol: str) -> str:
    """将入参标准化为 ts_code（如 601888.SH / 000001.SZ）。

    约定：
    - 如果已经是 ts_code（包含 . 且以 .SH/.SZ 结尾），直接返回（会做 upper + 去空格）
    - 否则按 6 位股票代码走 convert_stock_code
    """
    s = str(symbol).strip().upper()
    if "." in s and (s.endswith(".SH") or s.endswith(".SZ")):
        return s
    return convert_stock_code(s)


def _json_safe(v: Any):
    """把 numpy 标量 / datetime / NaN/Inf 等转换成可 JSON 序列化的值（递归）。"""
    try:
        import numpy as np
    except Exception:
        np = None

    if v is None:
        return None

    # datetime/date
    if hasattr(v, "strftime") and not isinstance(v, (str, bytes)):
        return _dt_to_str(v)

    # numpy scalar -> python scalar
    if np is not None and isinstance(v, (getattr(np, "floating", ()), getattr(np, "integer", ()))):
        v = v.item()

    # float NaN/Inf -> None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None

    if isinstance(v, dict):
        return {str(k): _json_safe(val) for k, val in v.items()}

    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]

    return v


def _get_ts_freq(czsc_freq: Freq | str) -> str:
    """将 czsc 的频率映射到数据库 period 字段。"""
    freq_str = czsc_freq.value if isinstance(czsc_freq, Freq) else str(czsc_freq)
    freq_str = str(freq_str).strip()

    mapping = {
        "日线": "daily",
        "周线": "weekly",
        "月线": "monthly",
        "5分钟": "5min",
        "30分钟": "30min",
    }
    if freq_str in mapping:
        return mapping[freq_str]
    if freq_str.endswith("分钟"):
        return freq_str.replace("分钟", "min")
    return freq_str


def _parse_bool(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _resolution_to_freq(resolution: str) -> Freq | None:
    r = str(resolution).strip().upper()
    mapping = {
        "1": Freq.F1,
        "5": Freq.F5,
        "15": Freq.F15,
        "30": Freq.F30,
        "60": Freq.F60,
        "1D": Freq.D,
        "1W": Freq.W,
        "1M": Freq.M,
    }
    return mapping.get(r)


def get_analysis_data(code: str, freq_enum: Freq) -> dict:
    """输入 code(如 601888) + czsc.Freq，输出 README 定义的 JSON 结构 dict。"""

    db_host = os.getenv("DB_HOST", "192.168.1.207")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "datadriver")
    db_password = os.getenv("DB_PASSWORD", "datadriver")
    db_name = os.getenv("DB_NAME", "datadriver")

    engine = create_engine(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

    ts_code = _normalize_ts_code(code)
    db_period = _get_ts_freq(freq_enum)

    query = text(
        """
        SELECT trade_time as dt, open, high, low, close, vol, amount
        FROM stock_kline
        WHERE ts_code = :code AND period = :period
        ORDER BY trade_time ASC
        """
    )

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"code": ts_code, "period": db_period})

    if df.empty:
        return {"symbol": ts_code, "kline": [], "bi": [], "zs": [], "bs": []}

    # 与原版 main.py 保持一致的预处理
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt")
    df["symbol"] = ts_code
    df = df[["dt", "symbol", "open", "high", "low", "close", "vol", "amount"]].copy().reset_index(drop=True)

    # --- 这里新增：复刻 main.py 的数据清洗逻辑 ---
    # 1. 确保数值类型安全 (防止数据库返回 Decimal 或字符串混杂)
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols + ["vol", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # 2. 填充成交量空值
    if "vol" in df.columns:
        df["vol"] = df["vol"].fillna(0)
    if "amount" in df.columns:
        df["amount"] = df["amount"].fillna(0)

    # 3. 裁剪由于复权可能导致的头部无效 NaN 数据 (参考 main.py)
    # 找到第一个“价格字段全不为NaN”的行索引
    valid_mask = df[price_cols].notna().all(axis=1)
    if not valid_mask.any():
        # 如果全部都是 NaN，直接返回空
        return {"symbol": ts_code, "kline": [], "bi": [], "zs": [], "bs": []}

    first_valid_idx = df.index[valid_mask][0]
    if first_valid_idx != 0:
        df = df.loc[first_valid_idx:].copy().reset_index(drop=True)
    
    # 4. 剔除剩余的无效行 (价格为 NaN 的行)
    df = df.dropna(subset=["dt"] + price_cols).reset_index(drop=True)

    if df.empty:
        return {"symbol": ts_code, "kline": [], "bi": [], "zs": [], "bs": []}
    # ---------------------------------------------

    # czsc 计算
    raw_bars = czsc.format_standard_kline(df, freq=freq_enum)
    c = czsc.CZSC(raw_bars, max_bi_num=1000)

    zs_list = get_zs_seq(c.bi_list)

    # 与原版 main.py 保持一致的买卖点计算顺序
    b1_list = find_B1(c.bi_list, zs_list, c)
    b2_list = find_B2(c.bi_list, b1_list)
    b3_list = find_B3(c.bi_list, zs_list)
    s1_list = find_S1(c.bi_list, zs_list, c)
    s2_list = find_S2(c.bi_list, s1_list)
    s3_list = find_S3(c.bi_list, zs_list)
    bs_points = b1_list + b2_list + b3_list + s1_list + s2_list + s3_list

    # A. K线（只输出前端常用字段，避免把 cache 等内部字段带出去）
    kline_data = []
    for x in c.bars_raw:
        kline_data.append(
            {
                "dt": _dt_to_str(x.dt),
                "open": _json_safe(x.open),
                "close": _json_safe(x.close),
                "high": _json_safe(x.high),
                "low": _json_safe(x.low),
                "vol": _json_safe(getattr(x, "vol", None)),
                "amount": _json_safe(getattr(x, "amount", None)),
            }
        )

    # B. 笔（按 README 的 start/end 结构输出）
    bi_data = []
    for bi in c.bi_list:
        bi_data.append(
            {
                "start_dt": _dt_to_str(bi.fx_a.dt),
                "start_price": _json_safe(bi.fx_a.fx),
                "end_dt": _dt_to_str(bi.fx_b.dt),
                "end_price": _json_safe(bi.fx_b.fx),
                "direction": str(getattr(bi.direction, "name", bi.direction)),
            }
        )

    # C. 中枢（ZS 对象）
    formatted_zs = []
    for zs in zs_list:
        formatted_zs.append(
            {
                "start_dt": _dt_to_str(zs.sdt),
                "end_dt": _dt_to_str(zs.edt),
                "zg": _json_safe(float(zs.zg)),
                "zd": _json_safe(float(zs.zd)),
                "gg": _json_safe(float(zs.gg)),
                "dd": _json_safe(float(zs.dd)),
            }
        )

    # D. 买卖点
    formatted_bs = []
    for p in bs_points:
        formatted_bs.append(
            {
                "dt": _dt_to_str(p.get("dt")),
                "price": _json_safe(p.get("price")),
                "text": p.get("op_desc") or p.get("bs_type"),
                "desc": p.get("bs_type"),
                "op": getattr(p.get("op"), "name", str(p.get("op"))) if p.get("op") is not None else None,
            }
        )

    return {
        "symbol": ts_code,
        "kline": _json_safe(kline_data),
        "bi": _json_safe(bi_data),
        "zs": _json_safe(formatted_zs),
        "bs": _json_safe(formatted_bs),
    }


def get_analysis_json(code: str, freq_enum: Freq) -> str:
    import json

    data = get_analysis_data(code=code, freq_enum=freq_enum)
    # 已处理 NaN/Inf，严格 JSON
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def get_history_data(
    code: str,
    freq_enum: Freq,
    from_ts: int | None = None,
    to_ts: int | None = None,
    countback: int | None = None,
    first_data_request: bool = False,
) -> dict:
    """将缠论分析结果转换成 TradingView UDF /history 输出结构。

    说明：
    - 核心K线字段以数组形式输出：t/o/h/l/c/v（t 为秒级时间戳）
    - 叠加字段：bis（笔）、bi_zss（笔中枢）、mmds（买卖点）
    - 线段/中枢线段等（xds/zsds/xd_zss/zsd_zss/bcs）当前算法未提供，先返回空数组
    - 新增：_perf 字段包含各环节性能埋点数据
    """
    import time as _time
    
    # 性能埋点数据
    perf = {
        "total_start": _time.perf_counter(),
        "db_connect_ms": 0.0,
        "db_query_ms": 0.0,
        "data_preprocess_ms": 0.0,
        "czsc_format_ms": 0.0,
        "czsc_parse_ms": 0.0,
        "zs_calc_ms": 0.0,
        "b1_calc_ms": 0.0,
        "b2_calc_ms": 0.0,
        "b3_calc_ms": 0.0,
        "s1_calc_ms": 0.0,
        "s2_calc_ms": 0.0,
        "s3_calc_ms": 0.0,
        "output_build_ms": 0.0,
        "total_ms": 0.0,
        "kline_count": 0,
        "bi_count": 0,
        "zs_count": 0,
        "bs_count": 0,
    }
    
    # ========== 1. 数据库连接 ==========
    db_connect_start = _time.perf_counter()
    
    db_host = os.getenv("DB_HOST", "192.168.1.207")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "datadriver")
    db_password = os.getenv("DB_PASSWORD", "datadriver")
    db_name = os.getenv("DB_NAME", "datadriver")

    engine = create_engine(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

    ts_code = _normalize_ts_code(code)
    db_period = _get_ts_freq(freq_enum)
    
    perf["db_connect_ms"] = (_time.perf_counter() - db_connect_start) * 1000

    # ========== 2. 数据库查询 ==========
    db_query_start = _time.perf_counter()
    
    query = text(
        """
        SELECT trade_time as dt, open, high, low, close, vol, amount
        FROM stock_kline
        WHERE ts_code = :code AND period = :period
        ORDER BY trade_time ASC
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"code": ts_code, "period": db_period})
    
    perf["db_query_ms"] = (_time.perf_counter() - db_query_start) * 1000
    perf["kline_count"] = len(df)

    if df.empty:
        perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
        return {"s": "no_data", "_perf": perf}

    # ========== 3. 数据预处理 ==========
    preprocess_start = _time.perf_counter()
    
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt")
    df["symbol"] = ts_code
    df = df[["dt", "symbol", "open", "high", "low", "close", "vol", "amount"]].copy().reset_index(drop=True)

    # --- 这里新增：复刻 main.py 的数据清洗逻辑 ---
    # 1. 确保数值类型安全 (防止数据库返回 Decimal 或字符串混杂)
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols + ["vol", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # 2. 填充成交量空值
    if "vol" in df.columns:
        df["vol"] = df["vol"].fillna(0)
    if "amount" in df.columns:
        df["amount"] = df["amount"].fillna(0)

    # 3. 裁剪由于复权可能导致的头部无效 NaN 数据 (参考 main.py)
    # 找到第一个“价格字段全不为NaN”的行索引
    valid_mask = df[price_cols].notna().all(axis=1)
    if not valid_mask.any():
        perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
        return {"s": "no_data", "_perf": perf}

    first_valid_idx = df.index[valid_mask][0]
    if first_valid_idx != 0:
        df = df.loc[first_valid_idx:].copy().reset_index(drop=True)
    
    # 4. 剔除剩余的无效行 (价格为 NaN 的行)
    df = df.dropna(subset=["dt"] + price_cols).reset_index(drop=True)

    if df.empty:
        perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
        return {"s": "no_data", "_perf": perf}
    # ---------------------------------------------
    
    perf["data_preprocess_ms"] = (_time.perf_counter() - preprocess_start) * 1000

    # ========== 4. CZSC 格式化 ==========
    czsc_format_start = _time.perf_counter()
    raw_bars = czsc.format_standard_kline(df, freq=freq_enum)
    perf["czsc_format_ms"] = (_time.perf_counter() - czsc_format_start) * 1000
    
    # ========== 5. CZSC 解析（分型 + 笔） ==========
    czsc_parse_start = _time.perf_counter()
    c = czsc.CZSC(raw_bars, max_bi_num=1000)
    perf["czsc_parse_ms"] = (_time.perf_counter() - czsc_parse_start) * 1000
    perf["bi_count"] = len(c.bi_list)

    # 判断是否为日线级别（日线/周线/月线），用于时间戳转换
    is_daily = freq_enum in (Freq.D, Freq.W, Freq.M)

    # --- K线：对象列表 -> 等长数组（并支持 from/to/countback 裁剪） ---
    bars = list(c.bars_raw)
    # 约定：firstDataRequest=true 时"第一次返回全量"，忽略 from/to/countback
    if first_data_request:
        from_ts = None
        to_ts = None
        countback = None

    if (from_ts is not None or to_ts is not None):
        f = -10**18 if from_ts is None else int(from_ts)
        t = 10**18 if to_ts is None else int(to_ts)
        bars = [b for b in bars if (_dt_to_ts(b.dt, is_daily, freq_enum) is not None and f <= _dt_to_ts(b.dt, is_daily, freq_enum) <= t)]

    if countback is not None and countback > 0 and len(bars) > countback:
        bars = bars[-int(countback) :]

    if not bars:
        perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
        return {"s": "no_data", "_perf": perf}

    t_arr, o_arr, h_arr, l_arr, c_arr, v_arr = [], [], [], [], [], []
    for b in bars:
        ts = _dt_to_ts(b.dt, is_daily, freq_enum)
        if ts is None:
            continue
        t_arr.append(int(ts))
        o_arr.append(_json_safe(b.open))
        h_arr.append(_json_safe(b.high))
        l_arr.append(_json_safe(b.low))
        c_arr.append(_json_safe(b.close))
        v_arr.append(_json_safe(getattr(b, "vol", None)))

    if not t_arr:
        perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
        return {"s": "no_data", "_perf": perf}

    t_min, t_max = t_arr[0], t_arr[-1]

    # --- 笔（bis）：start/end 结构 -> points 结构 ---
    bis = []
    for bi in c.bi_list:
        s_ts = _dt_to_ts(bi.fx_a.dt, is_daily, freq_enum)
        e_ts = _dt_to_ts(bi.fx_b.dt, is_daily, freq_enum)
        if s_ts is None or e_ts is None:
            continue
        # 只保留与当前K线区间有交集的笔
        if e_ts < t_min or s_ts > t_max:
            continue
        bis.append(
            {
                "points": [
                    {"time": int(s_ts), "price": _json_safe(bi.fx_a.fx)},
                    {"time": int(e_ts), "price": _json_safe(bi.fx_b.fx)},
                ],
                "linestyle": "0",
            }
        )

    # ========== 6. 中枢计算 ==========
    zs_calc_start = _time.perf_counter()
    zs_list = get_zs_seq(c.bi_list)
    perf["zs_calc_ms"] = (_time.perf_counter() - zs_calc_start) * 1000
    perf["zs_count"] = len(zs_list)
    
    bi_zss = []
    for zs in zs_list:
        s_ts = _dt_to_ts(zs.sdt, is_daily, freq_enum)
        e_ts = _dt_to_ts(zs.edt, is_daily, freq_enum)
        if s_ts is None or e_ts is None:
            continue
        if e_ts < t_min or s_ts > t_max:
            continue
        zg = _json_safe(float(zs.zg))
        zd = _json_safe(float(zs.zd))
        s_ts_i, e_ts_i = int(s_ts), int(e_ts)
        if e_ts_i <= s_ts_i:
            continue

        # 用两个对角点表达矩形：左上(s_ts, zg) 与 右下(e_ts, zd)
        bi_zss.append(
            {
                "points": [{"time": s_ts_i, "price": zg}, {"time": e_ts_i, "price": zd}],
                "linestyle": "0",
            }
        )

    # ========== 7. 六类买卖点计算 ==========
    # B1
    b1_start = _time.perf_counter()
    b1_list = find_B1(c.bi_list, zs_list, c)
    perf["b1_calc_ms"] = (_time.perf_counter() - b1_start) * 1000
    
    # B2
    b2_start = _time.perf_counter()
    b2_list = find_B2(c.bi_list, b1_list)
    perf["b2_calc_ms"] = (_time.perf_counter() - b2_start) * 1000
    
    # B3
    b3_start = _time.perf_counter()
    b3_list = find_B3(c.bi_list, zs_list)
    perf["b3_calc_ms"] = (_time.perf_counter() - b3_start) * 1000
    
    # S1
    s1_start = _time.perf_counter()
    s1_list = find_S1(c.bi_list, zs_list, c)
    perf["s1_calc_ms"] = (_time.perf_counter() - s1_start) * 1000
    
    # S2
    s2_start = _time.perf_counter()
    s2_list = find_S2(c.bi_list, s1_list)
    perf["s2_calc_ms"] = (_time.perf_counter() - s2_start) * 1000
    
    # S3
    s3_start = _time.perf_counter()
    s3_list = find_S3(c.bi_list, zs_list)
    perf["s3_calc_ms"] = (_time.perf_counter() - s3_start) * 1000
    
    bs_points = b1_list + b2_list + b3_list + s1_list + s2_list + s3_list
    perf["bs_count"] = len(bs_points)

    # ========== 调试打印：所有买卖点 ==========
    print(f"\n{'='*80}")
    print(f"[DEBUG] 买卖点计算结果 ({ts_code}, {freq_enum.value}):")
    print(f"  - B1: {len(b1_list)} 个")
    for p in b1_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"  - B2: {len(b2_list)} 个")
    for p in b2_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"  - B3: {len(b3_list)} 个")
    for p in b3_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"  - S1: {len(s1_list)} 个")
    for p in s1_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"  - S2: {len(s2_list)} 个")
    for p in s2_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"  - S3: {len(s3_list)} 个")
    for p in s3_list:
        print(f"      {p.get('dt')} @ {p.get('price'):.2f}")
    print(f"{'='*80}\n")

    # ========== 8. 构建输出 ==========
    output_start = _time.perf_counter()
    
    mmds = []
    for p in bs_points:
        ts = _dt_to_ts(p.get("dt"), is_daily, freq_enum)
        price = p.get("price")
        if ts is None or price is None:
            continue
        # 注意：不再按时间范围过滤买卖点，返回所有计算出的点，让前端决定显示
        # if ts < t_min or ts > t_max:
        #     continue
        text_val = p.get("op_desc") or p.get("bs_type") or "signal"
        # 与文档示例风格更接近（"笔:3S"）
        if isinstance(p.get("bs_type"), str) and p.get("bs_type"):
            text_val = f"笔:{p.get('bs_type')}"
        mmds.append({"points": {"time": int(ts), "price": _json_safe(price)}, "text": str(text_val)})
    
    # ========== 调试打印：输出的 mmds ==========
    print(f"\n{'='*80}")
    print(f"[DEBUG] 返回给前端的 mmds ({len(mmds)} 个):")
    for m in mmds:
        print(f"      time={m['points']['time']}, price={m['points']['price']}, text={m['text']}")
    print(f"{'='*80}\n")

    perf["output_build_ms"] = (_time.perf_counter() - output_start) * 1000
    perf["total_ms"] = (_time.perf_counter() - perf["total_start"]) * 1000
    
    # 移除 total_start（它是 float，不是最终输出）
    del perf["total_start"]

    return {
        "s": "ok",
        "t": t_arr,
        "o": o_arr,
        "h": h_arr,
        "l": l_arr,
        "c": c_arr,
        "v": v_arr,
        "fxs": [],
        "bis": bis,
        "xds": [],
        "zsds": [],
        "bi_zss": bi_zss,
        "xd_zss": [],
        "zsd_zss": [],
        "bcs": [],
        "mmds": mmds,
        "update": True,
        "chart_color": {},
        "update_time": int(time.time()),
        "last_k_time": int(t_arr[-1]),
        "_perf": perf,  # 性能埋点数据
    }


def get_history_json(
    code: str,
    freq_enum: Freq,
    from_ts: int | None = None,
    to_ts: int | None = None,
    countback: int | None = None,
    first_data_request: bool = False,
) -> str:
    import json

    data = get_history_data(
        code=code,
        freq_enum=freq_enum,
        from_ts=from_ts,
        to_ts=to_ts,
        countback=countback,
        first_data_request=first_data_request,
    )
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


class ChanlunTradingViewViewSet(viewsets.GenericViewSet):
    """独立的缠论 history 接口（不修改原 TradingViewViewSet）。"""

    permission_classes = []  # 允许匿名访问

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        params = request.query_params

        symbol = (params.get("symbol") or "").strip().upper()
        resolution = params.get("resolution") or ""
        from_ts = params.get("from")
        to_ts = params.get("to")
        countback = params.get("countback")
        first_data_request = _parse_bool(params.get("firstDataRequest"))

        if not symbol or not resolution:
            return Response({"s": "no_data"})

        freq_enum = _resolution_to_freq(resolution)
        if not freq_enum:
            return Response({"s": "no_data"})

        try:
            from_ts_i = int(from_ts) if from_ts is not None else None
            to_ts_i = int(to_ts) if to_ts is not None else None
            countback_i = int(countback) if countback is not None else None
        except Exception:
            from_ts_i = None
            to_ts_i = None
            countback_i = None

        data = get_history_data(
            code=symbol,
            freq_enum=freq_enum,
            from_ts=from_ts_i,
            to_ts=to_ts_i,
            countback=countback_i,
            first_data_request=first_data_request,
        )
        return Response(data)
