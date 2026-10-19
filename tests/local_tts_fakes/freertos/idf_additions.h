#pragma once
#include <stddef.h>
int xTaskCreatePinnedToCoreWithCaps(void (*)(void *), const char *, size_t, void *, int, void *, int, int);
