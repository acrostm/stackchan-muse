// SPDX-License-Identifier: Apache-2.0
#include "muse_notice.h"
#include "muse_notice_core.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t s_lock;
static muse_notice_core_t s_state;

static bool ensure_lock(void)
{
    if (s_lock) return true;
    s_lock = xSemaphoreCreateMutex();
    return s_lock != NULL;
}

bool muse_notice_publish(const char *message_id, const char *text)
{
    if (!ensure_lock() || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return false;
    bool ok = muse_notice_core_publish(&s_state, message_id, text);
    xSemaphoreGive(s_lock);
    return ok;
}

bool muse_notice_take(char *out, size_t cap)
{
    if (!ensure_lock() || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return false;
    bool ok = muse_notice_core_take(&s_state, out, cap);
    xSemaphoreGive(s_lock);
    return ok;
}

bool muse_notice_pending(void)
{
    if (!ensure_lock() || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return false;
    bool pending = s_state.count != 0;
    xSemaphoreGive(s_lock);
    return pending;
}
