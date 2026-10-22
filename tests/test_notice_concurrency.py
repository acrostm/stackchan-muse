"""Compile the actual notice wrapper with pthread-backed FreeRTOS mutexes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NoticeConcurrencyTests(unittest.TestCase):
    def test_first_publish_race_uses_one_lock_and_releases_losers(self):
        source = r'''
#include "muse_notice.h"
#include "freertos/semphr.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include "nvs.h"
void muse_state_set_reply_pending(bool value) {(void)value;}
void muse_state_nudge(void) {}
bool muse_settings_speaker_on(void) { return true; }
int muse_settings_volume(void) { return 70; }
esp_err_t nvs_open(const char *ns, int mode, nvs_handle_t *h) { (void)ns;(void)mode;*h=1;return ESP_OK; }
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *p,size_t *n) { (void)h;(void)key;(void)p;(void)n;return ESP_ERR_NVS_NOT_FOUND; }
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *p,size_t n) { (void)h;(void)key;(void)p;(void)n;return ESP_OK; }
esp_err_t nvs_commit(nvs_handle_t h) { (void)h;return ESP_OK; }
void nvs_close(nvs_handle_t h) { (void)h; }

static atomic_int created, deleted, arrivals;
static atomic_bool fail_allocation = true;
SemaphoreHandle_t xSemaphoreCreateMutex(void) {
    if (atomic_load(&fail_allocation)) return NULL;
    SemaphoreHandle_t p = malloc(sizeof(*p));
    assert(p && pthread_mutex_init(p, NULL) == 0);
    atomic_fetch_add(&created, 1);
    /* All first callers allocate before any can publish the winning lock. */
    atomic_fetch_add(&arrivals, 1);
    while (atomic_load(&arrivals) < MUSE_NOTICE_QUEUE_MAX) sched_yield();
    return p;
}
void vSemaphoreDelete(SemaphoreHandle_t p) {
    assert(pthread_mutex_destroy(p) == 0);
    atomic_fetch_add(&deleted, 1);
    free(p);
}
int xSemaphoreTake(SemaphoreHandle_t p, int timeout) {
    (void)timeout;
    return pthread_mutex_lock(p) == 0;
}
int xSemaphoreGive(SemaphoreHandle_t p) {
    return pthread_mutex_unlock(p) == 0;
}
static void *publish(void *arg) {
    assert(muse_notice_publish((const char *)arg, (const char *)arg));
    return NULL;
}
static bool consume(char *out, size_t cap) {
    const char *text = muse_notice_claim(NULL);
    if (!text) return false;
    assert(strlen(text) < cap);
    strcpy(out, text);
    muse_notice_finish(true);  /* test owner explicitly acknowledges consumption */
    return true;
}
int main(void) {
    char out[MUSE_NOTICE_TEXT_MAX+1];
    assert(!muse_notice_publish("fail", "fail"));
    assert(!consume(out, sizeof(out)));
    assert(!muse_notice_pending());
    atomic_store(&fail_allocation, false);
    pthread_t threads[MUSE_NOTICE_QUEUE_MAX];
    const char *ids[] = {"one", "two", "three", "four"};
    for (int i = 0; i < MUSE_NOTICE_QUEUE_MAX; ++i)
        assert(pthread_create(&threads[i], NULL, publish, (void *)ids[i]) == 0);
    for (int i = 0; i < MUSE_NOTICE_QUEUE_MAX; ++i)
        assert(pthread_join(threads[i], NULL) == 0);
    assert(atomic_load(&created) == MUSE_NOTICE_QUEUE_MAX);
    assert(atomic_load(&deleted) == MUSE_NOTICE_QUEUE_MAX - 1);
    assert(muse_notice_pending());
    assert(!muse_notice_publish("overflow", "full"));
    unsigned seen = 0;
    for (int n = 0; n < MUSE_NOTICE_QUEUE_MAX; ++n) {
        assert(consume(out, sizeof(out)));
        int i = 0;
        while (i < MUSE_NOTICE_QUEUE_MAX && strcmp(out, ids[i])) ++i;
        assert(i < MUSE_NOTICE_QUEUE_MAX && !(seen & (1U << i)));
        seen |= 1U << i;
    }
    assert(seen == (1U << MUSE_NOTICE_QUEUE_MAX) - 1);
    assert(!muse_notice_pending());
    assert(!muse_notice_publish("one", "deduplicated"));
    assert(muse_notice_publish("overflow", "retry accepted"));
    assert(consume(out, sizeof(out)) && !strcmp(out, "retry accepted"));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'freertos').mkdir()
            (path / 'freertos/FreeRTOS.h').write_text('#pragma once\n#define pdTRUE 1\n#define portMAX_DELAY -1\n')
            (path / 'freertos/semphr.h').write_text('''#pragma once
#include <pthread.h>
typedef pthread_mutex_t *SemaphoreHandle_t;
SemaphoreHandle_t xSemaphoreCreateMutex(void);
void vSemaphoreDelete(SemaphoreHandle_t);
int xSemaphoreTake(SemaphoreHandle_t, int);
int xSemaphoreGive(SemaphoreHandle_t);
''')
            (path / 'test.c').write_text(source)
            component = ROOT / 'firmware/esp32/components/muse'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-pthread', '-fsanitize=address,undefined',
                            '-I', str(path), '-I', str(ROOT / 'tests/notice_fakes'), '-I', str(component), str(path / 'test.c'),
                            str(component / 'muse_notice.c'), str(component / 'muse_notice_core.c'),
                            str(component / 'muse_notice_policy.c'),
                            '-o', str(path / 'test')], check=True)
            for _ in range(10):
                subprocess.run([str(path / 'test')], check=True, timeout=10)
