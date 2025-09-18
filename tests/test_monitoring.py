from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from notebooklm_mcp import monitoring


def test_metrics_collector_records_requests() -> None:
    collector = monitoring.MetricsCollector()

    collector.record_request(success=True, response_time=0.5)
    collector.record_request(success=False, response_time=1.0)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(3)

    metrics = collector.get_metrics()
    assert metrics["requests_total"] == 2
    assert metrics["requests_success"] == 1
    assert metrics["requests_failed"] == 1
    assert metrics["active_sessions"] == 3
    assert metrics["browser_restarts"] == 1
    assert metrics["authentication_failures"] == 1


def test_metrics_collector_with_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)

    class DummyCounter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, float | None]] = []

        def inc(self) -> None:
            self.calls.append(("inc", None))

    class DummyHistogram(DummyCounter):
        def observe(self, value: float) -> None:
            self.calls.append(("observe", value))

    class DummyGauge:
        def __init__(self) -> None:
            self.calls: list[float] = []

        def set(self, value: float) -> None:
            self.calls.append(value)

    monkeypatch.setattr(
        monitoring, "Counter", lambda *_, **__: DummyCounter(), raising=False
    )
    monkeypatch.setattr(
        monitoring, "Histogram", lambda *_, **__: DummyHistogram(), raising=False
    )
    monkeypatch.setattr(
        monitoring, "Gauge", lambda *_, **__: DummyGauge(), raising=False
    )
    monkeypatch.setattr(
        monitoring.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=50.0, used=2048),
    )
    monkeypatch.setattr(
        monitoring.psutil, "cpu_percent", lambda interval=None: 12.5
    )

    collector = monitoring.MetricsCollector()
    collector.record_request(success=True, response_time=0.25)
    collector.record_request(success=False, response_time=0.5)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(7)
    collector.update_system_metrics()

    assert collector.requests_counter.calls == [("inc", None), ("inc", None)]
    assert collector.requests_success_counter.calls == [("inc", None)]
    assert collector.requests_failed_counter.calls == [("inc", None)]
    assert collector.response_time_histogram.calls == [
        ("observe", 0.25),
        ("observe", 0.5),
    ]
    assert collector.browser_restarts_counter.calls == [("inc", None)]
    assert collector.auth_failures_counter.calls == [("inc", None)]
    assert collector.active_sessions_gauge.calls == [7]
    assert collector.memory_usage_gauge.calls == [2048]
    assert collector.cpu_usage_gauge.calls == [12.5]


def test_health_checker_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = SimpleNamespace(current_url="https://example.com")
    client = SimpleNamespace(driver=driver, _is_authenticated=True)

    health_checker = monitoring.HealthChecker(client)

    monkeypatch.setattr(monitoring.psutil, "virtual_memory", lambda: SimpleNamespace(percent=10))
    monkeypatch.setattr(monitoring.psutil, "cpu_percent", lambda interval=None: 5.0)

    result = asyncio.run(health_checker.check_health())
    assert result.healthy is True
    assert result.browser_status == "healthy"
    assert result.authentication_status == "authenticated"


def test_health_checker_reports_not_started(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(driver=None, _is_authenticated=False)
    health_checker = monitoring.HealthChecker(client)

    monkeypatch.setattr(monitoring.psutil, "virtual_memory", lambda: SimpleNamespace(percent=10))
    monkeypatch.setattr(monitoring.psutil, "cpu_percent", lambda interval=None: 5.0)

    result = asyncio.run(health_checker.check_health())
    assert result.browser_status == "not_started"
    assert result.authentication_status == "not_authenticated"
    assert result.healthy is False


def test_health_checker_marks_browser_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenDriver:
        @property
        def current_url(self) -> str:  # pragma: no cover - property for raising below
            raise RuntimeError("navigation failed")

    client = SimpleNamespace(driver=BrokenDriver(), _is_authenticated=False)
    health_checker = monitoring.HealthChecker(client)

    monkeypatch.setattr(monitoring.psutil, "virtual_memory", lambda: SimpleNamespace(percent=10))
    monkeypatch.setattr(monitoring.psutil, "cpu_percent", lambda interval=None: 5.0)

    result = asyncio.run(health_checker.check_health())
    assert result.browser_status.startswith("unhealthy:")
    assert result.healthy is False


def test_health_checker_handles_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(driver=None, _is_authenticated=False)
    health_checker = monitoring.HealthChecker(client)

    def broken_memory():
        raise RuntimeError("memory error")

    monkeypatch.setattr(monitoring.psutil, "virtual_memory", broken_memory)
    monkeypatch.setattr(monitoring.psutil, "cpu_percent", lambda interval=None: 0.0)

    result = asyncio.run(health_checker.check_health())
    assert result.healthy is False
    assert result.browser_status == "error"
    assert "memory error" in result.last_error


@pytest.mark.asyncio
async def test_request_timer_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bool, float]] = []

    def record(success: bool, response_time: float) -> None:
        calls.append((success, response_time))

    monkeypatch.setattr(monitoring.metrics_collector, "record_request", record)

    async with monitoring.request_timer():
        pass

    assert calls[0][0] is True

    with pytest.raises(RuntimeError):
        async with monitoring.request_timer():
            raise RuntimeError("boom")

    assert calls[1][0] is False


def test_setup_monitoring_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)
    called = {}

    def fake_start_http_server(port: int) -> None:
        called["port"] = port

    monitoring.start_http_server = fake_start_http_server  # type: ignore[assignment]
    monitoring.setup_monitoring(port=9100)
    assert called["port"] == 9100


def test_setup_monitoring_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(monitoring.logger, "warning", lambda message: messages.append(message))

    monitoring.setup_monitoring(port=1234)

    assert any("not available" in message for message in messages)


@pytest.mark.asyncio
async def test_periodic_health_check_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    check = AsyncMock()
    update = MagicMock()

    monkeypatch.setattr(monitoring.health_checker, "check_health", check)
    monkeypatch.setattr(monitoring.metrics_collector, "update_system_metrics", update)
    monkeypatch.setattr(monitoring.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    check.assert_awaited()
    update.assert_called()


@pytest.mark.asyncio
async def test_periodic_health_check_logs_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    error = RuntimeError("health failed")
    check = AsyncMock(side_effect=error)
    update = MagicMock()
    log_messages: list[str] = []

    monkeypatch.setattr(monitoring.health_checker, "check_health", check)
    monkeypatch.setattr(monitoring.metrics_collector, "update_system_metrics", update)
    monkeypatch.setattr(monitoring.logger, "error", lambda message: log_messages.append(message))
    monkeypatch.setattr(monitoring.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    check.assert_awaited()
    update.assert_not_called()
    assert any("health failed" in message for message in log_messages)


def test_setup_logging_configures_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    class DummyLogger:
        def remove(self) -> None:
            calls.append(("remove", None))

        def add(self, *args, **kwargs):
            calls.append(("add", kwargs.get("level")))
            return 1

    dummy = DummyLogger()
    monkeypatch.setattr(monitoring, "logger", dummy)

    monitoring.setup_logging(debug=True)
    monitoring.setup_logging(debug=False)

    levels = [level for action, level in calls if action == "add"]
    assert "DEBUG" in levels
    assert levels.count("INFO") >= 2  # stdout plus file handlers
