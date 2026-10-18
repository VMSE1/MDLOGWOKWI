# Сборка прошивки для Nucleo-C031C6 (Wokwi). Нужен arm-none-eabi-gcc: make
TARGET = madilog
BUILD  = build
PREFIX = arm-none-eabi-
CC = $(PREFIX)gcc
CP = $(PREFIX)objcopy
SZ = $(PREFIX)size

MCU    = -mcpu=cortex-m0plus -mthumb
CFLAGS = $(MCU) -DSTM32C031xx -Os -Wall -g -ffunction-sections -fdata-sections \
         -Ivendor/CMSIS/Include -Ivendor/Core/Inc -Isrc
LDFLAGS = $(MCU) -specs=nano.specs -specs=nosys.specs -Tvendor/STM32C031C6TX_FLASH.ld \
          -Wl,-Map=$(BUILD)/$(TARGET).map,--gc-sections

SRCS = src/main.c src/frame.c vendor/Core/Src/system_stm32c0xx.c
OBJS = $(addprefix $(BUILD)/,$(notdir $(SRCS:.c=.o))) $(BUILD)/startup.o
vpath %.c src vendor/Core/Src

all: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).hex $(BUILD)/$(TARGET).bin
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) -c $(CFLAGS) $< -o $@
$(BUILD)/startup.o: vendor/startup_stm32c031xx.s | $(BUILD)
	$(CC) -x assembler-with-cpp -c $(CFLAGS) $< -o $@
$(BUILD)/$(TARGET).elf: $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SZ) $@
$(BUILD)/%.hex: $(BUILD)/%.elf
	$(CP) -O ihex $< $@
$(BUILD)/%.bin: $(BUILD)/%.elf
	$(CP) -O binary -S $< $@
test:
	gcc -Wall -Isrc test/host_test.c src/frame.c -o /tmp/madilog_host_test && /tmp/madilog_host_test
emu: $(BUILD)/$(TARGET).elf
	python3 test/emu_run.py $(BUILD)/$(TARGET).elf released 4
	python3 test/emu_run.py $(BUILD)/$(TARGET).elf pressed 2
clean:
	rm -rf $(BUILD)
.PHONY: all clean test emu
