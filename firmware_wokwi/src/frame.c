#include "frame.h"
#include <string.h>

/* ---------- CRC16-CCITT ---------- */
uint16_t crc16_ccitt(const uint8_t *d, size_t n)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < n; i++) {
        crc ^= (uint16_t)d[i] << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

/* ---------- SHA-256 (компактная реализация) ---------- */
typedef struct { uint32_t h[8]; uint8_t buf[64]; uint32_t blen; uint64_t total; } sha_t;
static const uint32_t K[64] = {
 0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
 0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
 0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
 0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
 0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
 0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x,n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha_block(sha_t *s, const uint8_t *p)
{
    uint32_t w[64], a, b, c, d, e, f, g, h;
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[4*i] << 24) | ((uint32_t)p[4*i+1] << 16) | ((uint32_t)p[4*i+2] << 8) | p[4*i+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ROR(w[i-15],7) ^ ROR(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = ROR(w[i-2],17) ^ ROR(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    a=s->h[0]; b=s->h[1]; c=s->h[2]; d=s->h[3]; e=s->h[4]; f=s->h[5]; g=s->h[6]; h=s->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ROR(e,6) ^ ROR(e,11) ^ ROR(e,25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = ROR(a,2) ^ ROR(a,13) ^ ROR(a,22);
        uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + mj;
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    s->h[0]+=a; s->h[1]+=b; s->h[2]+=c; s->h[3]+=d; s->h[4]+=e; s->h[5]+=f; s->h[6]+=g; s->h[7]+=h;
}
static void sha_init(sha_t *s)
{
    static const uint32_t H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    memcpy(s->h, H0, sizeof H0); s->blen = 0; s->total = 0;
}
static void sha_update(sha_t *s, const uint8_t *d, size_t n)
{
    s->total += n;
    while (n--) {
        s->buf[s->blen++] = *d++;
        if (s->blen == 64) { sha_block(s, s->buf); s->blen = 0; }
    }
}
static void sha_final(sha_t *s, uint8_t out[32])
{
    uint64_t bits = s->total * 8;
    uint8_t pad = 0x80;
    sha_update(s, &pad, 1);
    pad = 0;
    while (s->blen != 56) sha_update(s, &pad, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8*i));
    sha_update(s, len, 8);
    for (int i = 0; i < 8; i++) {
        out[4*i] = (uint8_t)(s->h[i] >> 24); out[4*i+1] = (uint8_t)(s->h[i] >> 16);
        out[4*i+2] = (uint8_t)(s->h[i] >> 8); out[4*i+3] = (uint8_t)s->h[i];
    }
}

void hmac_sha256(const uint8_t *key, size_t klen, const uint8_t *msg, size_t mlen, uint8_t out[32])
{
    uint8_t k[64] = {0}, ipad[64], opad[64], inner[32];
    sha_t s;
    if (klen > 64) { sha_init(&s); sha_update(&s, key, klen); sha_final(&s, k); }
    else memcpy(k, key, klen);
    for (int i = 0; i < 64; i++) { ipad[i] = k[i] ^ 0x36; opad[i] = k[i] ^ 0x5c; }
    sha_init(&s); sha_update(&s, ipad, 64); sha_update(&s, msg, mlen); sha_final(&s, inner);
    sha_init(&s); sha_update(&s, opad, 64); sha_update(&s, inner, 32); sha_final(&s, out);
}

/* ---------- кадр ---------- */
static size_t put_uint(char *p, uint32_t v)  /* десятичное число без ведущих нулей */
{
    char t[10]; size_t n = 0, i;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    for (i = 0; i < n; i++) p[i] = t[n - 1 - i];
    return n;
}

void make_mac4(const char *key, uint32_t drone_num, uint16_t counter, uint8_t mac[4])
{
    char msg[24]; size_t n = 0; uint8_t full[32];
    msg[n++]='M'; msg[n++]='D'; msg[n++]='-';
    msg[n++] = (char)('0' + (drone_num / 1000) % 10); msg[n++] = (char)('0' + (drone_num / 100) % 10);
    msg[n++] = (char)('0' + (drone_num / 10) % 10);   msg[n++] = (char)('0' + drone_num % 10);
    msg[n++] = ':';
    n += put_uint(msg + n, counter);
    hmac_sha256((const uint8_t *)key, strlen(key), (const uint8_t *)msg, n, full);
    memcpy(mac, full, 4);
}

void build_frame(uint8_t f[FRAME_LEN], uint32_t num, uint16_t counter,
                 uint16_t depth_dm, uint8_t flags, const uint8_t mac[4])
{
    f[0] = 0xA5; f[1] = 1;
    f[2] = (uint8_t)(num >> 24); f[3] = (uint8_t)(num >> 16); f[4] = (uint8_t)(num >> 8); f[5] = (uint8_t)num;
    f[6] = (uint8_t)(counter >> 8); f[7] = (uint8_t)counter;
    f[8] = (uint8_t)(depth_dm >> 8); f[9] = (uint8_t)depth_dm;
    f[10] = flags;
    memcpy(f + 11, mac, 4);
    uint16_t c = crc16_ccitt(f, 15);
    f[15] = (uint8_t)(c >> 8); f[16] = (uint8_t)c;
}

void to_hex(const uint8_t *d, size_t n, char *out)
{
    static const char H[] = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) { out[2*i] = H[d[i] >> 4]; out[2*i+1] = H[d[i] & 15]; }
    out[2*n] = 0;
}
