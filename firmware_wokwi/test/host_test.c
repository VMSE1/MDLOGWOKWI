/* Проверка на обычном компьютере: gcc -I../src host_test.c ../src/frame.c -o t && ./t */
#include <stdio.h>
#include <string.h>
#include "frame.h"
int main(void)
{
    uint8_t mac[4], f[FRAME_LEN]; char hex[2*FRAME_LEN+1], mh[9];
    make_mac4("key-0427", 427, 10, mac); to_hex(mac, 4, mh);
    build_frame(f, 427, 10, 385, 0, mac); to_hex(f, FRAME_LEN, hex);
    int ok1 = !strcmp(mh, "d3e0c212");
    int ok2 = !strcmp(hex, "a501000001ab000a018100d3e0c2125e28");
    printf("mac   %s  %s\nframe %s  %s\n", mh, ok1 ? "OK" : "ОШИБКА", hex, ok2 ? "OK" : "ОШИБКА");
    return !(ok1 && ok2);
}
