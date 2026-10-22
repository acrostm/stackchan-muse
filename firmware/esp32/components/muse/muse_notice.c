// SPDX-License-Identifier: Apache-2.0
#include "muse_notice.h"
#include "muse_notice_core.h"

#include <stdatomic.h>
#include <time.h>
#include <string.h>
#include "nvs.h"
#include "muse_settings.h"
#include "muse_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static _Atomic(SemaphoreHandle_t) s_lock;
static muse_notice_core_t s_state;
static muse_notice_policy_t s_policy;
static bool s_policy_loaded, s_read_requested, s_reading;
static char s_active_text[MUSE_NOTICE_TEXT_MAX + 1];
static atomic_bool s_silence_requested;


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

/* Called with the queue mutex. Corrupt/unreadable settings fail quiet instead
 * of silently ignoring a previously saved schedule. A validated explicit save
 * can repair the record. No message text is persisted. */
static bool load_policy(void)
{
    if (s_policy_loaded) return true;
    nvs_handle_t nvs;
    if (nvs_open("muse_notice", NVS_READWRITE, &nvs) != ESP_OK) return false;
    uint8_t data[MUSE_NOTICE_POLICY_BYTES];
    size_t length = sizeof(data);
    esp_err_t err = nvs_get_blob(nvs, "policy", data, &length);
    nvs_close(nvs);
    if (err == ESP_ERR_NVS_NOT_FOUND) s_policy = muse_notice_policy_default();
    else if (err != ESP_OK || !muse_notice_policy_decode(&s_policy, data, length)) return false;
    s_policy_loaded = true;
    return true;
}

static bool refresh_policy(void)
{
    if (atomic_exchange_explicit(&s_silence_requested, false, memory_order_acq_rel)) {
        muse_notice_core_silence(&s_state);
        s_read_requested = false;
    }
    bool speaker = muse_settings_speaker_on() && muse_settings_volume() > 0;
    if (!speaker) s_read_requested = false;
    bool ready = load_policy();
    bool quiet = !speaker || !ready || muse_notice_policy_quiet(&s_policy, (int64_t)time(NULL));
    if (quiet) muse_notice_core_silence(&s_state);
    return quiet;
}

bool muse_notice_publish(const char *message_id, const char *text)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    bool quiet = refresh_policy();
    bool ok = s_state.count + (s_reading ? 1U : 0U) < MUSE_NOTICE_QUEUE_MAX &&
              muse_notice_core_publish_mode(&s_state, message_id, text, quiet);
    xSemaphoreGive(lock);
    if (ok && !quiet) muse_state_nudge();
    return ok;
}

bool muse_notice_take_next(char *out, size_t cap, bool *explicit_read)
{
    if (explicit_read) *explicit_read = false;
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    refresh_policy();
    if (s_reading || cap < sizeof(s_active_text)) {
        xSemaphoreGive(lock);
        return false;
    }
    if (!muse_settings_speaker_on() || muse_settings_volume() <= 0) {
        xSemaphoreGive(lock);
        return false;
    }
    bool manual = s_read_requested;
    bool ok = muse_notice_core_take_mode(&s_state, out, cap, manual);
    if (ok) {
        s_reading = true;
        memcpy(s_active_text, out, strlen(out) + 1);
        s_read_requested = false;
        if (explicit_read) *explicit_read = manual;
    }
    xSemaphoreGive(lock);
    return ok;
}

bool muse_notice_pending(void)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    refresh_policy();
    bool pending = (s_read_requested && s_state.count) || muse_notice_core_audible(&s_state);
    xSemaphoreGive(lock);
    return pending;
}

muse_notice_status_t muse_notice_status(void)
{
    muse_notice_status_t status = {.quiet_now = true};
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return status;
    status.quiet_now = refresh_policy();
    status.ready = s_policy_loaded;
    status.clock_ready = (int64_t)time(NULL) >= MUSE_NOTICE_CLOCK_MIN;
    status.policy = s_policy_loaded ? s_policy : muse_notice_policy_default();
    status.unread = s_state.count + (s_reading ? 1U : 0U);
    status.reading = s_reading;
    status.read_requested = s_read_requested;
    status.can_read = !s_reading && s_state.count && muse_settings_speaker_on() && muse_settings_volume() > 0;
    xSemaphoreGive(lock);
    return status;
}

esp_err_t muse_notice_set_policy(const muse_notice_policy_t *policy)
{
    uint8_t data[MUSE_NOTICE_POLICY_BYTES];
    if (!muse_notice_policy_encode(policy, data)) return ESP_ERR_INVALID_ARG;
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return ESP_ERR_NO_MEM;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("muse_notice", NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "policy", data, sizeof(data));
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err == ESP_OK) {
        s_policy = *policy;
        s_policy_loaded = true;
        refresh_policy();
    }
    xSemaphoreGive(lock);
    return err;
}

bool muse_notice_request_read(void)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    refresh_policy();
    bool ok = !s_reading && s_state.count && muse_settings_speaker_on() && muse_settings_volume() > 0;
    if (ok) s_read_requested = true; /* Repeated requests coalesce, never replay. */
    xSemaphoreGive(lock);
    if (ok) muse_state_nudge();
    return ok;
}

bool muse_notice_automatic_allowed(void)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return false;
    bool allowed = !refresh_policy();
    xSemaphoreGive(lock);
    return allowed;
}

void muse_notice_cancel_pending(void)
{
    atomic_store_explicit(&s_silence_requested, true, memory_order_release);
}

void muse_notice_finish(bool played)
{
    SemaphoreHandle_t lock = ensure_lock();
    if (!lock || xSemaphoreTake(lock, portMAX_DELAY) != pdTRUE) return;
    refresh_policy();
    if (s_reading && (played || muse_notice_core_return_unread(&s_state, s_active_text))) {
        s_reading = false;
        memset(s_active_text, 0, sizeof(s_active_text));
    }
    xSemaphoreGive(lock);
}
