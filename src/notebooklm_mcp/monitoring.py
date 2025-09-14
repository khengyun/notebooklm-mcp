"""
Monitoring and observability utilities for NotebookLM MCP Server
"""

import time
import psutil
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
from loguru import logger

try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class HealthStatus:
    """Health check status"""
    healthy: bool
    timestamp: float
    version: str
    uptime: float
    memory_usage: float
    cpu_usage: float
    browser_status: str
    authentication_status: str
    last_error: Optional[str] = None


@dataclass
class Metrics:
    """Application metrics"""
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    average_response_time: float = 0.0
    browser_restarts: int = 0
    authentication_failures: int = 0
    active_sessions: int = 0


class MetricsCollector:
    """Collects and manages application metrics"""
    
    def __init__(self):
        self.metrics = Metrics()
        self.start_time = time.time()
        self._request_times = []
        
        # Prometheus metrics (if available)
        if PROMETHEUS_AVAILABLE:
            self.requests_counter = Counter('notebooklm_requests_total', 'Total requests')
            self.requests_success_counter = Counter('notebooklm_requests_success_total', 'Successful requests')
            self.requests_failed_counter = Counter('notebooklm_requests_failed_total', 'Failed requests')
            self.response_time_histogram = Histogram('notebooklm_response_time_seconds', 'Response time')
            self.browser_restarts_counter = Counter('notebooklm_browser_restarts_total', 'Browser restarts')
            self.auth_failures_counter = Counter('notebooklm_auth_failures_total', 'Authentication failures')
            self.active_sessions_gauge = Gauge('notebooklm_active_sessions', 'Active sessions')
            self.memory_usage_gauge = Gauge('notebooklm_memory_usage_bytes', 'Memory usage')
            self.cpu_usage_gauge = Gauge('notebooklm_cpu_usage_percent', 'CPU usage')
    
    def record_request(self, success: bool, response_time: float):
        """Record a request"""
        self.metrics.requests_total += 1
        
        if success:
            self.metrics.requests_success += 1
            if PROMETHEUS_AVAILABLE:
                self.requests_success_counter.inc()
        else:
            self.metrics.requests_failed += 1
            if PROMETHEUS_AVAILABLE:
                self.requests_failed_counter.inc()
        
        self._request_times.append(response_time)
        if len(self._request_times) > 100:  # Keep last 100 requests
            self._request_times.pop(0)
        
        if self._request_times:
            self.metrics.average_response_time = sum(self._request_times) / len(self._request_times)
        
        if PROMETHEUS_AVAILABLE:
            self.requests_counter.inc()
            self.response_time_histogram.observe(response_time)
    
    def record_browser_restart(self):
        """Record browser restart"""
        self.metrics.browser_restarts += 1
        if PROMETHEUS_AVAILABLE:
            self.browser_restarts_counter.inc()
    
    def record_auth_failure(self):
        """Record authentication failure"""
        self.metrics.authentication_failures += 1
        if PROMETHEUS_AVAILABLE:
            self.auth_failures_counter.inc()
    
    def update_active_sessions(self, count: int):
        """Update active sessions count"""
        self.metrics.active_sessions = count
        if PROMETHEUS_AVAILABLE:
            self.active_sessions_gauge.set(count)
    
    def update_system_metrics(self):
        """Update system metrics"""
        if PROMETHEUS_AVAILABLE:
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_usage_gauge.set(memory.used)
            
            # CPU usage
            cpu_percent = psutil.cpu_percent()
            self.cpu_usage_gauge.set(cpu_percent)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return asdict(self.metrics)


class HealthChecker:
    """Health check functionality"""
    
    def __init__(self, client=None):
        self.client = client
        self.last_check = None
    
    async def check_health(self) -> HealthStatus:
        """Perform comprehensive health check"""
        start_time = time.time()
        
        try:
            # System metrics
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            uptime = time.time() - metrics_collector.start_time
            
            # Browser status
            browser_status = "unknown"
            if self.client and hasattr(self.client, 'driver'):
                if self.client.driver is not None:
                    try:
                        # Try to get current URL to test browser responsiveness
                        _ = self.client.driver.current_url
                        browser_status = "healthy"
                    except Exception as e:
                        browser_status = f"unhealthy: {str(e)[:50]}"
                else:
                    browser_status = "not_started"
            
            # Authentication status
            auth_status = "unknown"
            if self.client and hasattr(self.client, '_is_authenticated'):
                auth_status = "authenticated" if self.client._is_authenticated else "not_authenticated"
            
            # Overall health
            healthy = (
                browser_status == "healthy" and
                memory.percent < 90 and  # Memory usage < 90%
                cpu_percent < 90         # CPU usage < 90%
            )
            
            health = HealthStatus(
                healthy=healthy,
                timestamp=time.time(),
                version="1.0.0",  # TODO: Get from package
                uptime=uptime,
                memory_usage=memory.percent,
                cpu_usage=cpu_percent,
                browser_status=browser_status,
                authentication_status=auth_status
            )
            
            self.last_check = health
            logger.debug(f"Health check completed in {time.time() - start_time:.2f}s")
            
            return health
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return HealthStatus(
                healthy=False,
                timestamp=time.time(),
                version="1.0.0",
                uptime=0,
                memory_usage=0,
                cpu_usage=0,
                browser_status="error",
                authentication_status="error",
                last_error=str(e)
            )


# Global instances
metrics_collector = MetricsCollector()
health_checker = HealthChecker()


@asynccontextmanager
async def request_timer():
    """Context manager for timing requests"""
    start_time = time.time()
    success = False
    
    try:
        yield
        success = True
    except Exception:
        success = False
        raise
    finally:
        end_time = time.time()
        response_time = end_time - start_time
        metrics_collector.record_request(success, response_time)


def setup_monitoring(port: int = 8001):
    """Setup monitoring server"""
    if PROMETHEUS_AVAILABLE:
        logger.info(f"Starting Prometheus metrics server on port {port}")
        start_http_server(port)
    else:
        logger.warning("Prometheus client not available, metrics will not be exported")


async def periodic_health_check(interval: int = 30):
    """Run periodic health checks"""
    while True:
        try:
            await health_checker.check_health()
            metrics_collector.update_system_metrics()
        except Exception as e:
            logger.error(f"Periodic health check failed: {e}")
        
        await asyncio.sleep(interval)


# Logging configuration
def setup_logging(debug: bool = False):
    """Setup structured logging"""
    import sys
    
    # Remove default handler
    logger.remove()
    
    # Add structured logging
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    if debug:
        logger.add(sys.stdout, format=log_format, level="DEBUG")
    else:
        logger.add(sys.stdout, format=log_format, level="INFO")
    
    # Add file logging with rotation
    logger.add(
        "logs/notebooklm-mcp.log",
        format=log_format,
        level="INFO",
        rotation="100 MB",
        retention="7 days",
        compression="gz"
    )
    
    # Add error file
    logger.add(
        "logs/notebooklm-mcp-errors.log",
        format=log_format,
        level="ERROR",
        rotation="50 MB",
        retention="30 days"
    )