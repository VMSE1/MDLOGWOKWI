/* Кадр ответа MADILOG (17 байт). Формат совпадает с sim/packet.py. Без зависимостей от платы. */
#ifndef FRAME_H
#define FRAME_H
#include <stdint.h>
#include <stddef.h>

#define FRAME_LEN 17

uint16_t crc16_ccitt(const uint8_t *d, size_t n);                       /* poly 0x1021, init 0xFFFF */
void hmac_sha256(const uint8_t *key, size_t klen, const uint8_t *msg, size_t mlen, uint8_t out[32]);
/* Подпись: первые 4 байта HMAC-SHA256(key, "MD-NNNN:счётчик"). */
void make_mac4(const char *key, uint32_t drone_num, uint16_t counter, uint8_t mac[4]);
/* Собирает кадр: A5, ver=1, ID(4), счётчик(2), глубина в дм(2), флаги(1), подпись(4), CRC16(2). */
void build_frame(uint8_t f[FRAME_LEN], uint32_t drone_num, uint16_t counter,
                 uint16_t depth_dm, uint8_t flags, const uint8_t mac[4]);
/* hex-строка в out (размер не меньше 2*n+1) */
void to_hex(const uint8_t *d, size_t n, char *out);
#endif
