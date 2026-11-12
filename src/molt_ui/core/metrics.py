"""Evaluate the bundled dashboard's metrics without a Prometheus server.

Rates use observed samples in a rolling window, with counter reset correction.
They are local estimates rather than a full PromQL evaluator.
"""

from collections import defaultdict, deque
import math
import re


SAMPLE_LIMIT = 1800
SERIES_LIMIT = 2000
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')
SAMPLE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+(\S+)')


def parse_exposition(text: str, names: set[str]) -> dict:
    """Read the relevant Prometheus text samples, including escaped label values."""
    result = {}
    for line in text.splitlines():
        match = SAMPLE.match(line)
        if not match or match[1] not in names:
            continue
        try:
            value = float(match[3])
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        labels = tuple(sorted((item[1], re.sub(r'\\([\\n"])',
            lambda m: '\n' if m[1] == 'n' else m[1], item[2]))
            for item in LABEL.finditer(match[2] or '')))
        result[(match[1], labels)] = value
        if len(result) >= SERIES_LIMIT:
            break
    return result


def counter_rate(points: list, now: float, window: float) -> float | None:
    selected = [(t, v) for t, v in points if now - window < t <= now]
    if len(selected) < 2 or selected[-1][0] <= selected[0][0]:
        return None
    increase = sum(current - previous if current >= previous else current
                   for (_, previous), (_, current) in zip(selected, selected[1:]))
    return increase / (selected[-1][0] - selected[0][0])


def histogram_quantile(buckets: dict[float, float], quantile: float) -> float | None:
    ordered = sorted(buckets.items())
    if len(ordered) < 2 or ordered[-1][0] != math.inf or ordered[-1][1] <= 0:
        return None
    rank = quantile * ordered[-1][1]
    lower, previous = 0.0, 0.0
    for upper, cumulative in ordered:
        cumulative = max(previous, cumulative)
        if cumulative >= rank:
            if upper == math.inf:
                return lower
            if cumulative == previous:
                return upper
            return lower + (upper - lower) * (rank - previous) / (cumulative - previous)
        lower, previous = upper, cumulative
    return None


class MetricsEngine:
    def __init__(self, panels: list[dict]):
        self.panels = panels
        self.names = {panel['metric'] for panel in panels}
        self.history: dict[tuple, deque] = {}
        self.truncated = False

    def ingest(self, text: str, timestamp: float) -> dict:
        samples = parse_exposition(text, self.names)
        self.truncated |= len(samples) >= SERIES_LIMIT
        # Discard stale series, bounding both cardinality and rate-window storage.
        for key in list(self.history):
            points = self.history[key]
            while points and points[0][0] <= timestamp - 300:
                points.popleft()
            if not points:
                del self.history[key]
        for key, value in samples.items():
            if key not in self.history and len(self.history) >= SERIES_LIMIT:
                self.truncated = True
                continue
            self.history.setdefault(key, deque(maxlen=300)).append((timestamp, value))
        values = {}
        for panel in self.panels:
            groups = defaultdict(dict) if panel['kind'] == 'histogram' else defaultdict(float)
            for (name, pairs), value in samples.items():
                if name != panel['metric']:
                    continue
                labels = dict(pairs)
                if panel['category'] and labels.get('category') != panel['category']:
                    continue
                if panel['exclude_overall'] and labels.get('table') == 'overall':
                    continue
                if panel['kind'] in {'rate', 'histogram'}:
                    value = counter_rate(self.history.get((name, pairs), ()), timestamp,
                                         300 if panel['kind'] == 'histogram' else 60)
                    if value is None:
                        continue
                group = tuple((key, val) for key, val in pairs
                              if key != 'le' and (panel['group_by'] is None or key in panel['group_by']))
                if panel['kind'] == 'histogram':
                    try:
                        groups[group][float(labels['le'])] = value
                    except (KeyError, ValueError):
                        continue
                else:
                    groups[group] += value
            series = []
            for group, value in sorted(groups.items()):
                labels = dict(group)
                if panel['kind'] == 'histogram':
                    for quantile in (0.5, 0.75, 0.9, 0.99):
                        number = histogram_quantile(value, quantile)
                        if number is not None:
                            series.append({'labels': {**labels, 'quantile': f'p{quantile * 100:g}'}, 'value': number})
                else:
                    series.append({'labels': labels, 'value': value})
            values[panel['id']] = series
        return {'timestamp': timestamp, 'values': values}
