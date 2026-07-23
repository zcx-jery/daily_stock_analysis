# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 备用数据源 1 (Priority 2)
===================================

数据来源：Tushare Pro API（挖地兔）
特点：需要 Token、有请求配额限制
优点：数据质量高、接口稳定

流控策略：
1. 实现"每分钟调用计数器"
2. 超过免费配额（80次/分）时，强制休眠到下一分钟
3. 使用 tenacity 实现指数退避重试
"""

import json as _json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS,is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code, _is_hk_market
from .realtime_types import UnifiedRealtimeQuote, ChipDistribution
from src.config import get_config
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# ETF code prefixes by exchange
# Shanghai: 51xxxx, 52xxxx, 56xxxx, 58xxxx
# Shenzhen: 15xxxx, 16xxxx, 18xxxx
_ETF_SH_PREFIXES = ('51', '52', '56', '58')
_ETF_SZ_PREFIXES = ('15', '16', '18')
_ETF_ALL_PREFIXES = _ETF_SH_PREFIXES + _ETF_SZ_PREFIXES


def _is_etf_code(stock_code: str) -> bool:
    """
    Check if the code is an ETF fund code.

    ETF code ranges:
    - Shanghai ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - Shenzhen ETF: 15xxxx, 16xxxx, 18xxxx
    """
    code = stock_code.strip().split('.')[0]
    return code.startswith(_ETF_ALL_PREFIXES) and len(code) == 6


def _is_us_code(stock_code: str) -> bool:
    """
    判断代码是否为美股
    
    美股代码规则：
    - 1-5个大写字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class _TushareHttpClient:
    """Lightweight Tushare Pro client that does not require the tushare SDK."""

    def __init__(self, token: str, timeout: int = 30, api_url: str = "http://api.tushare.pro") -> None:
        self._token = token
        self._timeout = timeout
        self._api_url = api_url

    def query(self, api_name: str, fields: str = "", **kwargs) -> pd.DataFrame:
        req_params = {
            "api_name": api_name,
            "token": self._token,
            "params": kwargs,
            "fields": fields,
        }
        res = requests.post(self._api_url, json=req_params, timeout=self._timeout)
        if res.status_code != 200:
            raise Exception(f"Tushare API HTTP {res.status_code}")

        result = _json.loads(res.text)
        if result.get("code") != 0:
            raise Exception(result.get("msg") or f"Tushare API error code {result.get('code')}")

        data = result.get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        return pd.DataFrame(items, columns=columns)

    def __getattr__(self, api_name: str):
        if api_name.startswith("_"):
            raise AttributeError(api_name)

        def caller(**kwargs) -> pd.DataFrame:
            return self.query(api_name, **kwargs)

        return caller


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro 数据源实现
    
    优先级：2
    数据来源：Tushare Pro API
    
    关键策略：
    - 每分钟调用计数器，防止超出配额
    - 超过 80 次/分钟时强制等待
    - 失败后指数退避重试
    
    配额说明（Tushare 免费用户）：
    - 每分钟最多 80 次请求
    - 每天最多 500 次请求
    """
    
    name = "TushareFetcher"
    priority = int(os.getenv("TUSHARE_PRIORITY", "2"))  # 默认优先级，会在 __init__ 中根据配置动态调整

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        初始化 TushareFetcher

        Args:
            rate_limit_per_minute: 每分钟最大请求数（默认80，Tushare免费配额）
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self._call_count = 0  # 当前分钟内的调用次数
        self._minute_start: Optional[float] = None  # 当前计数周期开始时间
        self._api: Optional[object] = None  # Tushare API 实例
        self.date_list: Optional[List[str]] = None  # 交易日列表缓存（倒序，最新日期在前）
        self._date_list_end: Optional[str] = None  # 缓存对应的截止日期，用于跨日刷新

        # 尝试初始化 API
        self._init_api()

        # 根据 API 初始化结果动态调整优先级
        self.priority = self._determine_priority()
    
    def _init_api(self) -> None:
        """
        初始化 Tushare API

        如果 Token 未配置，此数据源将不可用。
        这里直接使用内置 HTTP client，避免运行时强依赖 tushare SDK，
        从而减少 Docker / PyInstaller / 多虚拟环境场景下因缺包导致的初始化失败。
        """
        config = get_config()

        if not config.tushare_token:
            logger.warning("Tushare Token 未配置，此数据源不可用")
            return

        try:
            self._api = self._build_api_client(config.tushare_token)
            logger.info("Tushare API 初始化成功")
        except Exception as e:
            logger.error(f"Tushare API 初始化失败: {e}")
            self._api = None

    def _build_api_client(self, token: str) -> _TushareHttpClient:
        """
        Build a lightweight Tushare Pro client over direct HTTP requests.

        The project already normalizes all Pro calls through the same request
        contract, so we do not need the official tushare SDK during runtime.
        """
        client = _TushareHttpClient(token=token)
        logger.debug("Tushare API client configured for direct HTTP calls")
        return client

    def _determine_priority(self) -> int:
        """
        根据 Token 配置和 API 初始化状态确定优先级

        策略：
        - Token 配置且 API 初始化成功：优先级 -1（绝对最高，优于 efinance）
        - 其他情况：优先级 2（默认）

        Returns:
            优先级数字（0=最高，数字越大优先级越低）
        """
        config = get_config()

        if config.tushare_token and self._api is not None:
            # Token 配置且 API 初始化成功，提升为最高优先级
            logger.info("检测到 TUSHARE_TOKEN 且 API 初始化成功，Tushare 数据源优先级提升为最高 (Priority -1)")
            return -1

        # Token 未配置或 API 初始化失败，保持默认优先级
        return 2

    def is_available(self) -> bool:
        """
        检查数据源是否可用

        Returns:
            True 表示可用，False 表示不可用
        """
        return self._api is not None

    def _check_rate_limit(self) -> None:
        """
        检查并执行速率限制
        
        流控策略：
        1. 检查是否进入新的一分钟
        2. 如果是，重置计数器
        3. 如果当前分钟调用次数超过限制，强制休眠
        """
        current_time = time.time()
        
        # 检查是否需要重置计数器（新的一分钟）
        if self._minute_start is None:
            self._minute_start = current_time
            self._call_count = 0
        elif current_time - self._minute_start >= 60:
            # 已经过了一分钟，重置计数器
            self._minute_start = current_time
            self._call_count = 0
            logger.debug("速率限制计数器已重置")
        
        # 检查是否超过配额
        if self._call_count >= self.rate_limit_per_minute:
            # 计算需要等待的时间（到下一分钟）
            elapsed = current_time - self._minute_start
            sleep_time = max(0, 60 - elapsed) + 1  # +1 秒缓冲
            
            logger.warning(
                f"Tushare 达到速率限制 ({self._call_count}/{self.rate_limit_per_minute} 次/分钟)，"
                f"等待 {sleep_time:.1f} 秒..."
            )
            
            time.sleep(sleep_time)
            
            # 重置计数器
            self._minute_start = time.time()
            self._call_count = 0
        
        # 增加调用计数
        self._call_count += 1
        logger.debug(f"Tushare 当前分钟调用次数: {self._call_count}/{self.rate_limit_per_minute}")

    def _call_api_with_rate_limit(self, method_name: str, **kwargs) -> pd.DataFrame:
        """统一通过速率限制包装 Tushare API 调用。"""
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")

        self._check_rate_limit()
        method = getattr(self._api, method_name)
        return method(**kwargs)

    @staticmethod
    def _format_tushare_date(value: Optional[str]) -> Optional[str]:
        """Normalize a user-facing date into Tushare's YYYYMMDD format."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text.replace("-", "").replace("/", "")

    @staticmethod
    def _format_display_trade_date(value: Any) -> Optional[str]:
        """Normalize Tushare trade_date values to YYYY-MM-DD for downstream APIs."""
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if not text:
            return None
        compact = text.replace("-", "").replace("/", "")
        if len(compact) == 8 and compact.isdigit():
            return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        return text

    @staticmethod
    def _safe_v13_value(value: Any) -> Any:
        """Convert pandas NaN values into JSON-safe None values."""
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    @classmethod
    def _safe_v13_float(cls, value: Any) -> Optional[float]:
        value = cls._safe_v13_value(value)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _safe_v13_money_yuan(cls, value: Any) -> Optional[float]:
        numeric = cls._safe_v13_float(value)
        if numeric is None:
            return None
        return numeric * 10000.0

    @classmethod
    def _safe_v13_int(cls, value: Any) -> Optional[int]:
        value = cls._safe_v13_value(value)
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _safe_v13_str(cls, value: Any) -> Optional[str]:
        value = cls._safe_v13_value(value)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _compute_v13_cyq_snapshot(
        cls,
        distribution_df: pd.DataFrame,
        current_price: float,
    ) -> Optional[Dict[str, float]]:
        price_series = pd.to_numeric(distribution_df.get("price"), errors="coerce")
        percent_series = pd.to_numeric(distribution_df.get("percent"), errors="coerce")
        if price_series is None or percent_series is None:
            return None

        normalized = pd.DataFrame({"price": price_series, "percent": percent_series}).dropna()
        normalized = normalized[(normalized["price"] > 0) & (normalized["percent"] > 0)]
        if normalized.empty:
            return None

        total_percent = float(normalized["percent"].sum())
        if total_percent <= 0:
            return None

        normalized = normalized.sort_values(by="price", ascending=True).reset_index(drop=True)
        normalized["norm_percent"] = normalized["percent"] / total_percent * 100.0
        normalized["cumsum"] = normalized["norm_percent"].cumsum()

        def percentile_price(target_pct: float) -> float:
            idx = int(normalized["cumsum"].searchsorted(target_pct, side="left"))
            idx = min(max(idx, 0), len(normalized) - 1)
            return float(normalized.loc[idx, "price"])

        winner_rate = float(normalized.loc[normalized["price"] <= current_price, "norm_percent"].sum()) / 100.0
        avg_cost = float((normalized["price"] * normalized["norm_percent"]).sum() / normalized["norm_percent"].sum())
        cost_90_low = percentile_price(5.0)
        cost_90_high = percentile_price(95.0)
        cost_70_low = percentile_price(15.0)
        cost_70_high = percentile_price(85.0)

        def concentration(low: float, high: float) -> float:
            denominator = low + high
            if denominator <= 0:
                return 0.0
            return (high - low) / denominator

        return {
            "profit_ratio": round(winner_rate, 4),
            "avg_cost": round(avg_cost, 4),
            "cost_90_low": round(cost_90_low, 4),
            "cost_90_high": round(cost_90_high, 4),
            "concentration_90": round(concentration(cost_90_low, cost_90_high), 4),
            "cost_70_low": round(cost_70_low, 4),
            "cost_70_high": round(cost_70_high, 4),
            "concentration_70": round(concentration(cost_70_low, cost_70_high), 4),
            "distribution_points": float(len(normalized.index)),
        }

    @classmethod
    def _parse_ths_concepts(cls, value: Any) -> List[str]:
        """Parse ths_hot concept labels, preserving a stable list output."""
        value = cls._safe_v13_value(value)
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = _json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [part.strip() for part in re.split(r"[,，、]", text) if part.strip()]

    def _v13_data_as_of(self) -> str:
        return self._get_china_now().isoformat()

    @staticmethod
    def _v13_payload(
        *,
        source: str,
        trade_date: Optional[str],
        rows: Optional[List[Dict[str, Any]]] = None,
        status: str = "ok",
        data_as_of: Optional[str] = None,
        degraded_reasons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        reasons = degraded_reasons or []
        return {
            "source": source,
            "status": status,
            "trade_date": trade_date,
            "data_as_of": data_as_of,
            "is_degraded": status != "ok" or bool(reasons),
            "degraded_reasons": reasons,
            "rows": rows or [],
        }

    @staticmethod
    def _is_tushare_permission_error(reason: Any) -> bool:
        text = str(reason or "").strip().lower()
        if not text:
            return False
        patterns = (
            "permission denied",
            "no permission",
            "not have permission",
            "without permission",
            "forbidden",
            "unauthorized",
            "not authorized",
            "privilege",
            "invalid token",
            "token invalid",
            "积分",
            "权限",
            "无权限",
            "没有权限",
            "权限不足",
            "访问权限",
            "未开通",
            "抱歉",
        )
        return any(pattern in text for pattern in patterns)

    def _v13_payload_with_stale_check(
        self,
        *,
        source: str,
        trade_date: Optional[str],
        rows: Optional[List[Dict[str, Any]]] = None,
        status: str = "ok",
        data_as_of: Optional[str] = None,
        degraded_reasons: Optional[List[str]] = None,
        expected_trade_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self._v13_payload(
            source=source,
            trade_date=trade_date,
            rows=rows,
            status=status,
            data_as_of=data_as_of,
            degraded_reasons=degraded_reasons,
        )
        expected_date = self._format_display_trade_date(expected_trade_date)
        payload_rows = payload.get("rows")
        if status != "ok" or not expected_date or not isinstance(payload_rows, list) or not payload_rows:
            return payload

        latest_row_date: Optional[str] = None
        for row in payload_rows:
            if not isinstance(row, dict):
                continue
            row_date = self._format_display_trade_date(row.get("trade_date"))
            if row_date and (latest_row_date is None or row_date > latest_row_date):
                latest_row_date = row_date

        if latest_row_date and latest_row_date < expected_date:
            reasons = list(payload.get("degraded_reasons") or [])
            reasons.append(f"stale_result:{latest_row_date}<expected:{expected_date}")
            payload["status"] = "stale"
            payload["is_degraded"] = True
            payload["degraded_reasons"] = reasons
        return payload

    def _v13_unavailable_payload(self, *, source: str, trade_date: Optional[str], reason: str) -> Dict[str, Any]:
        status = "permission_denied" if self._is_tushare_permission_error(reason) else "unavailable"
        logger.warning("[Tushare V1.3] %s unavailable: %s", source, reason)
        return self._v13_payload(
            source=source,
            trade_date=trade_date,
            rows=[],
            status=status,
            data_as_of=self._v13_data_as_of(),
            degraded_reasons=[reason],
        )

    @staticmethod
    def _compact_date_days_ago(end_date: str, days: int) -> str:
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        return (end_dt - timedelta(days=max(1, days))).strftime("%Y%m%d")

    @classmethod
    def _first_payload_row(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if isinstance(rows, list) and rows:
            first = rows[0]
            return first if isinstance(first, dict) else {}
        return {}

    @classmethod
    def _payload_has_rows(cls, payload: Dict[str, Any]) -> bool:
        rows = payload.get("rows") if isinstance(payload, dict) else None
        return isinstance(rows, list) and len(rows) > 0

    @classmethod
    def _wan_yuan_to_yuan(cls, value: Any) -> Optional[float]:
        numeric = cls._safe_v13_float(value)
        if numeric is None:
            return None
        return numeric * 10000.0

    @classmethod
    def _append_payload_meta(cls, result: Dict[str, Any], payload: Dict[str, Any]) -> None:
        source = str(payload.get("source") or "tushare")
        status = str(payload.get("status") or "partial")
        result.setdefault("source_chain", []).append(
            {
                "provider": source,
                "result": status,
                "duration_ms": 0,
            }
        )
        for reason in payload.get("degraded_reasons", []) or []:
            if reason:
                result.setdefault("errors", []).append(f"{source}:{reason}")

    def get_daily_basic_metrics(
        self,
        stock_code: str,
        trade_date: Optional[str] = None,
        lookback_days: int = 10,
    ) -> Dict[str, Any]:
        """
        获取首页单票分析需要的每日估值与交易指标。

        Tushare 接口：daily_basic。金额字段保留 Tushare 原始“万元”口径，
        通过字段名显式标注，避免与实时行情的元口径混用。
        """
        source = "tushare.daily_basic"
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(
                source=source,
                trade_date=display_trade_date,
                reason="api_not_initialized",
            )

        end_date = self._format_tushare_date(trade_date) or self._get_china_now().strftime("%Y%m%d")
        start_date = self._compact_date_days_ago(end_date, max(lookback_days, 1) * 3)
        params: Dict[str, Any] = {
            "ts_code": self._convert_stock_code(stock_code),
            "start_date": start_date,
            "end_date": end_date,
            "fields": (
                "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
                "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,"
                "free_share,total_mv,circ_mv"
            ),
        }

        try:
            df = self._call_api_with_rate_limit("daily_basic", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        work_df = df.copy()
        if "trade_date" in work_df.columns:
            work_df = work_df.sort_values(by="trade_date", ascending=False)
        row = work_df.iloc[0]
        row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
        result_row = {
            "ts_code": self._safe_v13_str(row.get("ts_code")),
            "trade_date": row_trade_date,
            "close": self._safe_v13_float(row.get("close")),
            "turnover_rate": self._safe_v13_float(row.get("turnover_rate")),
            "turnover_rate_f": self._safe_v13_float(row.get("turnover_rate_f")),
            "volume_ratio": self._safe_v13_float(row.get("volume_ratio")),
            "pe_ratio": self._safe_v13_float(row.get("pe")),
            "pe_ttm": self._safe_v13_float(row.get("pe_ttm")),
            "pb_ratio": self._safe_v13_float(row.get("pb")),
            "ps": self._safe_v13_float(row.get("ps")),
            "ps_ttm": self._safe_v13_float(row.get("ps_ttm")),
            "dividend_yield_pct": self._safe_v13_float(row.get("dv_ttm")),
            "dividend_yield_static_pct": self._safe_v13_float(row.get("dv_ratio")),
            "total_share_wan": self._safe_v13_float(row.get("total_share")),
            "float_share_wan": self._safe_v13_float(row.get("float_share")),
            "free_share_wan": self._safe_v13_float(row.get("free_share")),
            "total_mv_wan": self._safe_v13_float(row.get("total_mv")),
            "circ_mv_wan": self._safe_v13_float(row.get("circ_mv")),
            "data_source": source,
            "data_as_of": data_as_of,
            "is_degraded": False,
        }
        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=row_trade_date,
            rows=[result_row],
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_financial_indicator_summary(
        self,
        stock_code: str,
        periods: int = 4,
    ) -> Dict[str, Any]:
        """获取首页分析需要的 Tushare 财务指标摘要。"""
        source = "tushare.fina_indicator"
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "ts_code": self._convert_stock_code(stock_code),
            "fields": (
                "ts_code,ann_date,end_date,eps,dt_eps,bps,ocfps,roe,roe_dt,"
                "grossprofit_margin,netprofit_margin,roa,roic,or_yoy,netprofit_yoy,"
                "dt_netprofit_yoy,ocf_yoy"
            ),
        }
        try:
            df = self._call_api_with_rate_limit("fina_indicator", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=None,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        work_df = df.copy()
        sort_cols = [col for col in ("end_date", "ann_date") if col in work_df.columns]
        if sort_cols:
            work_df = work_df.sort_values(by=sort_cols, ascending=False)

        rows: List[Dict[str, Any]] = []
        for _, row in work_df.head(max(1, periods)).iterrows():
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "ann_date": self._format_display_trade_date(row.get("ann_date")),
                    "report_period": self._format_display_trade_date(row.get("end_date")),
                    "eps": self._safe_v13_float(row.get("eps")),
                    "dt_eps": self._safe_v13_float(row.get("dt_eps")),
                    "bps": self._safe_v13_float(row.get("bps")),
                    "ocfps": self._safe_v13_float(row.get("ocfps")),
                    "roe": self._safe_v13_float(row.get("roe")),
                    "roe_dt": self._safe_v13_float(row.get("roe_dt")),
                    "gross_margin": self._safe_v13_float(row.get("grossprofit_margin")),
                    "net_profit_margin": self._safe_v13_float(row.get("netprofit_margin")),
                    "roa": self._safe_v13_float(row.get("roa")),
                    "roic": self._safe_v13_float(row.get("roic")),
                    "revenue_yoy": self._safe_v13_float(row.get("or_yoy")),
                    "net_profit_yoy": self._safe_v13_float(row.get("netprofit_yoy")),
                    "deducted_net_profit_yoy": self._safe_v13_float(row.get("dt_netprofit_yoy")),
                    "operating_cash_flow_yoy": self._safe_v13_float(row.get("ocf_yoy")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=None, rows=rows, data_as_of=data_as_of)

    def get_dividend_summary(
        self,
        stock_code: str,
        years: int = 5,
    ) -> Dict[str, Any]:
        """获取现金分红摘要，统一按每股税前现金分红口径输出。"""
        source = "tushare.dividend"
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason="api_not_initialized")

        try:
            df = self._call_api_with_rate_limit(
                "dividend",
                ts_code=self._convert_stock_code(stock_code),
                fields=(
                    "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,"
                    "cash_div,cash_div_tax,record_date,ex_date,div_listdate,imp_ann_date,"
                    "base_date,base_share"
                ),
            )
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=None,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        now_date = self._get_china_now().date()
        cutoff_date = now_date - timedelta(days=max(1, years) * 366)
        events: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            event_date_text = (
                self._format_display_trade_date(row.get("ex_date"))
                or self._format_display_trade_date(row.get("record_date"))
                or self._format_display_trade_date(row.get("ann_date"))
            )
            event_dt = None
            if event_date_text:
                try:
                    event_dt = datetime.strptime(event_date_text, "%Y-%m-%d").date()
                except ValueError:
                    event_dt = None
            if event_dt is not None and (event_dt > now_date or event_dt < cutoff_date):
                continue

            per_10_cash = self._safe_v13_float(row.get("cash_div_tax"))
            if per_10_cash is None:
                per_10_cash = self._safe_v13_float(row.get("cash_div"))
            cash_per_share = round(per_10_cash / 10.0, 6) if per_10_cash is not None else None
            event = {
                "ts_code": self._safe_v13_str(row.get("ts_code")),
                "report_period": self._format_display_trade_date(row.get("end_date")),
                "ann_date": self._format_display_trade_date(row.get("ann_date")),
                "record_date": self._format_display_trade_date(row.get("record_date")),
                "ex_dividend_date": self._format_display_trade_date(row.get("ex_date")),
                "event_date": event_date_text,
                "dividend_process": self._safe_v13_str(row.get("div_proc")),
                "cash_dividend_per_10_share": per_10_cash,
                "cash_dividend_per_share": cash_per_share,
                "is_pre_tax": row.get("cash_div_tax") is not None,
                "data_source": source,
                "data_as_of": data_as_of,
                "is_degraded": cash_per_share is None,
            }
            if cash_per_share is not None:
                events.append(event)

        events.sort(key=lambda item: item.get("event_date") or "", reverse=True)
        ttm_start = now_date - timedelta(days=365)
        ttm_events = []
        for item in events:
            event_date_text = item.get("event_date")
            if not event_date_text:
                continue
            try:
                event_dt = datetime.strptime(str(event_date_text), "%Y-%m-%d").date()
            except ValueError:
                continue
            if ttm_start <= event_dt <= now_date:
                ttm_events.append(item)

        payload = self._v13_payload(
            source=source,
            trade_date=None,
            rows=events[:10],
            status="ok" if events else "partial",
            data_as_of=data_as_of,
            degraded_reasons=[] if events else ["no_cash_dividend_events"],
        )
        payload["summary"] = {
            "events": events[:5],
            "ttm_event_count": len(ttm_events),
            "ttm_cash_dividend_per_share": (
                round(sum(float(item.get("cash_dividend_per_share") or 0.0) for item in ttm_events), 6)
                if ttm_events else None
            ),
            "coverage": "cash_dividend_pre_tax",
            "as_of": now_date.isoformat(),
        }
        return payload

    def get_performance_event_summary(
        self,
        stock_code: str,
        periods: int = 4,
    ) -> Dict[str, Any]:
        """获取业绩预告和业绩快报摘要。"""
        source = "tushare.performance_events"
        normalized_ts_code = self._convert_stock_code(stock_code)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason="api_not_initialized")

        data_as_of = self._v13_data_as_of()
        errors: List[str] = []
        forecast_events: List[Dict[str, Any]] = []
        express_events: List[Dict[str, Any]] = []

        try:
            forecast_df = self._call_api_with_rate_limit(
                "forecast",
                ts_code=normalized_ts_code,
                fields=(
                    "ts_code,ann_date,end_date,type,p_change_min,p_change_max,"
                    "net_profit_min,net_profit_max,last_parent_net,first_ann_date,"
                    "summary,change_reason"
                ),
            )
            if forecast_df is not None and not forecast_df.empty:
                sort_cols = [col for col in ("ann_date", "end_date") if col in forecast_df.columns]
                work_df = forecast_df.sort_values(by=sort_cols, ascending=False) if sort_cols else forecast_df
                for _, row in work_df.head(max(1, periods)).iterrows():
                    forecast_events.append(
                        {
                            "ts_code": self._safe_v13_str(row.get("ts_code")),
                            "ann_date": self._format_display_trade_date(row.get("ann_date")),
                            "report_period": self._format_display_trade_date(row.get("end_date")),
                            "forecast_type": self._safe_v13_str(row.get("type")),
                            "profit_change_min_pct": self._safe_v13_float(row.get("p_change_min")),
                            "profit_change_max_pct": self._safe_v13_float(row.get("p_change_max")),
                            "net_profit_min": self._safe_v13_float(row.get("net_profit_min")),
                            "net_profit_max": self._safe_v13_float(row.get("net_profit_max")),
                            "summary": self._safe_v13_str(row.get("summary")),
                            "change_reason": self._safe_v13_str(row.get("change_reason")),
                            "data_source": "tushare.forecast",
                            "data_as_of": data_as_of,
                            "is_degraded": False,
                        }
                    )
        except Exception as exc:
            errors.append(f"forecast:{type(exc).__name__}:{exc}")

        try:
            express_df = self._call_api_with_rate_limit(
                "express",
                ts_code=normalized_ts_code,
                fields=(
                    "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,"
                    "total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,"
                    "yoy_net_profit,bps,yoy_sales,yoy_op"
                ),
            )
            if express_df is not None and not express_df.empty:
                sort_cols = [col for col in ("ann_date", "end_date") if col in express_df.columns]
                work_df = express_df.sort_values(by=sort_cols, ascending=False) if sort_cols else express_df
                for _, row in work_df.head(max(1, periods)).iterrows():
                    express_events.append(
                        {
                            "ts_code": self._safe_v13_str(row.get("ts_code")),
                            "ann_date": self._format_display_trade_date(row.get("ann_date")),
                            "report_period": self._format_display_trade_date(row.get("end_date")),
                            "revenue": self._safe_v13_float(row.get("revenue")),
                            "operating_profit": self._safe_v13_float(row.get("operate_profit")),
                            "total_profit": self._safe_v13_float(row.get("total_profit")),
                            "net_profit_parent": self._safe_v13_float(row.get("n_income")),
                            "diluted_eps": self._safe_v13_float(row.get("diluted_eps")),
                            "diluted_roe": self._safe_v13_float(row.get("diluted_roe")),
                            "net_profit_yoy": self._safe_v13_float(row.get("yoy_net_profit")),
                            "revenue_yoy": self._safe_v13_float(row.get("yoy_sales")),
                            "data_source": "tushare.express",
                            "data_as_of": data_as_of,
                            "is_degraded": False,
                        }
                    )
        except Exception as exc:
            errors.append(f"express:{type(exc).__name__}:{exc}")

        has_events = bool(forecast_events or express_events)
        payload = self._v13_payload(
            source=source,
            trade_date=None,
            rows=forecast_events + express_events,
            status="ok" if has_events else "partial",
            data_as_of=data_as_of,
            degraded_reasons=errors if errors else ([] if has_events else ["empty_result"]),
        )
        payload["forecast_events"] = forecast_events
        payload["express_events"] = express_events
        return payload

    def get_tushare_fundamental_bundle(
        self,
        stock_code: str,
        latest_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        返回首页个股分析可直接合并的 Tushare 基本面增强包。

        该方法 fail-open：单一接口失败只记录在 errors/source_chain 中，
        其他接口成功的数据仍会返回给上层聚合。
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "valuation": {},
            "profitability": {},
            "growth": {},
            "earnings": {},
            "institution": {},
            "source_chain": [],
            "errors": [],
        }

        if self._api is None:
            result["source_chain"].append(
                {"provider": "tushare", "result": "unavailable", "duration_ms": 0}
            )
            result["errors"].append("tushare:api_not_initialized")
            return result

        try:
            daily_payload = self.get_daily_basic_metrics(stock_code)
        except Exception as exc:
            daily_payload = self._v13_unavailable_payload(
                source="tushare.daily_basic",
                trade_date=None,
                reason=str(exc),
            )
        self._append_payload_meta(result, daily_payload)
        daily_row = self._first_payload_row(daily_payload)
        if daily_row:
            result["valuation"] = {
                "trade_date": daily_row.get("trade_date"),
                "close": daily_row.get("close"),
                "pe_ratio": daily_row.get("pe_ratio"),
                "pe_ttm": daily_row.get("pe_ttm"),
                "pb_ratio": daily_row.get("pb_ratio"),
                "ps": daily_row.get("ps"),
                "ps_ttm": daily_row.get("ps_ttm"),
                "dividend_yield_pct": daily_row.get("dividend_yield_pct"),
                "dividend_yield_static_pct": daily_row.get("dividend_yield_static_pct"),
                "turnover_rate": daily_row.get("turnover_rate"),
                "turnover_rate_f": daily_row.get("turnover_rate_f"),
                "volume_ratio": daily_row.get("volume_ratio"),
                "total_mv": self._wan_yuan_to_yuan(daily_row.get("total_mv_wan")),
                "circ_mv": self._wan_yuan_to_yuan(daily_row.get("circ_mv_wan")),
                "total_mv_wan": daily_row.get("total_mv_wan"),
                "circ_mv_wan": daily_row.get("circ_mv_wan"),
                "unit": "market_value_wan_yuan",
                "source": "tushare.daily_basic",
                "data_status": daily_payload.get("status"),
                "degraded_reasons": list(daily_payload.get("degraded_reasons", []) or []),
            }

        try:
            indicator_payload = self.get_financial_indicator_summary(stock_code)
        except Exception as exc:
            indicator_payload = self._v13_unavailable_payload(
                source="tushare.fina_indicator",
                trade_date=None,
                reason=str(exc),
            )
        self._append_payload_meta(result, indicator_payload)
        indicator_row = self._first_payload_row(indicator_payload)
        if indicator_row:
            result["profitability"] = {
                "ann_date": indicator_row.get("ann_date"),
                "report_period": indicator_row.get("report_period"),
                "roe": indicator_row.get("roe"),
                "roe_dt": indicator_row.get("roe_dt"),
                "gross_margin": indicator_row.get("gross_margin"),
                "net_profit_margin": indicator_row.get("net_profit_margin"),
                "roa": indicator_row.get("roa"),
                "roic": indicator_row.get("roic"),
                "source": "tushare.fina_indicator",
                "data_status": indicator_payload.get("status"),
                "degraded_reasons": list(indicator_payload.get("degraded_reasons", []) or []),
            }
            result["growth"] = {
                "ann_date": indicator_row.get("ann_date"),
                "report_period": indicator_row.get("report_period"),
                "revenue_yoy": indicator_row.get("revenue_yoy"),
                "net_profit_yoy": indicator_row.get("net_profit_yoy"),
                "deducted_net_profit_yoy": indicator_row.get("deducted_net_profit_yoy"),
                "operating_cash_flow_yoy": indicator_row.get("operating_cash_flow_yoy"),
                "source": "tushare.fina_indicator",
                "data_status": indicator_payload.get("status"),
                "degraded_reasons": list(indicator_payload.get("degraded_reasons", []) or []),
            }
            result["earnings"]["financial_report"] = {
                "report_date": indicator_row.get("report_period"),
                "ann_date": indicator_row.get("ann_date"),
                "eps": indicator_row.get("eps"),
                "dt_eps": indicator_row.get("dt_eps"),
                "bps": indicator_row.get("bps"),
                "ocfps": indicator_row.get("ocfps"),
                "roe": indicator_row.get("roe"),
                "gross_margin": indicator_row.get("gross_margin"),
                "source": "tushare.fina_indicator",
                "data_status": indicator_payload.get("status"),
                "degraded_reasons": list(indicator_payload.get("degraded_reasons", []) or []),
            }

        try:
            dividend_payload = self.get_dividend_summary(stock_code)
        except Exception as exc:
            dividend_payload = self._v13_unavailable_payload(
                source="tushare.dividend",
                trade_date=None,
                reason=str(exc),
            )
        self._append_payload_meta(result, dividend_payload)
        dividend_summary = dividend_payload.get("summary") if isinstance(dividend_payload, dict) else None
        if isinstance(dividend_summary, dict) and dividend_summary:
            dividend = dict(dividend_summary)
            price_for_yield = latest_price or daily_row.get("close")
            ttm_cash = dividend.get("ttm_cash_dividend_per_share")
            try:
                price_value = float(price_for_yield) if price_for_yield is not None else None
                ttm_cash_value = float(ttm_cash) if ttm_cash is not None else None
            except (TypeError, ValueError):
                price_value = None
                ttm_cash_value = None
            if price_value and price_value > 0 and ttm_cash_value is not None:
                dividend["ttm_dividend_yield_pct"] = round(ttm_cash_value / price_value * 100.0, 4)
                dividend["yield_formula"] = "ttm_cash_dividend_per_share / latest_price * 100"
            dividend["data_status"] = dividend_payload.get("status")
            dividend["degraded_reasons"] = list(dividend_payload.get("degraded_reasons", []) or [])
            result["earnings"]["dividend"] = dividend

        try:
            performance_payload = self.get_performance_event_summary(stock_code)
        except Exception as exc:
            performance_payload = self._v13_unavailable_payload(
                source="tushare.performance_events",
                trade_date=None,
                reason=str(exc),
            )
        self._append_payload_meta(result, performance_payload)
        forecast_events = performance_payload.get("forecast_events") if isinstance(performance_payload, dict) else None
        express_events = performance_payload.get("express_events") if isinstance(performance_payload, dict) else None
        if isinstance(forecast_events, list) and forecast_events:
            latest_forecast = forecast_events[0]
            summary_text = latest_forecast.get("summary") or latest_forecast.get("change_reason")
            result["earnings"]["forecast_summary"] = summary_text
            result["earnings"]["forecast_events"] = forecast_events[:3]
        if isinstance(express_events, list) and express_events:
            latest_express = express_events[0]
            result["earnings"]["quick_report_summary"] = {
                "ann_date": latest_express.get("ann_date"),
                "report_period": latest_express.get("report_period"),
                "revenue": latest_express.get("revenue"),
                "net_profit_parent": latest_express.get("net_profit_parent"),
                "revenue_yoy": latest_express.get("revenue_yoy"),
                "net_profit_yoy": latest_express.get("net_profit_yoy"),
            }
            result["earnings"]["express_events"] = express_events[:3]

        has_content = any(
            bool(result.get(block))
            for block in ("valuation", "profitability", "growth", "earnings", "institution")
        )
        payload_statuses = {
            str(payload.get("status") or "").strip().lower()
            for payload in (daily_payload, indicator_payload, dividend_payload, performance_payload)
            if isinstance(payload, dict)
        }
        if has_content:
            result["status"] = "partial"
        elif "permission_denied" in payload_statuses:
            result["status"] = "permission_denied"
        else:
            result["status"] = "not_supported"
        return result

    def get_stock_limit_prices(self, trade_date: str, ts_code: Optional[str] = None) -> Dict[str, Any]:
        """
        获取每日涨跌停价格，供 V1.3 追高边界和跌停风险使用。

        Tushare 接口：stk_limit。
        """
        source = "tushare.stk_limit"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": "trade_date,ts_code,pre_close,up_limit,down_limit",
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)

        try:
            df = self._call_api_with_rate_limit("stk_limit", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "pre_close": self._safe_v13_float(row.get("pre_close")),
                    "up_limit": self._safe_v13_float(row.get("up_limit")),
                    "down_limit": self._safe_v13_float(row.get("down_limit")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def get_limit_list(self, trade_date: str, limit_type: Optional[str] = None) -> Dict[str, Any]:
        """
        获取每日涨跌停和炸板数据，供 V1.3 短线情绪使用。

        Tushare 接口：limit_list_d。limit_type 可传 U / D / Z。
        """
        source = "tushare.limit_list_d"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "trade_date,ts_code,industry,name,close,pct_chg,amount,limit_amount,"
                "float_mv,total_mv,turnover_ratio,fd_amount,first_time,last_time,"
                "open_times,up_stat,limit_times,limit"
            ),
        }
        if limit_type:
            params["limit_type"] = str(limit_type).strip().upper()

        try:
            df = self._call_api_with_rate_limit("limit_list_d", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "industry": self._safe_v13_str(row.get("industry")),
                    "name": self._safe_v13_str(row.get("name")),
                    "close": self._safe_v13_float(row.get("close")),
                    "pct_chg": self._safe_v13_float(row.get("pct_chg")),
                    "amount": self._safe_v13_float(row.get("amount")),
                    "limit_amount": self._safe_v13_float(row.get("limit_amount")),
                    "float_mv": self._safe_v13_float(row.get("float_mv")),
                    "total_mv": self._safe_v13_float(row.get("total_mv")),
                    "turnover_ratio": self._safe_v13_float(row.get("turnover_ratio")),
                    "fd_amount": self._safe_v13_float(row.get("fd_amount")),
                    "first_time": self._safe_v13_str(row.get("first_time")),
                    "last_time": self._safe_v13_str(row.get("last_time")),
                    "open_times": self._safe_v13_int(row.get("open_times")),
                    "up_stat": self._safe_v13_str(row.get("up_stat")),
                    "limit_times": self._safe_v13_int(row.get("limit_times")),
                    "limit": self._safe_v13_str(row.get("limit")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def get_ths_members(
        self,
        *,
        ts_code: Optional[str] = None,
        theme_code: Optional[str] = None,
        con_code: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取同花顺概念板块成分，供 V1.3 股票到题材映射使用。

        Tushare 接口：ths_member。ts_code/theme_code 表示板块指数代码，
        con_code 表示股票代码。
        """
        source = "tushare.ths_member"
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "fields": "ts_code,con_code,con_name,weight,in_date,out_date,is_new",
        }
        board_code = theme_code or ts_code
        if board_code:
            params["ts_code"] = str(board_code).strip().upper()
        if con_code:
            params["con_code"] = self._convert_stock_code(con_code)
        if limit is not None:
            params["limit"] = int(limit)
        if offset is not None:
            params["offset"] = int(offset)

        try:
            df = self._call_api_with_rate_limit("ths_member", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=None,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "theme_code": self._safe_v13_str(row.get("ts_code")),
                    "con_code": self._safe_v13_str(row.get("con_code")),
                    "con_name": self._safe_v13_str(row.get("con_name")),
                    "weight": self._safe_v13_float(row.get("weight")),
                    "in_date": self._format_display_trade_date(row.get("in_date")),
                    "out_date": self._format_display_trade_date(row.get("out_date")),
                    "is_new": self._safe_v13_str(row.get("is_new")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=None, rows=rows, data_as_of=data_as_of)

    def get_ths_index(
        self,
        *,
        ts_code: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取同花顺概念 / 行业指数基础信息，用于把 .TI 代码翻译成人可读名称。

        Tushare 接口：ths_index。当前 V1.3 只按 ts_code 精确查询，避免拉取全量概念表。
        """
        source = "tushare.ths_index"
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "fields": "ts_code,name,count,exchange,list_date,type",
        }
        if ts_code:
            params["ts_code"] = str(ts_code).strip().upper()
        if limit is not None:
            params["limit"] = int(limit)
        if offset is not None:
            params["offset"] = int(offset)

        try:
            df = self._call_api_with_rate_limit("ths_index", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=None, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=None,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "theme_code": self._safe_v13_str(row.get("ts_code")),
                    "theme_name": self._safe_v13_str(row.get("name")),
                    "member_count": self._safe_v13_int(row.get("count")),
                    "exchange": self._safe_v13_str(row.get("exchange")),
                    "list_date": self._format_display_trade_date(row.get("list_date")),
                    "type": self._safe_v13_str(row.get("type")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=None, rows=rows, data_as_of=data_as_of)

    @staticmethod
    def _is_generic_ths_board(name: str, board_type: str) -> bool:
        normalized_name = str(name or "")
        normalized_type = str(board_type or "").strip().upper()
        if normalized_type in {"BB", "S", "ST"}:
            return True

        generic_patterns = (
            "\u540c\u82b1\u987a\u5168A",
            "\u540c\u82b1\u987a\u6caa\u6df1\u5168A",
            "\u6caa\u6df1\u5168A",
            "\u540c\u82b1\u987a\u4e3b\u677f",
            "\u6df1\u80a1\u901a",
            "\u6caa\u80a1\u901a",
            "\u9646\u80a1\u901a",
            "\u5927\u76d8",
            "\u4e2d\u76d8",
            "\u5c0f\u76d8",
            "\u8d85\u5927\u76d8",
            "\u9ad8\u4f30\u503c",
            "\u4f4e\u4f30\u503c",
            "\u5747\u8861\u4f30\u503c",
            "\u9ad8\u76c8\u5229",
            "\u4f4e\u76c8\u5229",
            "\u9ad8\u52a8\u91cf",
            "\u4f4e\u52a8\u91cf",
            "\u6fc0\u8fdb\u6295\u8d44",
            "\u5747\u8861\u6295\u8d44",
            "\u9ad8\u4ef7\u80a1",
            "\u4f4e\u4ef7\u80a1",
            "\u91d1\u4ed3",
            "\u7b49\u6743",
            "\u9664\u91d1\u878d",
            "\u9664\u79d1\u521b\u677f",
        )
        return any(pattern in normalized_name for pattern in generic_patterns)

    @classmethod
    def _ths_board_relevance_key(cls, board: Dict[str, Any]) -> Tuple[int, int, str]:
        name = str(board.get("name") or "")
        board_type = str(board.get("type") or "").strip()
        normalized_type = board_type.upper()

        if normalized_type == "I" or "\u884c\u4e1a" in board_type:
            type_rank = 0
        elif normalized_type in {"N", "C"} or "\u6982\u5ff5" in board_type:
            type_rank = 1
        else:
            type_rank = 2

        generic_rank = 1 if cls._is_generic_ths_board(name, board_type) else 0
        return generic_rank, type_rank, name

    def get_belong_board(self, stock_code: str) -> List[Dict[str, Any]]:
        """
        获取个股所属同花顺板块。

        Tushare `ths_member` 只返回板块代码，板块名称通过 `ths_index`
        小批量补齐；补名称失败时保留代码作为可追踪 fallback。
        """
        if self._api is None:
            return []
        if _is_us_code(stock_code) or _is_hk_market(stock_code) or _is_etf_code(stock_code):
            return []

        member_payload = self.get_ths_members(con_code=stock_code, limit=20)
        if not self._payload_has_rows(member_payload):
            return []

        boards: List[Dict[str, Any]] = []
        seen_codes = set()
        for row in member_payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            theme_code = self._safe_v13_str(row.get("theme_code"))
            if not theme_code or theme_code in seen_codes:
                continue
            seen_codes.add(theme_code)

            board_name = ""
            board_type = ""
            try:
                index_payload = self.get_ths_index(ts_code=theme_code, limit=1)
                index_row = self._first_payload_row(index_payload)
                board_name = self._safe_v13_str(index_row.get("theme_name")) or ""
                board_type = self._safe_v13_str(index_row.get("type")) or ""
            except Exception as exc:
                logger.debug("[Tushare] ths_index lookup failed for %s: %s", theme_code, exc)

            boards.append(
                {
                    "name": board_name or theme_code,
                    "code": theme_code,
                    "type": board_type or "同花顺板块",
                    "source": "tushare.ths_member",
                    "in_date": row.get("in_date"),
                    "out_date": row.get("out_date"),
                    "is_new": row.get("is_new"),
                }
            )

        ranked_boards = sorted(
            enumerate(boards),
            key=lambda item: (*self._ths_board_relevance_key(item[1]), item[0]),
        )
        return [board for _, board in ranked_boards]

    def get_ths_hot(
        self,
        trade_date: str,
        *,
        market: str = "热股",
        is_new: str = "Y",
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取同花顺 App 热榜数据，供 V1.3 热榜集中度辅助判断。

        Tushare 接口：ths_hot。
        """
        source = "tushare.ths_hot"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "market": market,
            "is_new": is_new,
            "fields": (
                "trade_date,data_type,ts_code,ts_name,rank,pct_change,current_price,"
                "concept,rank_reason,hot,rank_time"
            ),
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)

        try:
            df = self._call_api_with_rate_limit("ths_hot", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "data_type": self._safe_v13_str(row.get("data_type")),
                    "ts_name": self._safe_v13_str(row.get("ts_name")),
                    "rank": self._safe_v13_int(row.get("rank")),
                    "pct_change": self._safe_v13_float(row.get("pct_change")),
                    "current_price": self._safe_v13_float(row.get("current_price")),
                    "concepts": self._parse_ths_concepts(row.get("concept")),
                    "rank_reason": self._safe_v13_str(row.get("rank_reason")),
                    "hot": self._safe_v13_float(row.get("hot")),
                    "rank_time": self._safe_v13_str(row.get("rank_time")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def get_dc_index(
        self,
        trade_date: str,
        *,
        ts_code: Optional[str] = None,
        name: Optional[str] = None,
        idx_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取东方财富概念 / 行业 / 地域板块行情，供真实板块强度识别使用。

        Tushare 接口：dc_index。
        """
        source = "tushare.dc_index"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "ts_code,trade_date,name,leading,leading_code,pct_change,leading_pct,"
                "total_mv,turnover_rate,up_num,down_num,idx_type,level"
            ),
        }
        if ts_code:
            params["ts_code"] = str(ts_code).strip().upper()
        if name:
            params["name"] = str(name).strip()
        if idx_type:
            params["idx_type"] = str(idx_type).strip()

        try:
            df = self._call_api_with_rate_limit("dc_index", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "theme_code": self._safe_v13_str(row.get("ts_code")),
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "theme_name": self._safe_v13_str(row.get("name")),
                    "name": self._safe_v13_str(row.get("name")),
                    "leading": self._safe_v13_str(row.get("leading")),
                    "leading_code": self._safe_v13_str(row.get("leading_code")),
                    "pct_change": self._safe_v13_float(row.get("pct_change")),
                    "leading_pct": self._safe_v13_float(row.get("leading_pct")),
                    "total_mv": self._safe_v13_float(row.get("total_mv")),
                    "turnover_rate": self._safe_v13_float(row.get("turnover_rate")),
                    "up_num": self._safe_v13_int(row.get("up_num")),
                    "down_num": self._safe_v13_int(row.get("down_num")),
                    "idx_type": self._safe_v13_str(row.get("idx_type")),
                    "level": self._safe_v13_str(row.get("level")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def get_dc_concepts(self, trade_date: str, *, idx_type: Optional[str] = "概念板块") -> Dict[str, Any]:
        """兼容产品文档里的 dc_concept 命名，底层使用 Tushare dc_index。"""
        return self.get_dc_index(trade_date, idx_type=idx_type)

    def get_dc_members(
        self,
        trade_date: str,
        *,
        ts_code: Optional[str] = None,
        con_code: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取东方财富板块成分，供股票到真实强板块映射使用。

        Tushare 接口：dc_member。
        """
        source = "tushare.dc_member"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": "trade_date,ts_code,con_code,name",
        }
        if ts_code:
            params["ts_code"] = str(ts_code).strip().upper()
        if con_code:
            params["con_code"] = self._convert_stock_code(con_code)
        if limit is not None:
            params["limit"] = int(limit)
        if offset is not None:
            params["offset"] = int(offset)

        try:
            df = self._call_api_with_rate_limit("dc_member", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "theme_code": self._safe_v13_str(row.get("ts_code")),
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "con_code": self._safe_v13_str(row.get("con_code")),
                    "con_name": self._safe_v13_str(row.get("name")),
                    "name": self._safe_v13_str(row.get("name")),
                    "trade_date": row_trade_date,
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def get_dc_moneyflow_themes(
        self,
        trade_date: str,
        *,
        content_type: Optional[str] = None,
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取东方财富行业 / 概念 / 地域板块资金流，供真实主线资金强度评分使用。

        Tushare 接口：moneyflow_ind_dc。
        """
        source = "tushare.moneyflow_ind_dc"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "trade_date,content_type,ts_code,name,pct_change,close,net_amount,"
                "net_amount_rate,buy_elg_amount,buy_elg_amount_rate,buy_lg_amount,"
                "buy_lg_amount_rate,buy_md_amount,buy_md_amount_rate,buy_sm_amount,"
                "buy_sm_amount_rate,buy_sm_amount_stock,rank"
            ),
        }
        if content_type:
            params["content_type"] = str(content_type).strip()
        if ts_code:
            params["ts_code"] = str(ts_code).strip().upper()

        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_dc", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "theme_code": self._safe_v13_str(row.get("ts_code")),
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "content_type": self._safe_v13_str(row.get("content_type")),
                    "theme_name": self._safe_v13_str(row.get("name")),
                    "name": self._safe_v13_str(row.get("name")),
                    "pct_change": self._safe_v13_float(row.get("pct_change")),
                    "close": self._safe_v13_float(row.get("close")),
                    "net_amount": self._safe_v13_float(row.get("net_amount")),
                    "net_amount_rate": self._safe_v13_float(row.get("net_amount_rate")),
                    "buy_elg_amount": self._safe_v13_float(row.get("buy_elg_amount")),
                    "buy_elg_amount_rate": self._safe_v13_float(row.get("buy_elg_amount_rate")),
                    "buy_lg_amount": self._safe_v13_float(row.get("buy_lg_amount")),
                    "buy_lg_amount_rate": self._safe_v13_float(row.get("buy_lg_amount_rate")),
                    "buy_md_amount": self._safe_v13_float(row.get("buy_md_amount")),
                    "buy_md_amount_rate": self._safe_v13_float(row.get("buy_md_amount_rate")),
                    "buy_sm_amount": self._safe_v13_float(row.get("buy_sm_amount")),
                    "buy_sm_amount_rate": self._safe_v13_float(row.get("buy_sm_amount_rate")),
                    "buy_sm_amount_stock": self._safe_v13_str(row.get("buy_sm_amount_stock")),
                    "rank": self._safe_v13_int(row.get("rank")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=display_trade_date,
            rows=rows,
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_stock_moneyflow_ths(
        self,
        trade_date: str,
        *,
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get 同花顺个股资金流快照，统一转成元口径供 V1.3 使用。"""
        source = "tushare.moneyflow_ths"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "trade_date,ts_code,name,pct_change,latest,net_amount,net_d5_amount,"
                "buy_lg_amount,buy_lg_amount_rate,buy_md_amount,buy_md_amount_rate,"
                "buy_sm_amount,buy_sm_amount_rate"
            ),
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)

        try:
            df = self._call_api_with_rate_limit("moneyflow_ths", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "name": self._safe_v13_str(row.get("name")),
                    "pct_change": self._safe_v13_float(row.get("pct_change")),
                    "close": self._safe_v13_float(row.get("latest")),
                    "net_amount": self._safe_v13_money_yuan(row.get("net_amount")),
                    "net_d5_amount": self._safe_v13_money_yuan(row.get("net_d5_amount")),
                    "buy_lg_amount": self._safe_v13_money_yuan(row.get("buy_lg_amount")),
                    "buy_lg_amount_rate": self._safe_v13_float(row.get("buy_lg_amount_rate")),
                    "buy_md_amount": self._safe_v13_money_yuan(row.get("buy_md_amount")),
                    "buy_md_amount_rate": self._safe_v13_float(row.get("buy_md_amount_rate")),
                    "buy_sm_amount": self._safe_v13_money_yuan(row.get("buy_sm_amount")),
                    "buy_sm_amount_rate": self._safe_v13_float(row.get("buy_sm_amount_rate")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=display_trade_date,
            rows=rows,
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_stock_moneyflow_dc(
        self,
        trade_date: str,
        *,
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get 东方财富个股资金流快照，统一转成元口径供 V1.3 使用。"""
        source = "tushare.moneyflow_dc"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "trade_date,ts_code,name,pct_change,close,net_amount,net_amount_rate,"
                "buy_elg_amount,buy_elg_amount_rate,buy_lg_amount,buy_lg_amount_rate,"
                "buy_md_amount,buy_md_amount_rate,buy_sm_amount,buy_sm_amount_rate"
            ),
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)

        try:
            df = self._call_api_with_rate_limit("moneyflow_dc", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "name": self._safe_v13_str(row.get("name")),
                    "pct_change": self._safe_v13_float(row.get("pct_change")),
                    "close": self._safe_v13_float(row.get("close")),
                    "net_amount": self._safe_v13_money_yuan(row.get("net_amount")),
                    "net_amount_rate": self._safe_v13_float(row.get("net_amount_rate")),
                    "buy_elg_amount": self._safe_v13_money_yuan(row.get("buy_elg_amount")),
                    "buy_elg_amount_rate": self._safe_v13_float(row.get("buy_elg_amount_rate")),
                    "buy_lg_amount": self._safe_v13_money_yuan(row.get("buy_lg_amount")),
                    "buy_lg_amount_rate": self._safe_v13_float(row.get("buy_lg_amount_rate")),
                    "buy_md_amount": self._safe_v13_money_yuan(row.get("buy_md_amount")),
                    "buy_md_amount_rate": self._safe_v13_float(row.get("buy_md_amount_rate")),
                    "buy_sm_amount": self._safe_v13_money_yuan(row.get("buy_sm_amount")),
                    "buy_sm_amount_rate": self._safe_v13_float(row.get("buy_sm_amount_rate")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=display_trade_date,
            rows=rows,
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_cyq_perf(
        self,
        trade_date: str,
        *,
        ts_code: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get 指定交易日筹码成本快照，统一成 V1.3 可回放口径。"""
        source = "tushare.cyq_perf"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "fields": (
                "ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,"
                "cost_85pct,cost_95pct,weight_avg,winner_rate"
            ),
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)
        if limit is not None:
            params["limit"] = int(limit)
        if offset is not None:
            params["offset"] = int(offset)

        try:
            df = self._call_api_with_rate_limit("cyq_perf", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            winner_rate = self._safe_v13_float(row.get("winner_rate"))
            if winner_rate is not None and winner_rate > 1.0:
                winner_rate = winner_rate / 100.0
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "trade_date": row_trade_date,
                    "his_low": self._safe_v13_float(row.get("his_low")),
                    "his_high": self._safe_v13_float(row.get("his_high")),
                    "cost_5pct": self._safe_v13_float(row.get("cost_5pct")),
                    "cost_15pct": self._safe_v13_float(row.get("cost_15pct")),
                    "cost_50pct": self._safe_v13_float(row.get("cost_50pct")),
                    "cost_85pct": self._safe_v13_float(row.get("cost_85pct")),
                    "cost_95pct": self._safe_v13_float(row.get("cost_95pct")),
                    "weight_avg": self._safe_v13_float(row.get("weight_avg")),
                    "winner_rate": winner_rate,
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=display_trade_date,
            rows=rows,
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_cyq_chips(
        self,
        trade_date: str,
        *,
        ts_code: str,
    ) -> Dict[str, Any]:
        """Get 指定交易日筹码分布，并聚合成 V1.3 可直接消费的筹码快照。"""
        source = "tushare.cyq_chips"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        normalized_ts_code = self._convert_stock_code(ts_code)
        try:
            distribution_df = self._call_api_with_rate_limit(
                "cyq_chips",
                ts_code=normalized_ts_code,
                start_date=ts_trade_date,
                end_date=ts_trade_date,
            )
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if distribution_df is None or distribution_df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        try:
            daily_df = self._call_api_with_rate_limit(
                "daily",
                ts_code=normalized_ts_code,
                start_date=ts_trade_date,
                end_date=ts_trade_date,
            )
        except Exception as exc:
            return self._v13_unavailable_payload(
                source=source,
                trade_date=display_trade_date,
                reason=f"daily_lookup_failed:{exc}",
            )

        if daily_df is None or daily_df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["daily_empty_result"],
            )

        current_price = self._safe_v13_float(daily_df.iloc[0].get("close"))
        if current_price is None or current_price <= 0:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["invalid_close_price"],
            )

        metrics = self._compute_v13_cyq_snapshot(distribution_df, current_price)
        if metrics is None:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["invalid_distribution"],
            )

        chip_trade_date = display_trade_date
        if "trade_date" in distribution_df.columns:
            distribution_dates = [
                self._format_display_trade_date(value)
                for value in distribution_df["trade_date"].tolist()
            ]
            distribution_dates = [value for value in distribution_dates if value]
            if distribution_dates:
                chip_trade_date = max(distribution_dates)

        row = {
            "ts_code": normalized_ts_code,
            "trade_date": chip_trade_date,
            "profit_ratio": self._safe_v13_float(metrics.get("profit_ratio")),
            "avg_cost": self._safe_v13_float(metrics.get("avg_cost")),
            "cost_90_low": self._safe_v13_float(metrics.get("cost_90_low")),
            "cost_90_high": self._safe_v13_float(metrics.get("cost_90_high")),
            "concentration_90": self._safe_v13_float(metrics.get("concentration_90")),
            "cost_70_low": self._safe_v13_float(metrics.get("cost_70_low")),
            "cost_70_high": self._safe_v13_float(metrics.get("cost_70_high")),
            "concentration_70": self._safe_v13_float(metrics.get("concentration_70")),
            "distribution_points": self._safe_v13_int(metrics.get("distribution_points")) or 0,
            "data_source": source,
            "data_as_of": data_as_of,
            "is_degraded": False,
        }
        return self._v13_payload_with_stale_check(
            source=source,
            trade_date=chip_trade_date,
            rows=[row],
            data_as_of=data_as_of,
            expected_trade_date=display_trade_date,
        )

    def get_kpl_list(
        self,
        trade_date: str,
        *,
        tag: str = "涨停",
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取开盘啦涨停 / 炸板榜单，用于补充涨停原因和题材语义。

        Tushare 接口：kpl_list。
        """
        source = "tushare.kpl_list"
        ts_trade_date = self._format_tushare_date(trade_date)
        display_trade_date = self._format_display_trade_date(trade_date)
        if self._api is None:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason="api_not_initialized")

        params: Dict[str, Any] = {
            "trade_date": ts_trade_date,
            "tag": tag,
            "fields": (
                "ts_code,name,trade_date,lu_time,ld_time,open_time,last_time,lu_desc,"
                "tag,theme,net_change,bid_amount,status,bid_change,bid_turnover,"
                "lu_bid_vol,pct_chg,bid_pct_chg,rt_pct_chg,limit_order,amount,"
                "turnover_rate,free_float,lu_limit_order"
            ),
        }
        if ts_code:
            params["ts_code"] = self._convert_stock_code(ts_code)

        try:
            df = self._call_api_with_rate_limit("kpl_list", **params)
        except Exception as exc:
            return self._v13_unavailable_payload(source=source, trade_date=display_trade_date, reason=str(exc))

        data_as_of = self._v13_data_as_of()
        if df is None or df.empty:
            return self._v13_payload(
                source=source,
                trade_date=display_trade_date,
                rows=[],
                status="partial",
                data_as_of=data_as_of,
                degraded_reasons=["empty_result"],
            )

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            row_trade_date = self._format_display_trade_date(row.get("trade_date")) or display_trade_date
            rows.append(
                {
                    "ts_code": self._safe_v13_str(row.get("ts_code")),
                    "name": self._safe_v13_str(row.get("name")),
                    "trade_date": row_trade_date,
                    "lu_time": self._safe_v13_str(row.get("lu_time")),
                    "ld_time": self._safe_v13_str(row.get("ld_time")),
                    "open_time": self._safe_v13_str(row.get("open_time")),
                    "last_time": self._safe_v13_str(row.get("last_time")),
                    "lu_desc": self._safe_v13_str(row.get("lu_desc")),
                    "tag": self._safe_v13_str(row.get("tag")),
                    "theme": self._safe_v13_str(row.get("theme")),
                    "net_change": self._safe_v13_float(row.get("net_change")),
                    "bid_amount": self._safe_v13_float(row.get("bid_amount")),
                    "status": self._safe_v13_str(row.get("status")),
                    "bid_change": self._safe_v13_float(row.get("bid_change")),
                    "bid_turnover": self._safe_v13_float(row.get("bid_turnover")),
                    "lu_bid_vol": self._safe_v13_float(row.get("lu_bid_vol")),
                    "pct_chg": self._safe_v13_float(row.get("pct_chg")),
                    "bid_pct_chg": self._safe_v13_float(row.get("bid_pct_chg")),
                    "rt_pct_chg": self._safe_v13_float(row.get("rt_pct_chg")),
                    "limit_order": self._safe_v13_float(row.get("limit_order")),
                    "amount": self._safe_v13_float(row.get("amount")),
                    "turnover_rate": self._safe_v13_float(row.get("turnover_rate")),
                    "free_float": self._safe_v13_float(row.get("free_float")),
                    "lu_limit_order": self._safe_v13_float(row.get("lu_limit_order")),
                    "data_source": source,
                    "data_as_of": data_as_of,
                    "is_degraded": False,
                }
            )

        return self._v13_payload(source=source, trade_date=display_trade_date, rows=rows, data_as_of=data_as_of)

    def _get_china_now(self) -> datetime:
        """返回上海时区当前时间，方便测试覆盖跨日刷新逻辑。"""
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _get_trade_dates(self, end_date: Optional[str] = None) -> List[str]:
        """按自然日刷新交易日历缓存，避免服务跨日后继续复用旧日历。"""
        if self._api is None:
            return []

        china_now = self._get_china_now()
        requested_end_date = end_date or china_now.strftime("%Y%m%d")

        if self.date_list is not None and self._date_list_end == requested_end_date:
            return self.date_list

        start_date = (china_now - timedelta(days=20)).strftime("%Y%m%d")
        df_cal = self._call_api_with_rate_limit(
            "trade_cal",
            exchange="SSE",
            start_date=start_date,
            end_date=requested_end_date,
        )

        if df_cal is None or df_cal.empty or "cal_date" not in df_cal.columns:
            logger.warning("[Tushare] trade_cal 返回为空，无法更新交易日历缓存")
            self.date_list = []
            self._date_list_end = requested_end_date
            return self.date_list

        trade_dates = sorted(
            df_cal[df_cal["is_open"] == 1]["cal_date"].astype(str).tolist(),
            reverse=True,
        )
        self.date_list = trade_dates
        self._date_list_end = requested_end_date
        return trade_dates

    @staticmethod
    def _pick_trade_date(trade_dates: List[str], use_today: bool) -> Optional[str]:
        """根据可用交易日列表选择当天或前一交易日。"""
        if not trade_dates:
            return None
        if use_today or len(trade_dates) == 1:
            return trade_dates[0]
        return trade_dates[1]

    @staticmethod
    def _detect_exchange_hint(stock_code: str) -> Optional[str]:
        """Return SH/SZ/BJ when the raw user input carries an explicit exchange hint."""
        upper = (stock_code or "").strip().upper()
        if upper.startswith(("SH", "SS")) or upper.endswith((".SH", ".SS")):
            return "SH"
        if upper.startswith("SZ") or upper.endswith(".SZ"):
            return "SZ"
        if upper.startswith("BJ") or upper.endswith(".BJ"):
            return "BJ"
        return None

    @classmethod
    def _get_legacy_realtime_symbol(cls, stock_code: str) -> str:
        """Build the legacy tushare symbol while preserving explicit SH/SZ hints."""
        code = normalize_stock_code(stock_code)
        exchange_hint = cls._detect_exchange_hint(stock_code)

        if code == '000001' and exchange_hint == 'SH':
            return 'sh000001'
        if code == '399001':
            return 'sz399001'
        if code == '399006':
            return 'sz399006'
        if code == '000300':
            return 'sh000300'
        if is_bse_code(code):
            return f"bj{code}"
        return code
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换 A 股 / ETF / 北交所等为 Tushare ts_code（不含港股逻辑）。

        Tushare 要求的格式示例：
        - 沪市股票：600519.SH
        - 深市股票：000001.SZ
        - 沪市 ETF：510050.SH
        - 深市 ETF：159919.SZ

        Args:
            stock_code: 原始代码，如 '600519', '000001', '563230'

        Returns:
            Tushare 格式代码，如 '600519.SH', '000001.SZ'
        """
        raw_code = stock_code.strip()
        
        # Already has suffix
        if '.' in raw_code:
            ts_code = raw_code.upper()
            if ts_code.endswith('.SS'):
                return f"{ts_code[:-3]}.SH"
            return ts_code

        if _is_us_code(raw_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {raw_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        if _is_hk_market(raw_code):
            #raise DataFetchError(f"TushareFetcher 不支持港股 {raw_code}，请使用 AkshareFetcher")
            return normalize_stock_code(raw_code)

        code = normalize_stock_code(raw_code)
        exchange_hint = self._detect_exchange_hint(raw_code)

        if exchange_hint == "SH":
            return f"{code}.SH"
        if exchange_hint == "SZ":
            return f"{code}.SZ"
        if exchange_hint == "BJ":
            return f"{code}.BJ"

        # ETF: determine exchange by prefix
        if code.startswith(_ETF_SH_PREFIXES) and len(code) == 6:
            return f"{code}.SH"
        if code.startswith(_ETF_SZ_PREFIXES) and len(code) == 6:
            return f"{code}.SZ"
        
        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            return f"{code}.BJ"
        
        # Regular stocks
        # Shanghai: 600xxx, 601xxx, 603xxx, 688xxx (STAR Market)
        # Shenzhen: 000xxx, 002xxx, 300xxx (ChiNext)
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SH"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            logger.warning(f"无法确定股票 {code} 的市场，默认使用深市")
            return f"{code}.SZ"

    def _convert_hk_stock_code_for_tushare(self, stock_code: str) -> str:
        """
        将用户输入转为 Tushare Pro 接口所需的 ts_code（含港股 nnnnn.HK）。

        - 非港股：委托 _convert_stock_code（A 股 / ETF / 北交所等）。
        - 港股：从 HK00700、00700、00700.HK 等形式归一为 5 位数字 + .HK。
        """
        raw_code = stock_code.strip()
        if _is_hk_market(raw_code):
            if "." in raw_code:
                ts_code = raw_code.upper()
                if ts_code.endswith(".SS"):
                    return f"{ts_code[:-3]}.SH"
                if ts_code.endswith(".HK"):
                    return ts_code
            digits = re.sub(r"\D", "", raw_code)
            if not digits:
                raise DataFetchError(f"无法识别港股代码 {raw_code}")
            code = digits[-5:].rjust(5, "0")
            return f"{code}.HK"
        return self._convert_stock_code(stock_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Tushare 获取原始数据
        
        根据代码类型选择不同接口：
        - 普通股票：daily()
        - ETF 基金：fund_daily()
        
        流程：
        1. 检查 API 是否可用
        2. 检查是否为美股（不支持）
        3. 执行速率限制检查
        4. 转换股票代码格式
        5. 根据代码类型选择接口并调用
        """
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")
        
        # US stocks not supported
        if _is_us_code(stock_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")
        
        # Rate-limit check
        self._check_rate_limit()
        
        is_hk = _is_hk_market(stock_code)
         # 判断是否为 ETF / 港股，以选择不同接口
        is_etf = _is_etf_code(stock_code)
        if is_hk:
            ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
            api_name = "hk_daily"
        else:
            ts_code = self._convert_stock_code(stock_code)
            api_name = "fund_daily" if is_etf else "daily"
        
        # Convert date format (Tushare requires YYYYMMDD)
        ts_start = start_date.replace('-', '')
        ts_end = end_date.replace('-', '')
        
       

        logger.debug(f"调用 Tushare {api_name}({ts_code}, {ts_start}, {ts_end})")
        
        try:
            if is_hk:
                # 港股使用 hk_daily 接口
                df = self._api.hk_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            elif is_etf:
                # ETF uses fund_daily interface
                df = self._api.fund_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            else:
                # Regular A-share stocks use daily interface
                df = self._api.daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 检测配额超限
            if any(keyword in error_msg for keyword in ['quota', '配额', 'limit', '权限']):
                logger.warning(f"Tushare 配额可能超限: {e}")
                raise RateLimitError(f"Tushare 配额超限: {e}") from e
            
            raise DataFetchError(f"Tushare 获取数据失败: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Tushare 数据
        
        Tushare daily / fund_daily 返回的列名：
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg

        单位缩放仅适用于 A 股（及 ETF 等使用同一套单位的接口）：
        - vol 按「手」计，乘以 100 转为「股」
        - amount 按「千元」计，乘以 1000 转为「元」

        港股 hk_daily 返回的 vol / amount 已是可直接使用的量级，不做上述缩放。
        """
        df = df.copy()
        is_hk = _is_hk_market(stock_code)

        # 列名映射
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
            # open, high, low, close, amount, pct_chg 列名相同
        }
        
        df = df.rename(columns=column_mapping)
        
        # 转换日期格式（YYYYMMDD -> YYYY-MM-DD）
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        
        # 成交量 / 成交额：仅 A 股类接口做单位换算（港股 hk_daily 不换算）
        if 'volume' in df.columns and not is_hk:
            df['volume'] = df['volume'] * 100
        
        if 'amount' in df.columns and not is_hk:
            df['amount'] = df['amount'] * 1000
        
        # 添加股票代码列
        df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称
        
        使用 Tushare 的 stock_basic 接口获取股票基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票名称，失败返回 None
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，无法获取股票名称")
            return None

        # 检查缓存
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 初始化缓存
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            # 速率限制检查
            self._check_rate_limit()
            

            # 根据市场/类型选择基础信息接口
            if _is_hk_market(stock_code):
                ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
                # 港股：使用 hk_basic
                df = self._api.hk_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            elif _is_etf_code(stock_code):
                ts_code = self._convert_stock_code(stock_code)
                # ETF：使用 fund_basic
                df = self._api.fund_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            else:
                ts_code = self._convert_stock_code(stock_code)
                # A 股股票：使用 stock_basic
                df = self._api.stock_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            
            if df is not None and not df.empty:
                name = df.iloc[0]['name']
                self._stock_name_cache[stock_code] = name
                logger.debug(f"Tushare 获取股票名称成功: {stock_code} -> {name}")
                return name
            
        except Exception as e:
            logger.warning(f"Tushare 获取股票名称失败 {stock_code}: {e}")
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        获取股票列表
        
        使用 Tushare 的 stock_basic 接口获取 A 股列表（不含港股）。
        
        Returns:
            包含 code, name, industry, area, market 列的 DataFrame，失败返回 None
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，无法获取股票列表")
            return None
        
        try:
            self._check_rate_limit()

            df = self._api.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,name,industry,area,market'
            )

            if df is None or df.empty:
                return None

            df = df.copy()
            df['code'] = df['ts_code'].astype(str).str.split('.').str[0]

            if not hasattr(self, '_stock_name_cache'):
                self._stock_name_cache = {}
            for _, row in df.iterrows():
                self._stock_name_cache[row['code']] = row['name']

            logger.info(f"Tushare 获取股票列表成功: {len(df)} 条")
            return df[['code', 'name', 'industry', 'area', 'market']]

        except Exception as e:
            logger.warning(f"Tushare 获取股票列表失败: {e}")

        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情

        策略：
        1. 优先尝试 Pro 接口（需要2000积分）：数据全，稳定性高
        2. 失败降级到旧版接口：门槛低，数据较少

        Args:
            stock_code: 股票代码

        Returns:
            UnifiedRealtimeQuote 对象，失败返回 None
        """
        if self._api is None:
            return None

        # HK stocks not supported by Tushare
        if _is_hk_market(stock_code):
            logger.debug(f"TushareFetcher 跳过港股实时行情 {stock_code}")
            return None

        normalized_code = normalize_stock_code(stock_code)

        from .realtime_types import (
            RealtimeSource,
            safe_float, safe_int
        )

        # 速率限制检查
        self._check_rate_limit()

        # 尝试 Pro 接口
        try:
            ts_code = self._convert_stock_code(stock_code)
            # 尝试调用 Pro 实时接口 (需要积分)
            df = self._api.quotation(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                logger.debug(f"Tushare Pro 实时行情获取成功: {stock_code}")

                return UnifiedRealtimeQuote(
                    code=normalized_code,
                    name=str(row.get('name', '')),
                    source=RealtimeSource.TUSHARE,
                    price=safe_float(row.get('price')),
                    change_pct=safe_float(row.get('pct_chg')),  # Pro 接口通常直接返回涨跌幅
                    change_amount=safe_float(row.get('change')),
                    volume=safe_int(row.get('vol')),
                    amount=safe_float(row.get('amount')),
                    high=safe_float(row.get('high')),
                    low=safe_float(row.get('low')),
                    open_price=safe_float(row.get('open')),
                    pre_close=safe_float(row.get('pre_close')),
                    turnover_rate=safe_float(row.get('turnover_ratio')), # Pro 接口可能有换手率
                    pe_ratio=safe_float(row.get('pe')),
                    pb_ratio=safe_float(row.get('pb')),
                    total_mv=safe_float(row.get('total_mv')),
                )
        except Exception as e:
            # 仅记录调试日志，不报错，继续尝试降级
            logger.debug(f"Tushare Pro 实时行情不可用 (可能是积分不足): {e}")

        # 降级：尝试旧版接口
        try:
            import tushare as ts

            symbol = self._get_legacy_realtime_symbol(stock_code)

            # 调用旧版实时接口 (ts.get_realtime_quotes)
            df = ts.get_realtime_quotes(symbol)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # 计算涨跌幅
            price = safe_float(row['price'])
            pre_close = safe_float(row['pre_close'])
            change_pct = 0.0
            change_amount = 0.0

            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100

            # 构建统一对象
            return UnifiedRealtimeQuote(
                code=normalized_code,
                name=str(row['name']),
                source=RealtimeSource.TUSHARE,
                price=price,
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=safe_int(row['volume']) // 100,  # 转换为手
                amount=safe_float(row['amount']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                open_price=safe_float(row['open']),
                pre_close=pre_close,
            )

        except Exception as e:
            logger.warning(f"Tushare (旧版) 获取实时行情失败 {stock_code}: {e}")
            return None

    def get_main_indices(self, region: str = "cn") -> Optional[List[dict]]:
        """
        获取主要指数实时行情 (Tushare Pro)，仅支持 A 股
        """
        if region != "cn":
            return None
        if self._api is None:
            return None

        from .realtime_types import safe_float

        # 指数映射：Tushare代码 -> 名称
        indices_map = {
            '000001.SH': '上证指数',
            '399001.SZ': '深证成指',
            '399006.SZ': '创业板指',
            '000688.SH': '科创50',
            '000016.SH': '上证50',
            '000300.SH': '沪深300',
        }

        try:
            self._check_rate_limit()

            # Tushare index_daily 获取历史数据，实时数据需用其他接口或估算
            # 由于 Tushare 免费用户可能无法获取指数实时行情，这里作为备选
            # 使用 index_daily 获取最近交易日数据

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - pd.Timedelta(days=5)).strftime('%Y%m%d')

            results = []

            # 批量获取所有指数数据
            for ts_code, name in indices_map.items():
                try:
                    df = self._api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        row = df.iloc[0] # 最新一天

                        current = safe_float(row['close'])
                        prev_close = safe_float(row['pre_close'])

                        results.append({
                            'code': ts_code.split('.')[0], # 兼容 sh000001 格式需转换，这里保持纯数字
                            'name': name,
                            'current': current,
                            'change': safe_float(row['change']),
                            'change_pct': safe_float(row['pct_chg']),
                            'open': safe_float(row['open']),
                            'high': safe_float(row['high']),
                            'low': safe_float(row['low']),
                            'prev_close': prev_close,
                            'volume': safe_float(row['vol']),
                            'amount': safe_float(row['amount']) * 1000, # 千元转元
                            'amplitude': 0.0 # Tushare index_daily 不直接返回振幅
                        })
                except Exception as e:
                    logger.debug(f"Tushare 获取指数 {name} 失败: {e}")
                    continue

            if results:
                return results
            else:
                logger.warning("[Tushare] 未获取到指数行情数据")

        except Exception as e:
            logger.error(f"[Tushare] 获取指数行情失败: {e}")

        return None

    def get_market_stats(self) -> Optional[dict]:
        """
        获取市场涨跌统计 (Tushare Pro)
        2000积分 每天访问该接口 ts.pro_api().rt_k 两次
        接口限制见：https://tushare.pro/document/1?doc_id=108
        """
        if self._api is None:
            return None

        try:
            logger.info("[Tushare] ts.pro_api() 获取市场统计...")
            
            # 获取当前中国时间，判断是否在交易时间内
            china_now = self._get_china_now()
            current_clock = china_now.strftime("%H:%M")
            current_date = china_now.strftime("%Y%m%d")

            trade_dates = self._get_trade_dates(current_date)
            if not trade_dates:
                return None

            is_trade_day = current_date in trade_dates

            # 盘中（09:30-16:30）和盘后（>16:30）优先用 rt_k
            # rt_k 盘后也能返回完整当天数据，比 daily 通配符查询更可靠
            if is_trade_day and current_clock >= '09:30':
                try:
                    df = self._call_api_with_rate_limit("rt_k", ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ')
                    if df is not None and not df.empty:
                        logger.info("[Tushare] rt_k 获取实时/盘后数据成功, rows=%d", len(df))
                        return self._calc_market_stats(df)
                except Exception as e:
                    logger.warning("[Tushare] ts.pro_api().rt_k 失败: %s，回退到 daily", e)

            # 盘前（<09:30）或非交易日或 rt_k 失败时，用 daily 接口
            if is_trade_day and current_clock < '09:30':
                last_date = self._pick_trade_date(trade_dates, use_today=False)
            elif is_trade_day:
                last_date = self._pick_trade_date(trade_dates, use_today=True)
            else:
                last_date = self._pick_trade_date(trade_dates, use_today=True)

            if last_date is None:
                return None

            try:
                df = self._call_api_with_rate_limit(
                    "daily",
                    ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ',
                    start_date=last_date,
                    end_date=last_date,
                )
                if df is not None and not df.empty:
                    df.columns = [col.lower() for col in df.columns]
                    df_basic = self._call_api_with_rate_limit("stock_basic", fields='ts_code,name')
                    df = pd.merge(df, df_basic, on='ts_code', how='left')
                    if 'amount' in df.columns:
                        df['amount'] = df['amount'] * 1000
                    logger.info("[Tushare] daily 获取数据成功, rows=%d", len(df))
                    return self._calc_market_stats(df)
            except Exception as e:
                logger.warning("[Tushare] ts.pro_api().daily 获取数据失败: %s", e)
                    

            
        except Exception as e:
            logger.error(f"[Tushare] 获取市场统计失败: {e}")

        return None
    
    def _calc_market_stats(
            self,
            df: pd.DataFrame,
            ) -> Optional[Dict[str, Any]]:
            """从行情 DataFrame 计算涨跌统计。"""
            import numpy as np

            df = df.copy()
            
            # 1. 提取基础比对数据：最新价、昨收
            # 兼容不同接口返回的列名 sina/em efinance tushare xtdata
            code_col = next((c for c in ['代码', '股票代码', 'ts_code','stock_code'] if c in df.columns), None)
            name_col = next((c for c in ['名称', '股票名称','name','name'] if c in df.columns), None)
            close_col = next((c for c in ['最新价', '最新价', 'close','lastPrice'] if c in df.columns), None)
            pre_close_col = next((c for c in ['昨收', '昨日收盘', 'pre_close','lastClose'] if c in df.columns), None)
            amount_col = next((c for c in ['成交额', '成交额', 'amount','amount'] if c in df.columns), None) 
            
            limit_up_count = 0
            limit_down_count = 0
            up_count = 0
            down_count = 0
            flat_count = 0

            for code, name, current_price, pre_close, amount in zip(
                df[code_col], df[name_col], df[close_col], df[pre_close_col], df[amount_col]
            ):
                
                # 停牌过滤 efinance 的停牌数据有时候会缺失价格显示为 '-'，em 显示为none
                if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                    continue
                
                # em、efinance 为str 需要转换为float
                current_price = float(current_price)
                pre_close = float(pre_close)
                
                # 获取去除前缀的纯数字代码
                pure_code = normalize_stock_code(str(code)) 

                # A. 确定每只股票的涨跌幅比例 (使用纯数字代码判断)
                if is_bse_code(pure_code): 
                    ratio = 0.30
                elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                    ratio = 0.20
                elif is_st_stock(name): #'ST' in str_name:
                    ratio = 0.05
                else:
                    ratio = 0.10

                # B. 严格按照 A 股规则计算涨跌停价：昨收 * (1 ± 比例) -> 四舍五入保留2位小数
                limit_up_price = np.floor(pre_close * (1 + ratio) * 100 + 0.5) / 100.0
                limit_down_price = np.floor(pre_close * (1 - ratio) * 100 + 0.5) / 100.0

                limit_up_price_Tolerance = round(abs(pre_close * (1 + ratio) - limit_up_price), 10)
                limit_down_price_Tolerance = round(abs(pre_close * (1 - ratio) - limit_down_price), 10)

                # C. 精确比对
                if current_price > 0 :
                    is_limit_up = (current_price > 0) and (abs(current_price - limit_up_price) <= limit_up_price_Tolerance)
                    is_limit_down = (current_price > 0) and (abs(current_price - limit_down_price) <= limit_down_price_Tolerance)

                    if is_limit_up:
                        limit_up_count += 1
                    if is_limit_down:
                        limit_down_count += 1

                    if current_price > pre_close:
                        up_count += 1
                    elif current_price < pre_close:
                        down_count += 1
                    else:
                        flat_count += 1
                    
            # 统计数量
            stats = {
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'total_amount': 0.0,
            }
            
            # 成交额统计
            if amount_col and amount_col in df.columns:
                df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
                stats['total_amount'] = (df[amount_col].sum() / 1e8)
                
            return stats

    def get_trade_time(self,early_time='09:30',late_time='16:30') -> Optional[str]:
        '''
        获取当前时间可以获得数据的开始时间日期

        Args:
                early_time: 默认 '09:30'
                late_time: 默认 '16:30'
                early_time-late_time 之间为使用上一个交易日数据的时间段，其他时间为使用当天数据的时间段
        Returns:
                start_date: 可以获得数据的开始日期
        '''
        china_now = self._get_china_now()
        china_date = china_now.strftime("%Y%m%d")
        china_clock = china_now.strftime("%H:%M")

        trade_dates = self._get_trade_dates(china_date)
        if not trade_dates:
            return None

        if china_date in trade_dates:
            if  early_time < china_clock < late_time: # 使用上一个交易日数据的时间段
                use_today = False
            else:
                use_today = True
        else:
            use_today = False

        start_date = self._pick_trade_date(trade_dates, use_today=use_today)
        if start_date is None:
            return None

        if not use_today:
            logger.info(f"[Tushare] 当前时间 {china_clock} 可能无法获取当天筹码分布，尝试获取前一个交易日的数据 {start_date}")

        return start_date
    
    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[list, list]]:
        """
        获取行业板块涨跌榜 (Tushare Pro)
        
        数据源优先级：
        1. 同花顺接口 (ts.pro_api().moneyflow_ind_ths)
        2. 东财接口 (ts.pro_api().moneyflow_ind_dc)
        注意：每个接口的行业分类和板块定义不同，会导致结果两者不一致
        """
        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # 涨幅前n
            top = df.nlargest(n, change_col)
            top_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in top.iterrows()
            ]

            bottom = df.nsmallest(n, change_col)
            bottom_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors

        # 15:30之后才有当天数据
        start_date = self.get_trade_time(early_time='00:00', late_time='15:30')
        if not start_date:
            return None

        # 优先同花顺接口
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_ths 获取板块排行(同花顺)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_ths", trade_date=start_date)
            if df is not None and not df.empty:
                change_col = 'pct_change'
                name = 'industry'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            logger.warning(f"[Tushare] 获取同花顺行业板块涨跌榜失败: {e} 尝试东财接口")

        # 同花顺接口失败，降级尝试东财接口
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_dc 获取板块排行(东财)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_dc", trade_date=start_date)
            if df is not None and not df.empty:
                df = df[df['content_type'] == '行业']  # 过滤出行业板块
                change_col = 'pct_change'
                name = 'name'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            logger.warning(f"[Tushare] 获取东财行业板块涨跌榜失败: {e}")
            return None
        
        # 获取为空或者接口调用失败，返回 None
        return None
    
    

    
    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        获取筹码分布数据
        
        数据来源：ts.pro_api().cyq_chips()
        包含：获利比例、平均成本、筹码集中度
        
        注意：ETF/指数没有筹码分布数据，会直接返回 None；港股不支持，直接返回 None。
        5000积分以下每天访问15次,每小时访问5次
        
        Args:
            stock_code: 股票代码
            
        Returns:
            ChipDistribution 对象（最新交易日的数据），获取失败返回 None

        """
        if _is_us_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持美股 {stock_code} 的筹码分布")
            return None
        
        if _is_etf_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持 ETF {stock_code} 的筹码分布")
            return None

        if _is_hk_market(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持港股 {stock_code} 的筹码分布")
            return None
        
        try:
            # 19点之后才有当天数据
            start_date = self.get_trade_time(early_time='00:00', late_time='19:00') 
            if not start_date:
                return None

            ts_code = self._convert_stock_code(stock_code)

            df = self._call_api_with_rate_limit(
                "cyq_chips",
                ts_code=ts_code,
                start_date=start_date,
                end_date=start_date,
            )
            if df is not None and not df.empty:
                daily_df = self._call_api_with_rate_limit(
                    "daily",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=start_date,
                )
                if daily_df is None or daily_df.empty:
                    return None
                current_price = daily_df.iloc[0]['close']
                metrics = self.compute_cyq_metrics(df, current_price)

                chip = ChipDistribution(
                    code=stock_code,
                    date=datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d'),
                    source="tushare.cyq_chips",
                    profit_ratio=metrics['获利比例'],
                    avg_cost=metrics['平均成本'],
                    cost_90_low=metrics['90成本-低'],
                    cost_90_high=metrics['90成本-高'],
                    concentration_90=metrics['90集中度'],
                    cost_70_low=metrics['70成本-低'],
                    cost_70_high=metrics['70成本-高'],
                    concentration_70=metrics['70集中度'],
                )
                
                logger.info(f"[筹码分布] {stock_code} 日期={chip.date}: 获利比例={chip.profit_ratio:.1%}, "
                        f"平均成本={chip.avg_cost}, 90%集中度={chip.concentration_90:.2%}, "
                        f"70%集中度={chip.concentration_70:.2%}")
                return chip

        except Exception as e:
            logger.warning(f"[Tushare] 获取筹码分布失败 {stock_code}: {e}")
            return None

    def compute_cyq_metrics(self, df: pd.DataFrame, current_price: float) -> dict:
        """
        基于 Tushare 的筹码分布明细表 (cyq_chips) 计算常用筹码指标  
        :param df: 包含 'price' 和 'percent' 列的 DataFrame  
        :param current_price: 股票当天的当前价/收盘价 (用于计算获利比例)  
        :return: 包含各项筹码指标的字典  
        """
        import numpy as np
        # 1. 确保按价格从小到大排序 (Tushare 返回的数据往往是纯倒序的)
        df_sorted = df.sort_values(by='price', ascending=True).reset_index(drop=True)

        # 2. 防止原始数据 percent 总和产生浮点数误差，归一化到 100%
        total_percent = df_sorted['percent'].sum()

        df_sorted['norm_percent'] = df_sorted['percent'] / total_percent * 100

        # 3. 计算筹码的累积分布
        df_sorted['cumsum'] = df_sorted['norm_percent'].cumsum()

        # --- 获利比例 ---
        # 所有价格 <= 当前价的筹码之和
        winner_rate = df_sorted[df_sorted['price'] <= current_price]['norm_percent'].sum()

        # --- 平均成本 ---
        # 价格的加权平均值
        avg_cost = np.average(df_sorted['price'], weights=df_sorted['norm_percent'])

        # --- 辅助函数：求指定累积比例处的价格 ---
        def get_percentile_price(target_pct):
            # 寻找累积求和第一次大于等于目标百分比的行索引
            idx = df_sorted['cumsum'].searchsorted(target_pct)
            idx = min(idx, len(df_sorted) - 1) # 防止越界
            return df_sorted.loc[idx, 'price']

        # --- 90% 成本区与集中度 ---
        # 去头去尾各 5%
        cost_90_low = get_percentile_price(5)
        cost_90_high = get_percentile_price(95)
        if (cost_90_high + cost_90_low) != 0:
            concentration_90 = (cost_90_high - cost_90_low) / (cost_90_high + cost_90_low) * 100
        else:
            concentration_90 = 0.0
            
        # --- 70% 成本区与集中度 ---
        # 去头去尾各 15%
        cost_70_low = get_percentile_price(15)
        cost_70_high = get_percentile_price(85)
        if (cost_70_high + cost_70_low) != 0:
            concentration_70 = (cost_70_high - cost_70_low) / (cost_70_high + cost_70_low) * 100
        else:
            concentration_70 = 0.0

        # 返回格式化结果
        return {
            "获利比例": round(winner_rate/100, 4), # /100 与akshare保持一致，返回小数格式
            "平均成本": round(avg_cost, 4),
            "90成本-低": round(cost_90_low, 4),
            "90成本-高": round(cost_90_high, 4),
            "90集中度": round(concentration_90/100, 4),
            "70成本-低": round(cost_70_low, 4),
            "70成本-高": round(cost_70_high, 4),
            "70集中度": round(concentration_70/100, 4)
        }



if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = TushareFetcher()
    
    try:
        # 测试历史数据
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
        
        # 测试股票名称
        name = fetcher.get_stock_name('600519')
        print(f"股票名称: {name}")
        
    except Exception as e:
        print(f"获取失败: {e}")

    # 测试市场统计
    print("\n" + "=" * 50)
    print("Testing get_market_stats (tushare)")
    print("=" * 50)
    try:
        stats = fetcher.get_market_stats()
        if stats:
            print(f"Market Stats successfully computed:")
            print(f"Up: {stats['up_count']} (Limit Up: {stats['limit_up_count']})")
            print(f"Down: {stats['down_count']} (Limit Down: {stats['limit_down_count']})")
            print(f"Flat: {stats['flat_count']}")
            print(f"Total Amount: {stats['total_amount']:.2f} 亿 (Yi)")
        else:
            print("Failed to compute market stats.")
    except Exception as e:
        print(f"Failed to compute market stats: {e}")


    # 测试筹码分布数据
    print("\n" + "=" * 50)
    print("测试筹码分布数据获取")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # 茅台
    except Exception as e:
        print(f"[筹码分布] 获取失败: {e}")

    # 测试行业板块排名
    print("\n" + "=" * 50)
    print("测试行业板块排名获取")
    print("=" * 50)
    try:
        rankings = fetcher.get_sector_rankings(n=5)
        if rankings:
            top, bottom = rankings
            print("涨幅榜 Top 5:")
            for sector in top:
                print(f"{sector['name']}: {sector['change_pct']}%")
            print("\n跌幅榜 Top 5:")
            for sector in bottom:
                print(f"{sector['name']}: {sector['change_pct']}%")
        else:
            print("未获取到行业板块排名数据")
    except Exception as e:
        print(f"[行业板块排名] 获取失败: {e}")
