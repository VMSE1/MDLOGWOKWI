/*
 * MADILOG: имитация модуля аппарата на Nucleo-C031C6 для Wokwi.
 * Раз в секунду печатает в UART2 (PA2/PA3, это виртуальный порт ST-LINK на Nucleo) строку:
 *     FRAME,<кадр 17 байт в hex>,<дальность в метрах>
 * Дальность имитируется: ходит туда-обратно от 20 до 300 м.
 * Кнопка PC13 нажата -> режим «подмена»: подпись неверная, кадр с корректным CRC. Светодиод PA5 горит.
 * Строки, которые не начинаются с FRAME, мост игнорирует.
 */
#include "stm32c0xx.h"
#include "frame.h"

#define DRONE_NUM   427u            /* MD-0427 */
#define DRONE_KEY   "key-0427"      /* ключ из демо-реестра */
#define DEPTH_DM    385u            /* 38,5 м, как в тестовом примере */
#define BAUD        115200u

static void uart_putc(char c)
{
    while (!(USART2->ISR & USART_ISR_TXE_TXFNF)) { }
    USART2->TDR = (uint8_t)c;
}
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

static void uart_range(uint16_t dm)   /* дальность в дециметрах -> "142.5" */
{
    char t[8]; int n = 0;
    uint16_t whole = dm / 10, frac = dm % 10;
    do { t[n++] = (char)('0' + whole % 10); whole /= 10; } while (whole);
    while (n) uart_putc(t[--n]);
    uart_putc('.'); uart_putc((char)('0' + frac));
}

static void gpio_uart_init(void)
{
    RCC->IOPENR  |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOCEN;
    RCC->APBENR1 |= RCC_APBENR1_USART2EN;

    /* PA2 = USART2_TX, PA3 = USART2_RX, альтернативная функция AF1 */
    GPIOA->MODER = (GPIOA->MODER & ~((3u << 4) | (3u << 6))) | (2u << 4) | (2u << 6);
    GPIOA->AFR[0] = (GPIOA->AFR[0] & ~((0xFu << 8) | (0xFu << 12))) | (1u << 8) | (1u << 12);
    /* PA5 = светодиод */
    GPIOA->MODER = (GPIOA->MODER & ~(3u << 10)) | (1u << 10);
    /* PC13 = кнопка, вход с подтяжкой вверх (нажата = 0) */
    GPIOC->MODER &= ~(3u << 26);
    GPIOC->PUPDR = (GPIOC->PUPDR & ~(3u << 26)) | (1u << 26);

    SystemCoreClockUpdate();
    USART2->BRR = SystemCoreClock / BAUD;
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE;
}

static void delay_100ms(void)
{
    SysTick->LOAD = SystemCoreClock / 10 - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk | SysTick_CTRL_ENABLE_Msk;
    while (!(SysTick->CTRL & SysTick_CTRL_COUNTFLAG_Msk)) { }
    SysTick->CTRL = 0;
}

int main(void)
{
    uint16_t counter = 10;       /* первый кадр совпадает с примером из документа */
    uint16_t range_dm = 1425;    /* 142,5 м */
    int step = 25;               /* 2,5 м за секунду */

    gpio_uart_init();
    uart_puts("# MADILOG module sim, MD-0427\n");

    for (;;) {
        uint8_t mac[4], f[FRAME_LEN]; char hex[2 * FRAME_LEN + 1];
        int spoof = !(GPIOC->IDR & (1u << 13));

        if (spoof) { mac[0] = 0xDE; mac[1] = 0xAD; mac[2] = 0xBE; mac[3] = 0xEF; GPIOA->ODR |= (1u << 5); }
        else       { make_mac4(DRONE_KEY, DRONE_NUM, counter, mac);              GPIOA->ODR &= ~(1u << 5); }

        build_frame(f, DRONE_NUM, counter, DEPTH_DM, 0, mac);
        to_hex(f, FRAME_LEN, hex);
        uart_puts("FRAME,"); uart_puts(hex); uart_putc(','); uart_range(range_dm); uart_putc('\n');

        counter++;
        range_dm = (uint16_t)((int)range_dm + step);
        if (range_dm >= 3000) step = -25;
        if (range_dm <= 200)  step = 25;

        for (int i = 0; i < 10; i++) delay_100ms();
    }
}
