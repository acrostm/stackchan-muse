// SPDX-License-Identifier: Apache-2.0
#include "sw_runtime.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/stream_buffer.h"
#include "freertos/task.h"
#include "mbedtls/base64.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PCM_CAP (64 * 1024)
#define TTS_DEADLINE_US (90LL * 1000000)
typedef struct { uint32_t gen; char text[SW_TEXT_CAP]; } job_t;
static QueueHandle_t jobs;
static SemaphoreHandle_t lock;
static StreamBufferHandle_t pcm;
static atomic_uint generation;
static bool ended = true, succeeded;
typedef struct {
    uint32_t gen;
    int64_t deadline;
    bool final, audio;
    int http_status, provider_code, transport_error;
    const char *stage;
    unsigned char *decoded;
    unsigned char *preview;
    size_t preview_cap, preview_size;
} response_t;

void sw_tts_cancel(void)
{
    if (!lock) return;
    xSemaphoreTake(lock, portMAX_DELAY);
    atomic_fetch_add(&generation, 1);
    xStreamBufferReset(pcm);
    ended = true;
    succeeded = false;
    xSemaphoreGive(lock);
}

bool sw_tts_start(const char *text)
{
    if (!jobs) return false;
    sw_config_t c;
    sw_config_get(&c);
    bool configured = c.api_key[0] || (c.app_id[0] && c.access_key[0]);
    memset(&c, 0, sizeof(c));
    if (!configured || !text || !*text) return false;
    job_t job;
    sw_text_copy(job.text, sizeof(job.text), text);
    xSemaphoreTake(lock, portMAX_DELAY);
    job.gen = atomic_fetch_add(&generation, 1) + 1;
    xStreamBufferReset(pcm);
    ended = false;
    succeeded = false;
    xQueueOverwrite(jobs, &job);
    xSemaphoreGive(lock);
    return true;
}

size_t sw_tts_read(void *out, size_t cap)
{
    if (cap < 2) return 0;
    xSemaphoreTake(lock, portMAX_DELAY);
    /* Every provider PCM chunk must contain complete PCM16 samples. */
    size_t available = xStreamBufferBytesAvailable(pcm) & ~(size_t)1;
    if (cap > available) cap = available;
    size_t n = cap ? xStreamBufferReceive(pcm, out, cap & ~(size_t)1, 0) : 0;
    xSemaphoreGive(lock);
    return n;
}

bool sw_tts_done(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    bool done = ended && xStreamBufferIsEmpty(pcm);
    xSemaphoreGive(lock);
    return done;
}

bool sw_tts_succeeded(void)
{
    if (!lock) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = ended && succeeded && xStreamBufferIsEmpty(pcm);
    xSemaphoreGive(lock);
    return ok;
}

static bool current(response_t *r)
{
    return (r->preview || r->gen == atomic_load(&generation)) && esp_timer_get_time() < r->deadline;
}

static bool line(const char *s, void *ctx)
{
    response_t *r = ctx;
    if (!current(r)) return false;
    if (!*s || !strncmp(s, "event:", 6) || s[0] == ':') return true;
    if (!strncmp(s, "data:", 5)) { s += 5; while (*s == ' ') ++s; }
    if (r->final) return false;
    cJSON *root = cJSON_Parse(s);
    if (!root) { r->stage = "Invalid SSE JSON"; return false; }
    cJSON *code = cJSON_GetObjectItemCaseSensitive(root, "code");
    cJSON *data = cJSON_GetObjectItemCaseSensitive(root, "data");
    if (cJSON_IsNumber(code) && code->valueint) r->provider_code = code->valueint;
    bool ok = cJSON_IsNumber(code) && (code->valueint == 0 || code->valueint == 20000000);
    if (ok && cJSON_IsString(data) && data->valuestring[0]) {
        size_t n = 0;
        ok = mbedtls_base64_decode(r->decoded, SW_LINE_CAP * 3 / 4, &n,
                (const unsigned char *)data->valuestring, strlen(data->valuestring)) == 0 && !(n & 1);
        if (ok && r->preview) {
            ok = n <= r->preview_cap - r->preview_size;
            if (!ok) r->stage = "Preview audio exceeds buffer";
            if (ok) { memcpy(r->preview + r->preview_size, r->decoded, n); r->preview_size += n; }
        }
        size_t at = r->preview ? n : 0;
        while (ok && at < n) {
            if (!current(r)) { ok = false; break; }
            xSemaphoreTake(lock, portMAX_DELAY);
            if (r->gen == atomic_load(&generation))
                at += xStreamBufferSend(pcm, r->decoded + at, n - at, 0);
            xSemaphoreGive(lock);
            if (at < n) vTaskDelay(pdMS_TO_TICKS(10));
        }
        r->audio |= ok && n > 0;
    }
    if (ok && code->valueint == 20000000) r->final = true;
    cJSON_Delete(root);
    return ok;
}

static bool synthesize_config(const job_t *job, char *linebuf, response_t *sink, const sw_config_t *config)
{
    response_t response = *sink;
    sw_config_t c = *config;
    cJSON *root = cJSON_CreateObject();
    cJSON *user = cJSON_AddObjectToObject(root, "user");
    cJSON_AddStringToObject(user, "uid", "stopwatch");
    cJSON *req = cJSON_AddObjectToObject(root, "req_params");
    cJSON_AddStringToObject(req, "text", job->text);
    cJSON_AddStringToObject(req, "speaker", c.speaker);
    cJSON *audio = cJSON_AddObjectToObject(req, "audio_params");
    cJSON_AddStringToObject(audio, "format", "pcm");
    cJSON_AddNumberToObject(audio, "sample_rate", 16000);
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    esp_http_client_config_t cfg = {
        .url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse",
        .method = HTTP_METHOD_POST, .timeout_ms = 3000,
        .crt_bundle_attach = esp_crt_bundle_attach, .buffer_size = 2048,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t h = body ? esp_http_client_init(&cfg) : NULL;
    bool ok = h != NULL;
    response.stage = h ? "TLS connect" : "HTTP allocation";
    if (ok) {
        esp_http_client_set_header(h, "Content-Type", "application/json");
        esp_http_client_set_header(h, "X-Api-Resource-Id", "seed-tts-2.0");
        if (c.api_key[0]) esp_http_client_set_header(h, "X-Api-Key", c.api_key);
        else {
            esp_http_client_set_header(h, "X-Api-App-Id", c.app_id);
            esp_http_client_set_header(h, "X-Api-Access-Key", c.access_key);
        }
        ok = current(&response) && esp_http_client_open(h, strlen(body)) == ESP_OK;
        if (ok) response.stage = "HTTP request write";
        size_t at = 0, size = strlen(body);
        while (ok && at < size) {
            int n = esp_http_client_write(h, body + at, size - at);
            ok = n > 0 && current(&response);
            if (n > 0) at += n;
        }
        if (ok) {
            response.stage = "HTTP response headers";
            esp_http_client_fetch_headers(h);
            response.http_status = esp_http_client_get_status_code(h);
            ok = response.http_status == 200;
        }
        if (ok) response.stage = "SSE stream incomplete";
        sw_lines_t lines = { .buf = linebuf, .cap = SW_LINE_CAP };
        char chunk[2048];
        while (ok && !response.final && current(&response)) {
            int n = esp_http_client_read(h, chunk, sizeof(chunk));
            if (n <= 0) { ok = false; break; }
            ok = sw_lines_feed(&lines, chunk, n, line, &response);
        }
        ok = ok && current(&response) && response.final && response.audio;
        response.transport_error = esp_http_client_get_errno(h);
        esp_http_client_close(h);
        esp_http_client_cleanup(h);
    }
    free(body);
    memset(&c, 0, sizeof(c));
    *sink = response;
    return ok;
}

static bool synthesize(const job_t *job, char *linebuf, unsigned char *decoded)
{
    sw_config_t c; sw_config_get(&c);
    response_t sink = { .gen = job->gen, .deadline = esp_timer_get_time() + TTS_DEADLINE_US, .decoded = decoded };
    bool ok = synthesize_config(job, linebuf, &sink, &c);
    memset(&c, 0, sizeof(c));
    return ok;
}

bool sw_tts_preview(const sw_config_t *config, unsigned char *output, size_t cap, size_t *size, char *error, size_t error_cap)
{
    char *linebuf = heap_caps_malloc(SW_LINE_CAP, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    unsigned char *decoded = heap_caps_malloc(SW_LINE_CAP * 3 / 4, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    job_t job = {0};
    sw_text_copy(job.text, sizeof(job.text), "你好，我是你的 Muse。这是当前音色的试听，很高兴认识你。");
    response_t sink = { .deadline = esp_timer_get_time() + 30LL * 1000000,
        .decoded = decoded, .preview = output, .preview_cap = cap };
    bool ok = linebuf && decoded && synthesize_config(&job, linebuf, &sink, config);
    *size = ok ? sink.preview_size : 0;
    if (!ok) {
        if (!linebuf || !decoded) sw_text_copy(error, error_cap, "Preview allocation failed");
        else snprintf(error, error_cap, "%s; HTTP %d; provider %d; errno %d",
            sink.stage ? sink.stage : "TTS failed", sink.http_status, sink.provider_code, sink.transport_error);
    }
    free(linebuf); free(decoded);
    return ok;
}

static void worker(void *arg)
{
    (void)arg;
    char *linebuf = heap_caps_malloc(SW_LINE_CAP, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    unsigned char *decoded = heap_caps_malloc(SW_LINE_CAP * 3 / 4, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    job_t job;
    for (;;) {
        xQueueReceive(jobs, &job, portMAX_DELAY);
        if (job.gen != atomic_load(&generation)) continue;
        sw_tts_set_status("Synthesizing");
        bool ok = linebuf && decoded && synthesize(&job, linebuf, decoded);
        xSemaphoreTake(lock, portMAX_DELAY);
        if (job.gen == atomic_load(&generation)) {
            ended = true;
            succeeded = ok;
            /* Keep any already decoded speech; captions survive a TTS failure. */
            sw_tts_set_status(ok ? "Ready" : "TTS failed; text retained");
        }
        xSemaphoreGive(lock);
        memset(&job, 0, sizeof(job));
    }
}

esp_err_t sw_tts_init(void)
{
    lock = xSemaphoreCreateMutex();
    jobs = xQueueCreate(1, sizeof(job_t));
    pcm = xStreamBufferCreateWithCaps(PCM_CAP, 1, MALLOC_CAP_SPIRAM);
    if (!lock || !jobs || !pcm) return ESP_ERR_NO_MEM;
    /* Like the upstream Muse TLS session, keep this network-only stack in
     * PSRAM. Reserve internal RAM for Wi-Fi DMA, BLE and the audio driver. */
    return xTaskCreatePinnedToCoreWithCaps(worker, "doubao_tts", 12 * 1024, NULL, 4, NULL,
            tskNO_AFFINITY, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
