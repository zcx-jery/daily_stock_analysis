# -*- coding: utf-8 -*-
"""
Shared data parsing and normalization helpers.
"""

import json
from typing import Any, Dict, List, Optional


_MODEL_PLACEHOLDER_VALUES = {"unknown", "error", "none", "null", "n/a"}


def normalize_model_used(value: Any) -> Optional[str]:
    """Normalize placeholder/empty model values to None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _MODEL_PLACEHOLDER_VALUES:
        return None
    return text


def parse_json_field(value: Any) -> Any:
    """Best-effort JSON parse for string values; passthrough for others."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
    return value


def _non_empty_dict(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    return value if value else None


def _normalize_belong_boards(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name is None:
            continue
        name_text = str(name).strip()
        if not name_text:
            continue
        board = {"name": name_text}
        if item.get("code") is not None:
            code_text = str(item.get("code")).strip()
            if code_text:
                board["code"] = code_text
        if item.get("type") is not None:
            type_text = str(item.get("type")).strip()
            if type_text:
                board["type"] = type_text
        normalized.append(board)
    return normalized


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.endswith("%"):
                text = text[:-1].strip()
            return float(text)
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_sector_ranking_items(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name is None:
            continue
        name_text = str(name).strip()
        if not name_text:
            continue
        ranking_item: Dict[str, Any] = {"name": name_text}
        change_pct = _safe_float(item.get("change_pct"))
        if change_pct is not None:
            ranking_item["change_pct"] = change_pct
        normalized.append(ranking_item)
    return normalized


def _normalize_sector_rankings(value: Any) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not isinstance(value, dict):
        return None

    return {
        "top": _normalize_sector_ranking_items(value.get("top")),
        "bottom": _normalize_sector_ranking_items(value.get("bottom")),
    }


def _normalize_source_chain(value: Any, limit: int = 24) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        provider = item.get("provider")
        if provider is None:
            continue
        entry: Dict[str, Any] = {"provider": str(provider)}
        result = item.get("result")
        if result is not None:
            entry["result"] = str(result)
        duration_ms = _safe_float(item.get("duration_ms"))
        if duration_ms is not None:
            entry["duration_ms"] = int(duration_ms)
        if item.get("error") is not None:
            entry["error"] = str(item.get("error"))
        normalized.append(entry)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_error_list(value: Any, limit: int = 12) -> List[str]:
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    seen = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
        if len(normalized) >= limit:
            break
    return normalized


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _block_data(fundamental_ctx: Dict[str, Any], block_name: str) -> Dict[str, Any]:
    block = fundamental_ctx.get(block_name)
    data = block.get("data") if isinstance(block, dict) else None
    return data if isinstance(data, dict) else {}


def _block_status(fundamental_ctx: Dict[str, Any], block_name: str) -> Optional[str]:
    block = fundamental_ctx.get(block_name)
    status = block.get("status") if isinstance(block, dict) else None
    return str(status) if status is not None else None


def _block_sources(fundamental_ctx: Dict[str, Any], block_name: str, limit: int = 8) -> List[Dict[str, Any]]:
    block = fundamental_ctx.get(block_name)
    source_chain = block.get("source_chain") if isinstance(block, dict) else None
    return _normalize_source_chain(source_chain, limit=limit)


def _block_errors(fundamental_ctx: Dict[str, Any], block_name: str, limit: int = 6) -> List[str]:
    block = fundamental_ctx.get(block_name)
    errors = block.get("errors") if isinstance(block, dict) else None
    return _normalize_error_list(errors, limit=limit)


def extract_fundamental_context(
    context_snapshot: Any,
    fallback_fundamental_payload: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve fundamental_context from context snapshot, with optional fallback payload.
    """
    snapshot_obj = parse_json_field(context_snapshot)
    if isinstance(snapshot_obj, dict):
        direct_fundamental = snapshot_obj.get("fundamental_context")
        if isinstance(direct_fundamental, dict):
            return direct_fundamental

        enhanced = snapshot_obj.get("enhanced_context")
        if isinstance(enhanced, dict):
            fundamental = enhanced.get("fundamental_context")
            if isinstance(fundamental, dict):
                return fundamental

    fallback_obj = parse_json_field(fallback_fundamental_payload)
    if isinstance(fallback_obj, dict):
        return fallback_obj
    return None


def extract_fundamental_detail_fields(
    context_snapshot: Any,
    fallback_fundamental_payload: Any = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Extract stable API-facing financial and dividend blocks from fundamental_context.
    """
    fundamental_ctx = extract_fundamental_context(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    if not isinstance(fundamental_ctx, dict):
        return {"financial_report": None, "dividend_metrics": None, "fundamental_metrics": None}

    earnings_block = fundamental_ctx.get("earnings")
    earnings_data = earnings_block.get("data") if isinstance(earnings_block, dict) else None
    if not isinstance(earnings_data, dict):
        earnings_data = {}

    financial_report = _non_empty_dict(earnings_data.get("financial_report"))
    dividend_metrics = _non_empty_dict(earnings_data.get("dividend"))
    valuation_data = _block_data(fundamental_ctx, "valuation")
    profitability_data = _block_data(fundamental_ctx, "profitability")
    growth_data = _block_data(fundamental_ctx, "growth")
    fundamental_metrics = None
    if valuation_data or profitability_data or growth_data:
        statuses = {
            "valuation": _block_status(fundamental_ctx, "valuation"),
            "profitability": _block_status(fundamental_ctx, "profitability"),
            "growth": _block_status(fundamental_ctx, "growth"),
        }
        fundamental_metrics = {
            "valuation": _non_empty_dict(valuation_data),
            "profitability": _non_empty_dict(profitability_data),
            "growth": _non_empty_dict(growth_data),
            "statuses": {key: value for key, value in statuses.items() if value is not None},
            "source_chain": _normalize_source_chain(fundamental_ctx.get("source_chain"), limit=24),
            "errors": _normalize_error_list(fundamental_ctx.get("errors"), limit=12),
        }
    return {
        "financial_report": financial_report,
        "dividend_metrics": dividend_metrics,
        "fundamental_metrics": fundamental_metrics,
    }


def extract_enhanced_detail_fields(
    context_snapshot: Any,
    fallback_fundamental_payload: Any = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Extract optional Phase-2 detail blocks from fundamental_context.
    """
    fundamental_ctx = extract_fundamental_context(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    if not isinstance(fundamental_ctx, dict):
        return {
            "capital_flow_metrics": None,
            "chip_metrics": None,
            "data_quality": None,
            "tushare_enhancement": None,
        }

    capital_flow_data = _block_data(fundamental_ctx, "capital_flow")
    capital_flow_metrics = None
    if capital_flow_data:
        stock_flow = capital_flow_data.get("stock_flow")
        ths = capital_flow_data.get("ths")
        dc = capital_flow_data.get("dc")
        capital_flow_metrics = {
            "status": _block_status(fundamental_ctx, "capital_flow"),
            "signal": capital_flow_data.get("signal"),
            "mixed_reason": capital_flow_data.get("mixed_reason"),
            "trade_date": _first_non_empty(
                stock_flow.get("trade_date") if isinstance(stock_flow, dict) else None,
                ths.get("trade_date") if isinstance(ths, dict) else None,
                dc.get("trade_date") if isinstance(dc, dict) else None,
            ),
            "stock_flow": _non_empty_dict(stock_flow),
            "ths": _non_empty_dict(ths),
            "dc": _non_empty_dict(dc),
            "source_chain": _block_sources(fundamental_ctx, "capital_flow"),
            "errors": _block_errors(fundamental_ctx, "capital_flow"),
        }

    chip_data = _block_data(fundamental_ctx, "chip")
    chip_metrics = None
    if chip_data:
        chip_metrics = {
            "status": _block_status(fundamental_ctx, "chip"),
            "chip_status": chip_data.get("chip_status"),
            "chip_signal": chip_data.get("chip_signal"),
            "source": _first_non_empty(chip_data.get("data_source"), chip_data.get("source")),
            "as_of": _first_non_empty(chip_data.get("date"), chip_data.get("trade_date")),
            "data": chip_data,
            "source_chain": _block_sources(fundamental_ctx, "chip"),
            "errors": _block_errors(fundamental_ctx, "chip"),
        }

    coverage = fundamental_ctx.get("coverage") if isinstance(fundamental_ctx.get("coverage"), dict) else {}
    source_chain = _normalize_source_chain(fundamental_ctx.get("source_chain"), limit=32)
    errors = _normalize_error_list(fundamental_ctx.get("errors"), limit=16)
    block_names = [
        "valuation",
        "profitability",
        "growth",
        "earnings",
        "capital_flow",
        "boards",
        "chip",
        "institution",
        "dragon_tiger",
    ]
    blocks: Dict[str, Dict[str, Any]] = {}
    for block_name in block_names:
        status = coverage.get(block_name) or _block_status(fundamental_ctx, block_name)
        if status is None:
            continue
        blocks[block_name] = {
            "status": str(status),
            "source_chain": _block_sources(fundamental_ctx, block_name, limit=4),
            "errors": _block_errors(fundamental_ctx, block_name, limit=4),
        }

    data_quality = {
        "status": fundamental_ctx.get("status"),
        "market": fundamental_ctx.get("market"),
        "enhanced_by_tushare": bool(fundamental_ctx.get("enhanced_by_tushare")),
        "coverage": coverage,
        "blocks": blocks,
        "source_chain": source_chain,
        "errors": errors,
        "elapsed_ms": fundamental_ctx.get("elapsed_ms"),
    }

    tushare_sources = [
        entry for entry in source_chain
        if "tushare" in str(entry.get("provider", "")).lower()
    ]
    tushare_blocks = [
        name for name, status in coverage.items()
        if status in {"ok", "partial", "complete"} and any(
            "tushare" in str(source.get("provider", "")).lower()
            for source in _block_sources(fundamental_ctx, str(name), limit=8)
        )
    ]
    tushare_enhancement = {
        "enabled": bool(fundamental_ctx.get("enhanced_by_tushare")) or bool(tushare_sources),
        "blocks": tushare_blocks,
        "source_chain": tushare_sources,
        "coverage": coverage,
    }

    return {
        "capital_flow_metrics": capital_flow_metrics,
        "chip_metrics": chip_metrics,
        "data_quality": data_quality,
        "tushare_enhancement": tushare_enhancement,
    }


def extract_board_detail_fields(
    context_snapshot: Any,
    fallback_fundamental_payload: Any = None,
) -> Dict[str, Any]:
    """
    Extract stable board detail fields from fundamental_context.
    """
    fundamental_ctx = extract_fundamental_context(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    if not isinstance(fundamental_ctx, dict):
        return {"belong_boards": [], "sector_rankings": None, "board_linkage": None}

    boards_block = fundamental_ctx.get("boards")
    sector_rankings = None
    board_linkage = None
    if isinstance(boards_block, dict):
        boards_status = boards_block.get("status")
        if boards_status in {"ok", "partial"} or boards_status is None:
            boards_data = boards_block.get("data")
            sector_rankings = boards_data
            if isinstance(boards_data, dict):
                relative_strength = boards_data.get("relative_strength")
                board_linkage = _non_empty_dict(relative_strength)
    return {
        "belong_boards": _normalize_belong_boards(fundamental_ctx.get("belong_boards")),
        "sector_rankings": _normalize_sector_rankings(sector_rankings),
        "board_linkage": board_linkage,
    }
