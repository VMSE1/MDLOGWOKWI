"""Мост «плата -> сервер» MADILOG.

Читает строки FRAME,<кадр hex>,<дальность м> из порта платы (USB, Wokwi или stdin),
разбирает кадр тем же кодом, что симулятор (simulation/sim/packet.py),
и шлёт измерение в API: POST <server>/api/v1/detections.

Примеры (запускать из корня репозитория):
  python tools/serial_bridge.py --port COM5                         # настоящая Nucleo по USB (Windows)
  python tools/serial_bridge.py --port /dev/ttyACM0                 # то же на Linux
  python tools/serial_bridge.py --port rfc2217://localhost:4000     # плата в Wokwi (VS Code)
  python tools/serial_bridge.py --port COM5 --server http://203.0.113.10:8000   # сервер ребят по статическому IP
  python tools/serial_bridge.py --stdin --dry-run < tools/frames_example.txt   # без платы и без сервера

Строки, которые не начинаются с FRAME, пропускаются (например, приветствие платы "# ...").
"""
import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "simulation"))
from sim import packet  # noqa: E402


def parse_line(line: str):
    """'FRAME,<hex>,<м>' -> (кадр в байтах, дальность). None, если строка не кадр."""
    parts = line.strip().split(",")
    if len(parts) != 3 or parts[0] != "FRAME":
        return None
    try:
        return bytes.fromhex(parts[1]), float(parts[2])
    except ValueError:
        return None


def to_detection(frame: bytes, range_m: float, az_deg):
    """Кадр -> одно измерение в формате API. Битый кадр уходит с crc_ok=false, сервер его отбросит и запишет в журнал."""
    det = {"kind": "transponder", "range_m": range_m, "az_deg": az_deg}
    rx = packet.decode(frame)
    if rx is None:
        det["crc_ok"] = False
    else:
        det.update(crc_ok=True, id=rx["id"], counter=rx["counter"], mac=rx["mac"], depth_m=rx["depth_m"])
    return det


def post(url: str, payload: dict) -> str:
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.read().decode()


def lines_from(args):
    if args.stdin:
        yield from sys.stdin
        return
    import serial  # pip install pyserial
    port = serial.serial_for_url(args.port, baudrate=args.baud, timeout=2)
    print(f"[bridge] порт {args.port} открыт, {args.baud} бод")
    while True:
        raw = port.readline()
        if raw:
            yield raw.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser(description="Мост плата -> сервер MADILOG")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="COM5, /dev/ttyACM0 или rfc2217://localhost:4000")
    src.add_argument("--stdin", action="store_true", help="читать строки из stdin (проверка без платы)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--server", default="http://127.0.0.1:8000", help="адрес сервера, например http://203.0.113.10:8000")
    ap.add_argument("--module", default="BUOY-01", help="ID станции, от имени которой идут измерения")
    ap.add_argument("--lat", type=float, default=60.0, help="координаты станции (демо-акватория)")
    ap.add_argument("--lon", type=float, default=28.99)
    ap.add_argument("--heading", type=float, default=0.0)
    ap.add_argument("--az", type=float, default=45.0,
                    help="азимут на объект, град. У платы угла нет: при одной станции сервер без него "
                         "не поставит точку на карту. Значение условное. --az -1 = не слать угол")
    ap.add_argument("--dry-run", action="store_true", help="не отправлять, только печатать JSON")
    args = ap.parse_args()

    url = args.server.rstrip("/") + "/api/v1/detections"
    az = None if args.az == -1 else args.az
    sent = 0
    for line in lines_from(args):
        parsed = parse_line(line)
        if parsed is None:
            continue
        frame, range_m = parsed
        payload = {"module_id": args.module,
                   "pose": {"lat": args.lat, "lon": args.lon, "heading_deg": args.heading},
                   "sound_speed_mps": 1500.0,
                   "detections": [to_detection(frame, range_m, az)]}
        det = payload["detections"][0]
        info = f"{det.get('id', '?')} #{det.get('counter', '?')} R={range_m} м crc={'ok' if det['crc_ok'] else 'BAD'}"
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False))
            continue
        try:
            post(url, payload)
            sent += 1
            print(f"[bridge] -> {url}: {info}")
        except Exception as e:  # сервер не поднят или нет сети: не падаем, ждём следующий кадр
            print(f"[bridge] ошибка отправки ({info}): {e}")


if __name__ == "__main__":
    main()
