// SPDX-License-Identifier: Apache-2.0
#include "muse_notice.h"
#include "muse_notice_core.h"

#include <stdatomic.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static _Atomic(SemaphoreHandle_t) s_lock;
static muse_notice_core_t s_state;

/* Allocate outside a critical section. Only the published winner protects the
 * queue; racing candidates are deleted without ever being taken. No spinlock
 * is held across allocation or a blocking semaphore operation. */
static SemaphoreHandle_t ensure_lock(void)
{
    SemaphoreHandle_t lock = atomic_load_explicit(&s_lock, memory_order_acquire);
    if (lock) return lock;
    SemaphoreHandle_t candidate = xSemaphoreCreateMutex();
    if (!candidate) return atomic_load_explicit(&s_lock, memory_order_acquire);
    SemaphoreHandle_t expected = NULL;
    if (atomic_compare_exchange_strong_explicit(&s_lock, &expected, candidate,
                                                memory_order_acq_rel,
                                                memory_order_acquire)) {
        return candidate;
    }
    vSemaphoreDelete(candidate);
    return expected;
}

bool muse_notice_publish(const char *message_id, const char *text)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    bool ok = muse_notice_core_publish(&s_state, message_id, text);
    xSemaphoreGive(lock);
    return ok;
}

bool muse_notice_take(char *out, size_t cap)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    bool ok = muse_notice_core_take(&s_state, out, cap);
    xSemaphoreGive(lock);
    return ok;
}

bool muse_notice_pending(void)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    bool pending = s_state.count != 0;
    xSemaphoreGive(lock);
    return pending;
}
