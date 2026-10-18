"""Геометрия: локальная система координат (метры), полярные -> XY, трилатерация."""
import math
from typing import List, Optional, Tuple

import numpy as np

M_PER_DEG = 111_320.0
LAT0, LON0 = 60.0, 29.0  # условное начало координат акватории (демо)


def latlon_to_xy(lat: float, lon: float) -> Tuple[float, float]:
    """x - на восток, y - на север (метры от начала координат)."""
    return ((lon - LON0) * M_PER_DEG * math.cos(math.radians(LAT0)), (lat - LAT0) * M_PER_DEG)


def xy_to_latlon(x: float, y: float) -> Tuple[float, float]:
    return (LAT0 + y / M_PER_DEG, LON0 + x / (M_PER_DEG * math.cos(math.radians(LAT0))))


def polar_to_xy(mx: float, my: float, rng: float, heading_deg: float, az_deg: float) -> Tuple[float, float]:
    """Позиция объекта по дальности и углу.
    heading_deg - курс модуля от севера по часовой, az_deg - азимут цели относительно носа модуля."""
    th = math.radians(heading_deg + az_deg)
    return mx + rng * math.sin(th), my + rng * math.cos(th)


def circle_intersections(p1, r1, p2, r2):
    (x1, y1), (x2, y2) = p1, p2
    d = math.hypot(x2 - x1, y2 - y1)
    if d == 0 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    xm, ym = x1 + a * (x2 - x1) / d, y1 + a * (y2 - y1) / d
    return [(xm + h * (y2 - y1) / d, ym - h * (x2 - x1) / d),
            (xm - h * (y2 - y1) / d, ym + h * (x2 - x1) / d)]


def trilaterate(obs: List[Tuple[float, float, float]],
                prev: Optional[Tuple[float, float]] = None):
    """obs = [(x, y, range), ...], не меньше двух станций.
    Возвращает ((x, y), quality, rms_residual_m).
    Две станции дают два зеркальных решения: берём ближайшее к прошлой позиции,
    а без истории - северное (неоднозначность, quality='trilat2')."""
    (x1, y1, r1), (x2, y2, r2) = obs[0], obs[1]
    cands = circle_intersections((x1, y1), r1, (x2, y2), r2)
    if len(obs) == 2:
        if not cands:
            t = r1 / (r1 + r2)
            return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t), "trilat2", 0.0
        if prev:
            p = min(cands, key=lambda q: math.hypot(q[0] - prev[0], q[1] - prev[1]))
        else:
            p = max(cands, key=lambda q: q[1])
        return p, "trilat2", 0.0

    def resid(p):
        return [math.hypot(p[0] - x, p[1] - y) - r for x, y, r in obs]

    if cands:
        start = min(cands, key=lambda q: sum(e * e for e in resid(q)))
    else:
        start = (sum(o[0] for o in obs) / len(obs), sum(o[1] for o in obs) / len(obs))
    p = np.array(start, dtype=float)
    for _ in range(20):
        J, f = [], []
        for x, y, r in obs:
            d = max(math.hypot(p[0] - x, p[1] - y), 1e-6)
            J.append([(p[0] - x) / d, (p[1] - y) / d])
            f.append(d - r)
        step, *_ = np.linalg.lstsq(np.array(J), -np.array(f), rcond=None)
        p = p + step
        if np.hypot(*step) < 1e-3:
            break
    res = resid(p)
    rms = math.sqrt(sum(e * e for e in res) / len(res))
    return (float(p[0]), float(p[1])), "trilat3", rms
