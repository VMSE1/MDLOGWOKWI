"""Ядро сервера: приём измерений от модулей -> координаты -> треки -> статус «свой/чужой»."""
import hmac
import math
import time
from collections import deque
from typing import Dict, List, Optional

from .db import Registry, make_mac
from .geo import latlon_to_xy, xy_to_latlon, polar_to_xy, trilaterate

GATE_M = 30.0        # окно склейки эха и ответа по положению
MERGE_ID_M = 120.0   # один ID в пределах этого расстояния - тот же трек
TRACK_TTL = 12.0     # через сколько секунд без данных трек удаляется
PENDING_S = 6.0      # столько ждём ответ, потом «не подтверждено»
OBS_TTL = 4.0        # актуальность измерения дальности для трилатерации
SAME_TX_S = 3.0      # один и тот же пакет, услышанный разными станциями

STATUS_TEXT = {
    "own": "СВОЙ", "denied": "ЧУЖОЙ: нет допуска", "foreign": "ЧУЖОЙ: ID не в реестре",
    "spoof": "ПОДМЕНА ID", "pending": "ожидание ответа", "unconfirmed": "НЕ ПОДТВЕРЖДЕНО",
}
LEVEL = {"own": "ok", "pending": "info", "unconfirmed": "warn",
         "denied": "bad", "foreign": "bad", "spoof": "bad"}


class Track:
    def __init__(self, tid: int, x: float, y: float, now: float):
        self.tid, self.x, self.y = tid, x, y
        self.id: Optional[str] = None
        self.verdict: Optional[str] = None
        self.cls = "good"
        self.quality = "polar"
        self.first = self.last = now
        self.trail = [(round(x, 1), round(y, 1))]
        self.status: Optional[str] = None


class Engine:
    def __init__(self, db_path: str, clock=time.time):
        self.reg = Registry(db_path)
        self.clock = clock
        self.reset()

    def reset(self):
        self.modules: Dict[str, dict] = {}
        self.tracks: List[Track] = []
        self.range_obs: Dict[str, dict] = {}
        self.last_pos: Dict[str, tuple] = {}
        self.last_counter: Dict[str, tuple] = {}
        self._lastlog: Dict[tuple, float] = {}
        self.events = deque(maxlen=80)
        self._tid = 0

    def log(self, text: str, level: str = "info"):
        self.events.append({"t": time.strftime("%H:%M:%S", time.localtime(self.clock())),
                            "text": text, "level": level})

    # ---------- приём ----------
    def ingest(self, p: dict):
        now = self.clock()
        mid, pose = p["module_id"], p["pose"]
        mx, my = latlon_to_xy(pose["lat"], pose["lon"])
        hd = pose.get("heading_deg", 0.0)
        if mid not in self.modules:
            self.log(f"Модуль {mid} подключился", "info")
        self.modules[mid] = {"id": mid, "x": mx, "y": my, "heading": hd,
                             "lat": pose["lat"], "lon": pose["lon"], "last_seen": now}
        for d in p["detections"]:
            self._detection(mid, mx, my, hd, d, now)

    def _verify(self, d: dict, now: float) -> str:
        if not d.get("crc_ok", True):
            return "crc"
        did = d.get("id")
        row = self.reg.get(did)
        if row is None:
            return "unknown"
        if not d.get("mac") or d.get("counter") is None:
            return "spoof"
        if not hmac.compare_digest(d["mac"], make_mac(row["key"], did, d["counter"])):
            return "spoof"
        last = self.last_counter.get(did)
        if last:
            lc, lt = last
            if d["counter"] < lc or (d["counter"] == lc and now - lt > SAME_TX_S):
                return "replay"
        if not last or d["counter"] > last[0]:
            self.last_counter[did] = (d["counter"], now)
        return "ok"

    def _locate(self, mid, mx, my, hd, d, now, verdict=None):
        if d.get("az_deg") is not None:
            x, y = polar_to_xy(mx, my, d["range_m"], hd, d["az_deg"])
            return x, y, "polar"
        if d["kind"] == "transponder" and d.get("id"):
            key = d["id"] + ("#bad" if verdict in ("spoof", "replay") else "")  # подделку не смешиваем с настоящим
            obs = self.range_obs.setdefault(key, {})
            obs[mid] = (mx, my, d["range_m"], now)
            fresh = [v[:3] for v in obs.values() if now - v[3] <= OBS_TTL]
            if len(fresh) >= 2:
                pos, q, _ = trilaterate(fresh, self.last_pos.get(key))
                self.last_pos[key] = pos
                return pos[0], pos[1], q
        return None  # эхо без угла однозначно не локализуется (нужна ассоциация, см. README)

    def _detection(self, mid, mx, my, hd, d, now):
        verdict = None
        if d["kind"] == "transponder":
            verdict = self._verify(d, now)
            if verdict == "crc":
                self.log(f"{mid}: ответ с ошибкой CRC, отброшен", "warn")
                return
            if verdict in ("spoof", "replay") and now - self._lastlog.get((d.get("id"), verdict), -99) > 10:
                self._lastlog[(d.get("id"), verdict)] = now
                self.log(f"{mid}: {'неверная подпись' if verdict == 'spoof' else 'повтор старого пакета'} для {d.get('id')}", "bad")
        loc = self._locate(mid, mx, my, hd, d, now, verdict)
        if loc is None:
            return
        self._update_track(loc[0], loc[1], loc[2],
                           d.get("id") if d["kind"] == "transponder" else None, verdict, now)

    # ---------- треки ----------
    def _update_track(self, x, y, q, did, verdict, now):
        self.tracks = [t for t in self.tracks if now - t.last <= TRACK_TTL]
        dist = lambda t: math.hypot(t.x - x, t.y - y)
        t = None
        if did:
            cls = "bad" if verdict in ("spoof", "replay") else "good"
            same = [t for t in self.tracks if t.id == did and t.cls == cls and dist(t) <= MERGE_ID_M]
            if same:
                t = min(same, key=dist)
            else:
                anon = [t for t in self.tracks if t.id is None and dist(t) <= GATE_M]
                t = min(anon, key=dist) if anon else None
                if t is None:
                    t = self._new(x, y, now)
            t.id, t.verdict, t.cls = did, verdict, cls
        else:
            near = [t for t in self.tracks if dist(t) <= GATE_M]
            t = min(near, key=dist) if near else self._new(x, y, now)
        t.x, t.y = 0.5 * t.x + 0.5 * x, 0.5 * t.y + 0.5 * y
        t.quality, t.last = q, now
        t.trail.append((round(t.x, 1), round(t.y, 1)))
        del t.trail[:-30]

    def _new(self, x, y, now) -> Track:
        self._tid += 1
        t = Track(self._tid, x, y, now)
        self.tracks.append(t)
        return t

    def _status(self, t: Track, now: float) -> str:
        if t.id:
            if t.verdict in ("spoof", "replay"):
                return "spoof"
            if t.verdict == "unknown":
                return "foreign"
            row = self.reg.get(t.id)
            return "own" if row and row["allowed"] else "denied"
        return "unconfirmed" if now - t.first > PENDING_S else "pending"

    # ---------- выдача интерфейсу ----------
    def snapshot(self) -> dict:
        now = self.clock()
        self.tracks = [t for t in self.tracks if now - t.last <= TRACK_TTL]
        out = []
        for t in self.tracks:
            st = self._status(t, now)
            label = t.id or f"объект #{t.tid}"
            if st != t.status:
                self.log(f"{label}: {STATUS_TEXT[st]}", LEVEL[st])
                t.status = st
            row = self.reg.get(t.id)
            lat, lon = xy_to_latlon(t.x, t.y)
            out.append({"tid": t.tid, "label": label, "id": t.id, "x": round(t.x, 1), "y": round(t.y, 1),
                        "lat": round(lat, 6), "lon": round(lon, 6), "status": st,
                        "status_text": STATUS_TEXT[st], "quality": t.quality,
                        "age_s": round(now - t.last, 1), "trail": t.trail,
                        "owner": row["owner"] if row else None,
                        "mission": row["mission"] if row else None})
        mods = [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items() if k != "last_seen"}
                for m in self.modules.values()]
        return {"modules": mods, "tracks": out, "registry": self.reg.all(),
                "events": list(self.events)[-40:]}
