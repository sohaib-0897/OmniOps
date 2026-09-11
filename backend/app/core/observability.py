import json, logging, threading, time, uuid
from collections import Counter
from fastapi import Request
_lock = threading.Lock(); _requests = Counter(); _latency_sum = Counter(); _sse = 0
logger = logging.getLogger("omniops.request")
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)
logger.propagate = False
class _Gauge:
    def inc(self):
        global _sse
        with _lock: _sse += 1
    def dec(self):
        global _sse
        with _lock: _sse = max(0, _sse - 1)
SSE_CONNECTIONS = _Gauge()
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4()); request.state.request_id = request_id; started = time.monotonic()
    try: response = await call_next(request); code = response.status_code
    except Exception:
        code = 500; logger.exception(json.dumps({"event_type": "request.failed", "request_id": request_id, "method": request.method, "path": request.url.path})); raise
    finally:
        route = request.scope.get("route"); template = getattr(route, "path", request.url.path); elapsed = time.monotonic() - started
        with _lock: _requests[(request.method, template, code)] += 1; _latency_sum[(request.method, template)] += elapsed
    response.headers.update({"X-Request-ID": request_id, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), microphone=(), geolocation=()", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
    logger.info(json.dumps({"event_type": "request.completed", "request_id": request_id, "method": request.method, "path": template, "status": code, "duration_ms": round(elapsed * 1000, 2)})); return response
def prometheus_metrics() -> str:
    lines = ["# HELP omniops_http_requests_total HTTP requests", "# TYPE omniops_http_requests_total counter"]
    with _lock:
        for (method, route, code), count in _requests.items(): lines.append(f'omniops_http_requests_total{{method="{method}",route="{route}",status="{code}"}} {count}')
        lines += ["# HELP omniops_http_request_duration_seconds_sum HTTP request latency sum", "# TYPE omniops_http_request_duration_seconds_sum counter"]
        for (method, route), value in _latency_sum.items(): lines.append(f'omniops_http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {value}')
        lines += ["# HELP omniops_sse_connections Active SSE connections", "# TYPE omniops_sse_connections gauge", f"omniops_sse_connections {_sse}"]
    return "\n".join(lines) + "\n"
