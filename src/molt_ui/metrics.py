"""Background HTTP collection of a running Molt process's Prometheus endpoint."""

from collections.abc import Callable
import ipaddress
import logging
from threading import Event, Lock, Thread
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from .core.metrics import MetricsEngine

logger = logging.getLogger(__name__)
SCRAPE_INTERVAL = 2


def metrics_endpoint(address: str) -> str:
    parsed = urlsplit('http://' + address)
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Metrics listen address must be a host:port address.')
    host, port = parsed.hostname, parsed.port
    if host is None or port is None or not 0 < port < 65536:
        raise ValueError('Metrics listen address must include a valid port.')
    if host in {'0.0.0.0', '::'}:
        host = '127.0.0.1' if host == '0.0.0.0' else '::1'
    try:
        if ipaddress.ip_address(host).version == 6:
            host = f'[{host}]'
    except ValueError:
        pass
    return f'http://{host}:{port}/metrics'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_metrics(endpoint: str) -> str:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(endpoint, headers={'Accept': 'text/plain; version=0.0.4'})
    with opener.open(request, timeout=1) as response:
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError('Metrics response exceeds 8 MiB.')
    return payload.decode('utf-8')


class MetricsCollector:
    def __init__(self, endpoint: str, panels: list[dict], save: Callable,
                 *, interval: float = SCRAPE_INTERVAL, fetch: Callable | None = None):
        self.endpoint = endpoint
        self.engine = MetricsEngine(panels)
        self.save = save
        self.interval = interval
        self.fetch = fetch or fetch_metrics
        self._done = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._state = {'endpoint': endpoint, 'status': 'waiting', 'error': None,
                       'interval': interval, 'truncated': False}

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self) -> None:
        with self._lock:
            if self._done.is_set():
                return
            self._thread = Thread(target=self._collect, daemon=True)
            self._thread.start()

    def _collect(self) -> None:
        while not self._done.is_set():
            frame = None
            try:
                text = self.fetch(self.endpoint)
                frame = self.engine.ingest(text, time.time())
                status = 'collecting' if any(frame['values'].values()) else 'waiting'
                error = None
            except (OSError, ValueError) as exc:
                status, error = 'unreachable', f'Cannot collect Molt metrics: {exc}'
                frame = {'timestamp': time.time(), 'values': {}}
            with self._lock:
                self._state.update(status=status, error=error, truncated=self.engine.truncated)
                state = dict(self._state)
            try:
                self.save(state, frame)
            except Exception:
                logger.exception('Could not save Molt metrics')
            if self._done.wait(self.interval):
                return

    def close(self) -> None:
        self._done.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            self._state['status'] = 'complete'
        try:
            self.save(self.state(), None)
        except Exception:
            logger.exception('Could not save final Molt metrics state')
