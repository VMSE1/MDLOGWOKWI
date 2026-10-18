"""Прогон прошивки без Wokwi: эмулятор ядра Cortex-M0+ (Unicorn) с заглушками периферии.

Проверяет логику прошивки: старт, настройку порта (BRR), строки FRAME и реакцию на кнопку.
Не проверяет настоящую периферию (тайминги, пины, электрику): для этого нужен Wokwi или плата.
  pip install unicorn pyelftools
  python test/emu_run.py build/madilog.elf released 4    # кнопка отпущена, 4 строки
  python test/emu_run.py build/madilog.elf pressed 3     # кнопка нажата: подмена подписи
"""
import sys
from unicorn import *
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile

elf_path, pressed, nlines = sys.argv[1], sys.argv[2] == "pressed", int(sys.argv[3])
mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
mu.mem_map(0x08000000, 0x10000); mu.mem_map(0x20000000, 0x4000)
mu.mem_map(0x40000000, 0x40000); mu.mem_map(0x50000000, 0x2000)
with open(elf_path, "rb") as f:
    e = ELFFile(f)
    for seg in e.iter_segments():
        if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]:
            mu.mem_write(seg["p_paddr"], seg.data())
    sym = {s.name: s["st_value"] for s in e.get_section_by_name(".symtab").iter_symbols()}
RCC, USART2, GPIOC = 0x40021000, 0x40004400, 0x50000800
mu.mem_write(RCC + 0x00, (0x1540).to_bytes(4, "little"))  # RCC_CR после сброса: HSI48/4 = 12 МГц
out, gpio_log = bytearray(), []
st = {"systick": 0}
def on_read(uc, acc, addr, size, val, ud):
    if addr == USART2 + 0x1C: uc.mem_write(addr, (0xC0).to_bytes(4, "little"))  # передатчик всегда свободен
    if addr == GPIOC + 0x10: uc.mem_write(addr, (0 if pressed else 1 << 13).to_bytes(4, "little"))
def on_write(uc, acc, addr, size, val, ud):
    if addr == USART2 + 0x28:
        out.append(val & 0xFF)
        if out.count(b"\n"[0]) >= nlines: uc.emu_stop()
    if addr == USART2 + 0x0C: st["brr"] = val
    if addr == 0x50000014: gpio_log.append(val)
mu.hook_add(UC_HOOK_MEM_READ, on_read, begin=0x40000000, end=0x50002000)
mu.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=0x40000000, end=0x50002000)
# SysTick: COUNTFLAG всегда «готов», задержки пролетают мгновенно
def on_unmapped(uc, acc, addr, size, val, ud):
    uc.mem_map(addr & ~0xFFF, 0x1000)
    return True
mu.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
def on_scs_read(uc, acc, addr, size, val, ud):
    if addr == 0xE000E010: uc.mem_write(addr, (1 << 16).to_bytes(4, "little"))
mu.hook_add(UC_HOOK_MEM_READ, on_scs_read, begin=0xE000E000, end=0xE000F000)
sp = int.from_bytes(mu.mem_read(0x08000000, 4), "little"); pc = int.from_bytes(mu.mem_read(0x08000004, 4), "little")
mu.reg_write(UC_ARM_REG_SP, sp)
mu.emu_start(pc | 1, 0, count=200_000_000)
print(out.decode(errors="replace"), end="")
print(f"[BRR={st.get('brr')}  => {12_000_000/st['brr']:.0f} baud; PA5 ODR writes: {sorted(set(v & (1<<5) for v in gpio_log))}]")
