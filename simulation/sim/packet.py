"""Формат кадра ответа модуля (17 байт) + CRC16-CCITT.

  0     1     2..5      6..7       8..9        10     11..14    15..16
  0xA5 | ver | ID(u32) | counter | depth(дм) | flags | MAC(4Б) | CRC16
"""
import random
import struct
from typing import Optional

PRE, VER = 0xA5, 1
FRAME_LEN = 17


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def id_to_num(s: str) -> int:
    return int(s.split("-")[1])


def num_to_id(n: int) -> str:
    return f"MD-{n:04d}"


def encode(drone_id: str, counter: int, depth_m: float, flags: int, mac_hex: str) -> bytes:
    body = struct.pack(">BBIHHB", PRE, VER, id_to_num(drone_id), counter & 0xFFFF,
                       int(depth_m * 10) & 0xFFFF, flags) + bytes.fromhex(mac_hex)
    return body + struct.pack(">H", crc16(body))


def decode(frame: bytes) -> Optional[dict]:
    """None, если длина/преамбула/CRC не сошлись."""
    if len(frame) != FRAME_LEN or frame[0] != PRE:
        return None
    if crc16(frame[:-2]) != struct.unpack(">H", frame[-2:])[0]:
        return None
    _, ver, num, counter, depth_dm, flags = struct.unpack(">BBIHHB", frame[:11])
    return {"ver": ver, "id": num_to_id(num), "counter": counter,
            "depth_m": depth_dm / 10.0, "flags": flags, "mac": frame[11:15].hex()}


def flip_bits(frame: bytes, ber: float, rng: random.Random) -> bytes:
    """Имитация ошибок в канале: каждый бит инвертируется с вероятностью ber."""
    out = bytearray(frame)
    for i in range(len(out) * 8):
        if rng.random() < ber:
            out[i // 8] ^= 1 << (i % 8)
    return bytes(out)
