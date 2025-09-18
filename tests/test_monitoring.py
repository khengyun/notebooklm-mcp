import asyncio
from types import SimpleNamespace

import pytest

from notebooklm_mcp import monitoring


class DummyPsutil:
    def __init__(self, memory_percent=10.0, cpu_percent=20.0):
        self._memory_percent = memory_percent
        self._cpu_percent = cpu_percent

    def virtual_memory(self):
        return SimpleNamespace(percent=self._memory_percent, used=1024)

    def cpu_percent(self, interval=None):  # pragma: no cover - interval unused
        return self._cpu_percent


def test_metrics_collector_record_request():
    collector = monitoring.MetricsCollector()
    collector.record_request(True, 0.5)
    collector.record_request(False, 0.25)

    metrics = collector.get_metrics()
    assert metrics["requests_total"] == 2
    assert metrics["requests_success"] == 1
    assert metrics["requests_failed"] == 1
    assert metrics["average_response_time"] > 0


def test_metrics_collector_update_active_sessions():
    collector = monitoring.MetricsCollector()
    collector.update_active_sessions(3)
    assert collector.get_metrics()["active_sessions"] == 3


def test_metrics_collector_browser_and_auth():
    collector = monitoring.MetricsCollector()
    collector.record_browser_restart()
    collector.record_auth_failure()
    metrics = collector.get_metrics()
    assert metrics["browser_restarts"] == 1
    assert metrics["authentication_failures"] == 1


def test_metrics_collector_with_prometheus(monkeypatch):
    class DummyMetric:
        def __init__(self, *_args, **_kwargs):
            self.events = []

        def inc(self):
            self.events.append(("inc", None))

        def observe(self, value):
            self.events.append(("observe", value))

        def set(self, value):
            self.events.append(("set", value))

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(monitoring, "Counter", DummyMetric, raising=False)
    monkeypatch.setattr(monitoring, "Gauge", DummyMetric, raising=False)
    monkeypatch.setattr(monitoring, "Histogram", DummyMetric, raising=False)

    collector = monitoring.MetricsCollector()
    collector.record_request(True, 0.5)
    collector.record_request(False, 0.25)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(3)

    monkeypatch.setattr(
        monitoring, "psutil", DummyPsutil(memory_percent=50.0, cpu_percent=45.0)
    )
    collector.update_system_metrics()

    assert collector.requests_counter.events
    assert any(event == ("set", 3) for event in collector.active_sessions_gauge.events)
    assert collector.memory_usage_gauge.events[-1][0] == "set"


@pytest.mark.asyncio
async def test_request_timer_success(monkeypatch):
    calls = []

    class DummyCollector:
        def record_request(self, success, response_time):
            calls.append((success, response_time))

    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())

    async with monitoring.request_timer():
        await asyncio.sleep(0)

    assert calls and calls[0][0] is True
    assert calls[0][1] >= 0


@pytest.mark.asyncio
async def test_request_timer_failure(monkeypatch):
    calls = []

    class DummyCollector:
        def record_request(self, success, response_time):
            calls.append((success, response_time))

    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())

    with pytest.raises(RuntimeError):
        async with monitoring.request_timer():
            raise RuntimeError("boom")

    assert calls and calls[0][0] is False


@pytest.mark.asyncio
async def test_health_checker_reports_status(monkeypatch):
    dummy_psutil = DummyPsutil(memory_percent=40.0, cpu_percent=30.0)
    monkeypatch.setattr(monitoring, "psutil", dummy_psutil)

    client = SimpleNamespace(
        driver=SimpleNamespace(
            current_url="https://notebooklm.google.com/notebook/123"
        ),
        _is_authenticated=True,
    )

    checker = monitoring.HealthChecker(client)
    monitoring.metrics_collector.start_time = asyncio.get_event_loop().time()

    result = await checker.check_health()
    assert result.healthy is True
    assert result.browser_status == "healthy"
    assert result.authentication_status == "authenticated"


@pytest.mark.asyncio
async def test_health_checker_not_started(monkeypatch):
    dummy_psutil = DummyPsutil(memory_percent=20.0, cpu_percent=10.0)
    monkeypatch.setattr(monitoring, "psutil", dummy_psutil)

    client = SimpleNamespace(driver=None, _is_authenticated=False)
    checker = monitoring.HealthChecker(client)
    monitoring.metrics_collector.start_time = asyncio.get_event_loop().time()

    result = await checker.check_health()
    assert result.browser_status == "not_started"
    assert result.authentication_status == "not_authenticated"


def test_setup_monitoring_with_prometheus(monkeypatch):
    recorded = {}

    def fake_start(port):
        recorded["port"] = port

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(monitoring, "start_http_server", fake_start, raising=False)

    monitoring.setup_monitoring(port=8123)
    assert recorded["port"] == 8123


def test_setup_monitoring_without_prometheus(monkeypatch):
    messages = []

    class DummyLogger:
        def warning(self, message):
            messages.append(("warning", message))

        def info(self, _message):  # pragma: no cover - unused
            pass

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(monitoring, "logger", DummyLogger())

    monitoring.setup_monitoring(port=9001)

    assert any(
        "metrics will not be exported" in message for _level, message in messages
    )


@pytest.mark.asyncio
async def test_periodic_health_check_handles_cancel(monkeypatch):
    calls = {
        "health": 0,
        "metrics": 0,
    }

    class DummyChecker:
        async def check_health(self):
            calls["health"] += 1

    class DummyCollector:
        def update_system_metrics(self):
            calls["metrics"] += 1

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(monitoring, "health_checker", DummyChecker())
    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    assert calls["health"] == 1
    assert calls["metrics"] == 1


@pytest.mark.asyncio
async def test_periodic_health_check_logs_error(monkeypatch):
    class BrokenChecker:
        async def check_health(self):
            raise RuntimeError("bad")

    class DummyCollector:
        def update_system_metrics(self):
            pass

    messages = []

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(monitoring, "health_checker", BrokenChecker())
    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        monitoring, "logger", SimpleNamespace(error=lambda msg: messages.append(msg))
    )

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    assert any("Periodic health check failed" in message for message in messages)


def test_setup_logging_configures_handlers(monkeypatch, tmp_path):
    calls = []

    class DummyLogger:
        def remove(self):
            calls.append(("remove", None))

        def add(self, *args, **kwargs):
            calls.append(("add", args, kwargs))

    monkeypatch.setattr(monitoring, "logger", DummyLogger())
    monkeypatch.chdir(tmp_path)

    monitoring.setup_logging(debug=True)

    actions = [entry[0] for entry in calls]
    assert actions.count("remove") == 1
    # Expect multiple add calls: stdout + log files
    assert actions.count("add") >= 3


def test_setup_logging_info_level(monkeypatch, tmp_path):
    calls = []

    class DummyLogger:
        def remove(self):
            calls.append(("remove", None))

        def add(self, *args, **kwargs):
            calls.append(("add", args, kwargs))

    monkeypatch.setattr(monitoring, "logger", DummyLogger())
    monkeypatch.chdir(tmp_path)

    monitoring.setup_logging(debug=False)

    first_add = next(entry for entry in calls if entry[0] == "add")
    assert first_add[2]["level"] == "INFO"


@pytest.mark.asyncio
async def test_health_checker_handles_exception(monkeypatch):
    class BrokenPsutil:
        def virtual_memory(self):
            raise RuntimeError("fail")

        def cpu_percent(self, interval=None):
            return 0

    monkeypatch.setattr(monitoring, "psutil", BrokenPsutil())
    checker = monitoring.HealthChecker()
    result = await checker.check_health()
    assert result.healthy is False
    assert result.browser_status == "error"
