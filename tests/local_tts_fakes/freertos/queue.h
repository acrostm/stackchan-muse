#pragma once
#include <stddef.h>
#include <stdint.h>
struct fake_queue;
using QueueHandle_t = fake_queue *;
QueueHandle_t xQueueCreate(size_t, size_t);
int xQueueReceive(QueueHandle_t, void *, uint32_t);
int xQueueSend(QueueHandle_t, const void *, uint32_t);
void vQueueDelete(QueueHandle_t);
