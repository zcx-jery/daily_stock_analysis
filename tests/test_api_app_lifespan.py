# -*- coding: utf-8 -*-
"""Tests for FastAPI lifecycle-managed services."""

from pathlib import Path

from fastapi.testclient import TestClient

from api import app as app_module


class _DummyBacktestService:
    def __init__(self, events):
        self._events = events

    def close(self):
        self._events.append("close")


def test_app_lifespan_starts_and_closes_momentum_backtest_worker(monkeypatch, tmp_path):
    events = []

    def fake_initialize(app, **_kwargs):
        events.append("initialize")
        service = _DummyBacktestService(events)
        app.state.momentum_backtest_service = service
        return service

    monkeypatch.setattr(app_module, "initialize_momentum_backtest_service", fake_initialize)

    app = app_module.create_app(static_dir=Path(tmp_path), start_backtest_worker=True)
    with TestClient(app):
        assert events == ["initialize"]

    assert events == ["initialize", "close"]


def test_app_lifespan_keeps_api_available_when_backtest_worker_start_fails(monkeypatch, tmp_path):
    def fake_initialize(_app, **_kwargs):
        raise RuntimeError("simulated startup failure")

    monkeypatch.setattr(app_module, "initialize_momentum_backtest_service", fake_initialize)

    app = app_module.create_app(static_dir=Path(tmp_path), start_backtest_worker=True)
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
