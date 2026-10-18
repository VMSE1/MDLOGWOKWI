"""Графики модели канала -> sim/out/channel.png. Запуск: python -m sim.plot_channel"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import channel

OUT = os.path.join(os.path.dirname(__file__), "out")


def main():
    os.makedirs(OUT, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    rs = list(range(10, 2001, 10))
    for f in (25, 35):
        ax[0].plot(rs, [100 * channel.packet_success(r, f) for r in rs], label=f"{f} кГц")
    ax[0].axhline(91, ls=":", c="gray")
    ax[0].set_title("Приём пакета ответа с ID (расчёт, параметры - допущения)")
    ax[0].set_xlabel("расстояние, м")
    ax[0].set_ylabel("доля принятых пакетов, %")
    ax[0].legend()
    ax[0].grid(alpha=.3)
    rs2 = list(range(10, 1201, 5))
    for f in (150, 40):
        ax[1].plot(rs2, [100 * channel.echo_detect_prob(r, f) for r in rs2], label=f"скан {f} кГц")
    ax[1].set_title("Обнаружение объекта по эху (расчёт, параметры - допущения)")
    ax[1].set_xlabel("расстояние, м")
    ax[1].set_ylabel("вероятность обнаружения, %")
    ax[1].legend()
    ax[1].grid(alpha=.3)
    fig.tight_layout()
    path = os.path.join(OUT, "channel.png")
    fig.savefig(path, dpi=150)
    print(path)
    print("дальность приёма пакета >=50%%: 25 кГц %d м, 35 кГц %d м" % (
        channel.range_at(lambda r: channel.packet_success(r, 25)),
        channel.range_at(lambda r: channel.packet_success(r, 35))))
    print("дальность эхо-обнаружения >=50%%: 150 кГц %d м, 40 кГц %d м" % (
        channel.range_at(lambda r: channel.echo_detect_prob(r, 150)),
        channel.range_at(lambda r: channel.echo_detect_prob(r, 40))))


if __name__ == "__main__":
    main()
