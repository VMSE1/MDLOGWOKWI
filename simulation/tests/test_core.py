import math
import random

from server import geo
from server.db import make_mac
from server.engine import Engine
from sim import channel, packet


def test_polar():
    x, y = geo.polar_to_xy(0, 0, 100, 90, 0)  # курс на восток, цель по носу
    assert abs(x - 100) < 1e-6 and abs(y) < 1e-6


def test_trilat3_exact():
    mods = [(-300, 0), (300, 0), (0, -250)]
    tgt = (50, 200)
    obs = [(mx, my, math.hypot(tgt[0] - mx, tgt[1] - my)) for mx, my in mods]
    (x, y), q, rms = geo.trilaterate(obs)
    assert q == "trilat3" and abs(x - 50) < 0.1 and abs(y - 200) < 0.1


def test_trilat2_prefers_prev():
    obs = [(-300, 0, math.hypot(350, 200)), (300, 0, math.hypot(250, 200))]
    (x, y), q, _ = geo.trilaterate(obs, prev=(50, -190))
    assert q == "trilat2" and y < 0


def test_packet_roundtrip_and_crc():
    f = packet.encode("MD-0427", 1234, 38.5, 0, "deadbeef")
    d = packet.decode(f)
    assert d["id"] == "MD-0427" and d["counter"] == 1234 and d["mac"] == "deadbeef" and d["depth_m"] == 38.5
    bad = bytearray(f); bad[3] ^= 0x01
    assert packet.decode(bytes(bad)) is None


def test_channel_monotonic():
    assert channel.packet_success(300) > channel.packet_success(1500)
    assert channel.echo_detect_prob(50) > channel.echo_detect_prob(400)
    assert channel.echo_detect_prob(250, 40) > channel.echo_detect_prob(250, 150)


def mk(tmp_path, t=[1000.0]):
    t[0] = 1000.0
    clock = lambda: t[0]
    return Engine(str(tmp_path / "r.db"), clock), t


def payload(did, counter, mac, r=300, az=45.0, crc=True, kind="transponder"):
    lat, lon = geo.xy_to_latlon(0, 0)
    det = {"kind": kind, "range_m": r, "az_deg": az, "crc_ok": crc}
    if kind == "transponder":
        det.update(id=did, counter=counter, mac=mac)
    return {"module_id": "BUOY-T", "pose": {"lat": lat, "lon": lon, "heading_deg": 0},
            "detections": [det]}


def statuses(e):
    return {t["label"]: t["status"] for t in e.snapshot()["tracks"]}


def test_own_foreign_spoof_replay(tmp_path):
    e, t = mk(tmp_path)
    e.ingest(payload("MD-0427", 10, make_mac("key-0427", "MD-0427", 10)))
    assert statuses(e)["MD-0427"] == "own"
    e.ingest(payload("MD-9913", 5, "00000000", az=200.0))
    assert statuses(e)["MD-9913"] == "foreign"
    e.ingest(payload("MD-0427", 11, "badbad00", az=300.0, r=400))
    assert "spoof" in statuses(e).values()
    t[0] += 1
    e.ingest(payload("MD-0427", 3, make_mac("key-0427", "MD-0427", 3)))  # старый счётчик
    assert any("повтор" in ev["text"] for ev in e.snapshot()["events"])


def test_denied_and_same_tx_other_station(tmp_path):
    e, _ = mk(tmp_path)
    e.ingest(payload("MD-0588", 7, make_mac("key-0588", "MD-0588", 7)))
    assert statuses(e)["MD-0588"] == "denied"
    # тот же пакет, услышанный второй станцией, не считается повтором
    e.ingest(payload("MD-0311", 9, make_mac("key-0311", "MD-0311", 9), az=100.0))
    e.ingest(payload("MD-0311", 9, make_mac("key-0311", "MD-0311", 9), az=100.0))
    assert statuses(e)["MD-0311"] == "own"


def test_silent_object_becomes_unconfirmed(tmp_path):
    e, t = mk(tmp_path)
    e.ingest(payload(None, None, None, r=80, az=10.0, kind="echo"))
    assert list(statuses(e).values()) == ["pending"]
    t[0] += 3; e.ingest(payload(None, None, None, r=80, az=10.0, kind="echo"))
    t[0] += 4; e.ingest(payload(None, None, None, r=80, az=10.0, kind="echo"))
    assert list(statuses(e).values()) == ["unconfirmed"]


def test_echo_merges_with_reply(tmp_path):
    e, _ = mk(tmp_path)
    e.ingest(payload(None, None, None, r=300, az=45.0, kind="echo"))
    e.ingest(payload("MD-0427", 20, make_mac("key-0427", "MD-0427", 20), r=305, az=45.5))
    s = statuses(e)
    assert s == {"MD-0427": "own"}  # одна цель, а не две


def test_http_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("MADILOG_DB", str(tmp_path / "h.db"))
    from fastapi.testclient import TestClient
    from server.app import app
    c = TestClient(app)
    lat, lon = geo.xy_to_latlon(0, 0)
    body = {"module_id": "B", "pose": {"lat": lat, "lon": lon, "heading_deg": 0},
            "detections": [{"kind": "transponder", "range_m": 200, "az_deg": 10, "id": "MD-0427",
                            "counter": 5, "mac": make_mac("key-0427", "MD-0427", 5)}]}
    assert c.post("/api/v1/detections", json=body).json()["ok"]
    st = c.get("/api/v1/state").json()
    assert st["tracks"] and len(st["registry"]) >= 3
    assert c.post("/api/v1/registry", json={"id": "MD-0777", "owner": "o", "mission": "m"}).json()["ok"]
    assert c.get("/").status_code == 200


def test_range_only_spoof_not_mixed(tmp_path):
    """Без угла: настоящий и поддельный MD-0427 не должны склеиваться в «призрак»."""
    e, t = mk(tmp_path)
    mods = [("A", -300, 0), ("B", 300, 0), ("C", 0, -250)]
    real, fake = (-200, 250), (-100, 350)
    for k in range(3):
        for mid, mx, my in mods:
            lat, lon = geo.xy_to_latlon(mx, my)
            c = 100 + k
            dets = [
                {"kind": "transponder", "range_m": math.hypot(real[0]-mx, real[1]-my), "id": "MD-0427",
                 "counter": c, "mac": make_mac("key-0427", "MD-0427", c)},
                {"kind": "transponder", "range_m": math.hypot(fake[0]-mx, fake[1]-my), "id": "MD-0427",
                 "counter": 9000 + k, "mac": "badbad00"}]
            e.ingest({"module_id": mid, "pose": {"lat": lat, "lon": lon, "heading_deg": 0}, "detections": dets})
        t[0] += 1
    tr = e.snapshot()["tracks"]
    own = [x for x in tr if x["status"] == "own"]
    spoof = [x for x in tr if x["status"] == "spoof"]
    assert len(own) == 1 and len(spoof) == 1
    assert math.hypot(own[0]["x"] - real[0], own[0]["y"] - real[1]) < 5
    assert math.hypot(spoof[0]["x"] - fake[0], spoof[0]["y"] - fake[1]) < 5
