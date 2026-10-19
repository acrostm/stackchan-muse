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
typedef struct {
    stackchan_expression_t expression;
    uint32_t generation;
} expression_request_t;
static expression_request_t s_request;

static bool move(const expression_request_t *request, int yaw, int pitch)
{
    return stackchan_head_move_for_generation(
        yaw, pitch, 300, STACKCHAN_MOVE_EXPRESSION, 0,
        request->generation) == ESP_OK;
}

static void expression_task(void *arg)
{
    const expression_request_t *request = arg;
    bool alive = true;
    switch (request->expression) {
    case STACKCHAN_EXPRESSION_AFFIRM:
        alive = move(request, 0, 6);
        vTaskDelay(pdMS_TO_TICKS(160));
        alive = alive && move(request, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(120));
        alive = alive && move(request, 0, 6);
        vTaskDelay(pdMS_TO_TICKS(160));
        break;
    case STACKCHAN_EXPRESSION_THINK:
        alive = move(request, 7, 3);
        vTaskDelay(pdMS_TO_TICKS(420));
        break;
    case STACKCHAN_EXPRESSION_APOLOGY:
        alive = move(request, -5, 2);
        vTaskDelay(pdMS_TO_TICKS(220));
        alive = alive && move(request, 5, 2);
        vTaskDelay(pdMS_TO_TICKS(240));
        break;
    case STACKCHAN_EXPRESSION_HAPPY:
        alive = move(request, 0, 9);
        vTaskDelay(pdMS_TO_TICKS(240));
        break;
    case STACKCHAN_EXPRESSION_NOD:
    default:
        alive = move(request, 0, 4);
        vTaskDelay(pdMS_TO_TICKS(160));
        break;
    }
    if (alive) (void)move(request, 0, 0);
    atomic_store(&s_busy, false);
    vTaskDelete(NULL);
}

void stackchan_express_reply(const char *text)
{
    const uint32_t generation = stackchan_head_ready_generation();
    if (!generation || atomic_exchange(&s_busy, true)) return;
    s_request = (expression_request_t){
        .expression = stackchan_expression_plan(text),
        .generation = generation,
    };
    if (xTaskCreate(expression_task, "stackchan_express", 3072,
                    &s_request, 3, NULL) != pdPASS) {
        atomic_store(&s_busy, false);
        ESP_LOGW(TAG, "could not start expression task");
    }
}
