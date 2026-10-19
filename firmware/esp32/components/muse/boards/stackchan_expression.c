// SPDX-License-Identifier: Apache-2.0
#include "stackchan_expression.h"

#include <stdatomic.h>
#include <stdint.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "stackchan_expression_plan.h"
#include "stackchan_head.h"

static const char *TAG = "stackchan_express";
static atomic_bool s_busy;

static void move(int yaw, int pitch)
{
    stackchan_head_move(yaw, pitch, 300, STACKCHAN_MOVE_EXPRESSION, 0);
}

static void expression_task(void *arg)
{
    const stackchan_expression_t expression = (stackchan_expression_t)(uintptr_t)arg;
    switch (expression) {
    case STACKCHAN_EXPRESSION_AFFIRM:
        move(0, 6);
        vTaskDelay(pdMS_TO_TICKS(160));
        move(0, 0);
        vTaskDelay(pdMS_TO_TICKS(120));
        move(0, 6);
        vTaskDelay(pdMS_TO_TICKS(160));
        break;
    case STACKCHAN_EXPRESSION_THINK:
        move(7, 3);
        vTaskDelay(pdMS_TO_TICKS(420));
        break;
    case STACKCHAN_EXPRESSION_APOLOGY:
        move(-5, 2);
        vTaskDelay(pdMS_TO_TICKS(220));
        move(5, 2);
        vTaskDelay(pdMS_TO_TICKS(240));
        break;
    case STACKCHAN_EXPRESSION_HAPPY:
        move(0, 9);
        vTaskDelay(pdMS_TO_TICKS(240));
        break;
    case STACKCHAN_EXPRESSION_NOD:
    default:
        move(0, 4);
        vTaskDelay(pdMS_TO_TICKS(160));
        break;
    }
    move(0, 0);
    atomic_store(&s_busy, false);
    vTaskDelete(NULL);
}

void stackchan_express_reply(const char *text)
{
    if (!stackchan_head_ready() || atomic_exchange(&s_busy, true)) return;
    const stackchan_expression_t expression = stackchan_expression_plan(text);
    if (xTaskCreate(expression_task, "stackchan_express", 3072,
                    (void *)(uintptr_t)expression, 3, NULL) != pdPASS) {
        atomic_store(&s_busy, false);
        ESP_LOGW(TAG, "could not start expression task");
    }
}
