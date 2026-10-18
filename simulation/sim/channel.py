"""Простая модель гидроакустического канала.

ВАЖНО: параметры в PARAMS - допущения для демонстрации, а не измерения.
Их нужно заменить на реальные характеристики излучателя, шума и условий.
Результаты модели на слайдах подписывать как «расчёт / моделирование».
"""
import math

PARAMS = dict(
    comm_sl_db=160.0,     # уровень излучения ответа, дБ отн. 1 мкПа на 1 м (допущение)
    comm_nl_db=75.0,      # шум в полосе приёма, дБ (допущение, мелкое море, волнение)
    comm_extra_db=10.0,   # доп. потери: многолучёвость, поверхность, дно (допущение)
    comm_bw_hz=2000.0,    # полоса приёма
    comm_bitrate=200.0,   # скорость передачи, бит/с
    packet_bits=136,      # длина кадра: 17 байт
    echo_sl_db=190.0,     # уровень излучения скан-импульса (допущение)
    echo_nl_db=60.0,      # шум в полосе эхо-канала (допущение)
    echo_extra_db=5.0,
    echo_ts_db=-15.0,     # сила цели малого аппарата (допущение)
    echo_dt_db=10.0,      # порог обнаружения
)


def thorp_db_per_km(f_khz: float) -> float:
    """Затухание в морской воде по формуле Тёрпа, дБ/км."""
    f2 = f_khz ** 2
    return 0.11 * f2 / (1 + f2) + 44 * f2 / (4100 + f2) + 2.75e-4 * f2 + 0.003


def transmission_loss_db(r_m: float, f_khz: float) -> float:
    """Сферическое расхождение + поглощение."""
    return 20 * math.log10(max(r_m, 1.0)) + thorp_db_per_km(f_khz) * r_m / 1000.0


def comm_snr_db(r_m: float, f_khz: float = 35.0, p=PARAMS) -> float:
    return p["comm_sl_db"] - transmission_loss_db(r_m, f_khz) - p["comm_extra_db"] - p["comm_nl_db"]


def bit_error_rate(r_m: float, f_khz: float = 35.0, p=PARAMS) -> float:
    """Некогерентная FSK: Pb = 0.5*exp(-Eb/N0 / 2)."""
    ebn0_db = comm_snr_db(r_m, f_khz, p) + 10 * math.log10(p["comm_bw_hz"] / p["comm_bitrate"])
    return min(0.5, 0.5 * math.exp(-(10 ** (ebn0_db / 10)) / 2))


def packet_success(r_m: float, f_khz: float = 35.0, p=PARAMS) -> float:
    return (1 - bit_error_rate(r_m, f_khz, p)) ** p["packet_bits"]


def echo_signal_excess_db(r_m: float, f_khz: float = 150.0, p=PARAMS) -> float:
    """Активная гидролокация: путь туда-обратно, 2*TL."""
    return (p["echo_sl_db"] - 2 * transmission_loss_db(r_m, f_khz) - p["echo_extra_db"]
            + p["echo_ts_db"] - p["echo_nl_db"] - p["echo_dt_db"])


def echo_detect_prob(r_m: float, f_khz: float = 150.0, p=PARAMS) -> float:
    se = echo_signal_excess_db(r_m, f_khz, p)
    return 1.0 / (1.0 + math.exp(-se / 3.0))


def range_at(fn, level: float = 0.5, r_max: float = 6000.0) -> float:
    """Дальность, на которой функция fn(r) падает ниже level."""
    r = 1.0
    while r < r_max and fn(r) >= level:
        r += 1.0
    return r
