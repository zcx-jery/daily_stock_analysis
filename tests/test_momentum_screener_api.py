# -*- coding: utf-8 -*-
"""API tests for momentum screener endpoint."""

import sys
import types
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.modules.setdefault(
    "fake_useragent",
    types.SimpleNamespace(UserAgent=lambda *args, **kwargs: types.SimpleNamespace(random="pytest-agent")),
)
multipart_module = types.ModuleType("multipart")
multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (value, {})
multipart_module.__version__ = "0.0-test"
sys.modules.setdefault("multipart", multipart_module)
sys.modules.setdefault("multipart.multipart", multipart_submodule)

from api.app import create_app
import src.auth as auth
from src.services.momentum_screener_service import MomentumScreenerService
from tests.test_momentum_screener_service import _FakeFetcher


class _IntegrationMomentumScreenerService(MomentumScreenerService):
    def __init__(self):
        super().__init__(fetcher=_FakeFetcher())


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def disable_auth():
    auth._auth_enabled = None
    with patch("api.middlewares.auth.is_auth_enabled", return_value=False), \
         patch("src.auth.is_auth_enabled", return_value=False):
        yield
    auth._auth_enabled = None


def test_momentum_screener_endpoint_returns_response(client):
    fake_result = {
        "profile": "standard",
        "trade_date": "2026-04-10",
        "candidate_count": 1,
        "results": [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "测试龙头",
                "pct_chg": 9.8,
                "continuation_score": 86.5,
                "extension_score": 78.2,
                "risk_score": 15.0,
                "buyability_score": None,
                "final_score": 84.0,
                "rank_score": 73.4,
                "themes": ["电力设备"],
                "leader_level": "龙头",
                "top_reasons": ["强势确认", "量价结构"],
                "risk_tags": [],
                "score_breakdown": {
                    "strength_confirmation": {
                        "score": 17.0,
                        "max_score": 20.0,
                        "items": {"pct_chg_strength": 6},
                    }
                },
            }
        ],
    }

    with patch("api.deps.MomentumScreenerService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.screen.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "standard", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "standard"
    assert data["candidate_count"] == 1
    assert data["results"][0]["ts_code"] == "600001.SH"


def test_momentum_screener_endpoint_supports_aggressive_profile(client):
    fake_result = {
        "profile": "aggressive",
        "trade_date": "2026-04-10",
        "candidate_count": 1,
        "results": [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "测试龙头",
                "pct_chg": 9.8,
                "continuation_score": 88.1,
                "extension_score": 81.4,
                "risk_score": 6.7,
                "buyability_score": 72.5,
                "opportunity_tag": "分歧转一致",
                "entry_range_low": 10.34,
                "entry_range_high": 10.66,
                "final_score": 91.0,
                "rank_score": 79.6,
                "themes": ["电力设备"],
                "leader_level": "龙头",
                "top_reasons": ["强势确认", "买入可行性"],
                "risk_tags": ["upper_shadow"],
                "score_breakdown": {
                    "strength_confirmation": {
                        "score": 26.0,
                        "max_score": 30.0,
                        "items": {"limit_strength": 10},
                    },
                    "buyability": {
                        "score": 11.0,
                        "max_score": 15.0,
                        "items": {"amplitude_space": 6},
                    },
                },
            }
        ],
    }

    with patch("api.deps.MomentumScreenerService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.screen.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "aggressive"
    assert data["results"][0]["buyability_score"] == 72.5
    assert data["results"][0]["opportunity_tag"] == "分歧转一致"
    assert data["results"][0]["entry_range_low"] == 10.34
    assert data["results"][0]["entry_range_high"] == 10.66
    assert "buyability" in data["results"][0]["score_breakdown"]


def test_momentum_screener_endpoint_runs_real_standard_service_flow(client):
    with patch("api.deps.MomentumScreenerService", _IntegrationMomentumScreenerService):
        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "standard", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "standard"
    assert data["trade_date"] == "2026-04-10"
    assert data["candidate_count"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["ts_code"] == "600001.SH"
    assert data["results"][0]["themes"][0] == "电力设备"
    assert "strength_confirmation" in data["results"][0]["score_breakdown"]
    assert hasattr(client.app.state, "momentum_screener_service")


def test_momentum_screener_endpoint_runs_real_aggressive_service_flow(client):
    with patch("api.deps.MomentumScreenerService", _IntegrationMomentumScreenerService):
        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "aggressive", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "aggressive"
    assert data["trade_date"] == "2026-04-10"
    assert data["candidate_count"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["buyability_score"] is not None
    assert data["results"][0]["opportunity_tag"] is not None
    assert data["results"][0]["entry_range_low"] is not None
    assert data["results"][0]["entry_range_high"] is not None
    assert "buyability" in data["results"][0]["score_breakdown"]


def test_health_endpoint_exposes_momentum_sector_cache_stats(client):
    with patch.object(
        MomentumScreenerService,
        "get_sector_cache_stats",
        return_value={"hit": 5, "miss": 2},
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["diagnostics"]["momentum_sector_cache"] == {"hit": 5, "miss": 2}
