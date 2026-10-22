#pragma once
#include <pthread.h>
typedef pthread_mutex_t *SemaphoreHandle_t;
SemaphoreHandle_t xSemaphoreCreateMutex(void);
void vSemaphoreDelete(SemaphoreHandle_t);
int xSemaphoreTake(SemaphoreHandle_t, int);
int xSemaphoreGive(SemaphoreHandle_t);
