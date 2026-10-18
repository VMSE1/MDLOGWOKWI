"""Генератор: имитирует плавучие модули (буи и корабль) и подводные аппараты.

Модуль -> POST /api/v1/detections. Запуск из корня проекта:
  python -m sim.generator --scenario mixed
Сценарии: own | unknown | silent | spoof | mixed
  --range-only   модули без угловой решётки (только дальность; позицию даёт трилатерация)
  --scan-khz 150 частота скан-импульса (влияет на дальность эхо-обнаружения)
"""
import argparse
import json
import math
import random
import time
import urllib.request
from typing import List, Optional

from server.db import make_mac
from server.geo import xy_to_latlon
from . import channel, packet

# (id, x, y, курс). Корабль - тот же модуль, закреплённый на корпусе.
MODULES = [("BUOY-01", -300.0, 0.0, 0.0), ("BUOY-02", 300.0, 0.0, 0.0), ("SHIP-01", 0.0, -250.0, 90.0)]
KEYS = {"MD-0427": "key-0427", "MD-0311": "key-0311", "MD-0588": "key-0588"}  # как в демо-реестре


class Drone:
    def __init__(self, did: Optional[str], x, y, vx, vy, tx=True, key=None, spoof=False):
        self.id, self.x, self.y, self.vx, self.vy = did, x, y, vx, vy
        self.tx, self.spoof = tx, spoof
        self.key = key or (KEYS.get(did) if did else None) or "key-unregistered"
        self.counter = random.randint(100, 5000)
        self.depth = random.uniform(20, 60)

    def step(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if abs(self.x) > 600:
            self.vx = -self.vx
        if self.y > 550 or self.y < -450:
            self.vy = -self.vy


def build(scn: str) -> List[Drone]:
    d = []
    if scn in ("own", "mixed"):
        d += [Drone("MD-0427", -200, 200, 1.2, 0.0), Drone("MD-0311", 250, 150, -0.8, 0.5)]
    if scn in ("unknown", "mixed"):
        d.append(Drone("MD-9913", 100, 300, -0.6, -0.3))
    if scn in ("silent", "mixed"):
        d.append(Drone(None, -260, 70, 0.3, 0.1, tx=False))  # молчащий объект рядом с BUOY-01
    if scn in ("spoof", "mixed"):
        d.append(Drone("MD-0427", -100, 350, 0.8, -0.2, spoof=True))  # чужой, выдаёт себя за MD-0427
    return d


def post(url: str, payload: dict):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=3).read()


def run(url, scn, rate, duration, range_only, scan_khz, seed):
    rng = random.Random(seed)
    drones = build(scn)
    t0 = time.time()
    tick = 0
    print(f"[gen] сценарий={scn}, модулей={len(MODULES)}, объектов={len(drones)}, "
          f"угол={'нет' if range_only else 'есть'}, скан={scan_khz} кГц")
    while duration == 0 or time.time() - t0 < duration:
        tick += 1
        for dr in drones:
            dr.step(1.0 / rate)
            if dr.tx:
                dr.counter += 1
        for mid, mx, my, hd in MODULES:
            lat, lon = xy_to_latlon(mx, my)
            dets = []
            for dr in drones:
                r = math.hypot(dr.x - mx, dr.y - my)
                bearing = math.degrees(math.atan2(dr.x - mx, dr.y - my))
                az = (bearing - hd + 180) % 360 - 180
                r_m = max(1.0, r + rng.gauss(0, 0.5 + 0.004 * r))
                az_m = None if range_only else round(az + rng.gauss(0, 2.0), 1)
                if rng.random() < channel.echo_detect_prob(r, scan_khz):
                    dets.append({"kind": "echo", "range_m": round(r_m, 1), "az_deg": az_m,
                                 "snr_db": round(channel.echo_signal_excess_db(r, scan_khz), 1)})
                if dr.tx:
                    did = dr.id
                    mac = (rng.randbytes(4).hex() if dr.spoof else make_mac(dr.key, did, dr.counter))
                    frame = packet.encode(did, dr.counter, dr.depth, 0, mac)
                    ber = channel.bit_error_rate(r)
                    if channel.packet_success(r) < 0.01:
                        continue  # слишком далеко - модуль не слышит
                    rx = packet.decode(packet.flip_bits(frame, ber, rng))
                    det = {"kind": "transponder", "range_m": round(r_m, 1), "az_deg": az_m,
                           "crc_ok": rx is not None}
                    if rx:
                        det.update(id=rx["id"], counter=rx["counter"], mac=rx["mac"], depth_m=rx["depth_m"])
                    dets.append(det)
            if dets:
                try:
                    post(url, {"module_id": mid, "pose": {"lat": lat, "lon": lon, "heading_deg": hd},
                               "sound_speed_mps": 1500.0, "detections": dets})
                except Exception as e:  # сервер ещё не поднят
                    print("[gen] ошибка отправки:", e)
        time.sleep(1.0 / rate)
    print("[gen] готово")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/api/v1/detections")
    ap.add_argument("--scenario", default="mixed", choices=["own", "unknown", "silent", "spoof", "mixed"])
    ap.add_argument("--rate", type=float, default=1.0, help="циклов в секунду")
    ap.add_argument("--duration", type=float, default=0, help="секунд, 0 = бесконечно")
    ap.add_argument("--range-only", action="store_true")
    ap.add_argument("--scan-khz", type=float, default=150.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    run(a.url, a.scenario, a.rate, a.duration, a.range_only, a.scan_khz, a.seed)
