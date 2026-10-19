// SPDX-License-Identifier: Apache-2.0
#include "sdkconfig.h"
#include "muse_local_tts.h"
#include "muse_tts_json.h"
#include <atomic>
#include <cstring>
#include <new>
#include <strings.h>
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
extern "C" {
#include "minimp3.h"
}

#ifndef CONFIG_MUSE_LOCAL_TTS_URL
#define CONFIG_MUSE_LOCAL_TTS_URL ""
#endif
#ifndef CONFIG_MUSE_LOCAL_TTS_FALLBACK_URL
#define CONFIG_MUSE_LOCAL_TTS_FALLBACK_URL ""
#endif
#ifndef CONFIG_MUSE_LOCAL_TTS_TOKEN
#define CONFIG_MUSE_LOCAL_TTS_TOKEN ""
#endif

static constexpr size_t AUDIO_MAX = 512 * 1024;
static constexpr int64_t DEADLINE_US = 45 * 1000000LL;
struct job_t {
    std::atomic<bool> done{false};
    uint32_t epoch;
    int64_t deadline;
    char json[700 * 4 + 16];
    uint8_t *audio = nullptr;
    size_t length = 0;
    bool ok = false, mime = false;
};
static std::atomic<uint32_t> s_epoch{0};
static QueueHandle_t s_queue;
static job_t *s_job; // Owned by the session until worker publishes done.

static void *allocate(size_t size)
{
    return heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
static bool alive(const job_t &job)
{
    return job.epoch == s_epoch.load() && esp_timer_get_time() < job.deadline;
}
static void release(job_t *job)
{
    heap_caps_free(job->audio);
    job->~job_t();
    heap_caps_free(job);
}
static esp_err_t on_header(esp_http_client_event_t *event)
{
    auto *job = static_cast<job_t *>(event->user_data);
    // IDF ignores the return value of body-event callbacks. Shut down only
    // this worker's socket instead: a peer dripping bytes cannot keep its
    // internal read loop alive past cancellation/deadline. Cleanup stays here.
    if (!alive(*job)) {
        int socket = esp_http_client_get_socket(event->client);
        if (socket >= 0) shutdown(socket, SHUT_RDWR);
        return ESP_FAIL;
    }
    if (event->event_id == HTTP_EVENT_ON_HEADER && event->header_key && event->header_value &&
        !strcasecmp(event->header_key, "Content-Type")) {
        const char *value = event->header_value;
        job->mime = !strncasecmp(value, "audio/mpeg", 10) &&
                    (!value[10] || value[10] == ';' || value[10] == ' ');
    }
    return ESP_OK;
}

/* A 200 with a JSON error body or empty/undecodable MP3 is not usable audio. */
static bool decodable(const job_t &job)
{
    auto *decoder = static_cast<mp3dec_t *>(allocate(sizeof(mp3dec_t)));
    auto *pcm = static_cast<int16_t *>(allocate(MINIMP3_MAX_SAMPLES_PER_FRAME * sizeof(int16_t)));
    bool ok = false;
    if (decoder && pcm) {
        mp3dec_init(decoder);
        size_t offset = 0;
        while (offset < job.length && alive(job)) {
            mp3dec_frame_info_t frame{};
            int samples = mp3dec_decode_frame(decoder, job.audio + offset, job.length - offset, pcm, &frame);
            if (samples > 0 && frame.hz > 0 && (frame.channels == 1 || frame.channels == 2)) {
                ok = true;
                break;
            }
            if (frame.frame_bytes <= 0) break;
            offset += static_cast<size_t>(frame.frame_bytes);
        }
    }
    heap_caps_free(decoder);
    heap_caps_free(pcm);
    return ok;
}

static bool fetch(job_t &job, const char *url)
{
    if (!alive(job) || !url[0]) return false;
    job.length = 0;
    job.mime = false;
    esp_http_client_config_t config{};
    config.url = url;
    config.method = HTTP_METHOD_POST;
    config.timeout_ms = 2000; // Every blocking operation is bounded; UI runs separately.
    config.buffer_size = 4096;
    config.event_handler = on_header;
    config.user_data = &job;
    config.disable_auto_redirect = true; // Never forward the private bridge token.
    if (!strncmp(url, "https://", 8)) config.crt_bundle_attach = esp_crt_bundle_attach;
    auto client = esp_http_client_init(&config);
    if (!client) return false;
    bool ok = false;
    esp_http_client_set_header(client, "Content-Type", "application/json");
    if (CONFIG_MUSE_LOCAL_TTS_TOKEN[0])
        esp_http_client_set_header(client, "X-Tts-Auth", CONFIG_MUSE_LOCAL_TTS_TOKEN);
    size_t size = strlen(job.json), sent = 0;
    if (esp_http_client_open(client, static_cast<int>(size)) != ESP_OK) goto finished;
    while (sent < size && alive(job)) {
        int n = esp_http_client_write(client, job.json + sent, size - sent);
        if (n <= 0) goto finished;
        sent += static_cast<size_t>(n);
    }
    if (!alive(job) || sent != size) goto finished;
    {
        int64_t length;
        do {
            if (!alive(job)) goto finished;
            length = esp_http_client_fetch_headers(client);
        } while (length == -ESP_ERR_HTTP_EAGAIN);
        if (length < 0 || length > static_cast<int64_t>(AUDIO_MAX) ||
            esp_http_client_get_status_code(client) != 200 || !job.mime) goto finished;
    }
    if (!job.audio) job.audio = static_cast<uint8_t *>(allocate(AUDIO_MAX));
    if (!job.audio) goto finished;
    while (alive(job)) {
        uint8_t chunk[4096];
        int n = esp_http_client_read(client, reinterpret_cast<char *>(chunk), sizeof(chunk));
        if (n == -ESP_ERR_HTTP_EAGAIN) continue;
        if (!n) break; // Cached body must be drained even if headers already completed it.
        if (n < 0) goto finished;
        if (static_cast<size_t>(n) > AUDIO_MAX - job.length) goto finished;
        memcpy(job.audio + job.length, chunk, n);
        job.length += n;
    }
    ok = alive(job) && job.length && esp_http_client_is_complete_data_received(client) && decodable(job);
finished:
    esp_http_client_cleanup(client);
    if (!ok) job.length = 0;
    return ok;
}

static void worker(void *)
{
    for (;;) {
        job_t *job;
        if (xQueueReceive(s_queue, &job, portMAX_DELAY) != pdTRUE) continue;
        job->ok = fetch(*job, CONFIG_MUSE_LOCAL_TTS_URL);
        if (!job->ok && alive(*job) && CONFIG_MUSE_LOCAL_TTS_FALLBACK_URL[0])
            job->ok = fetch(*job, CONFIG_MUSE_LOCAL_TTS_FALLBACK_URL);
        job->done.store(true, std::memory_order_release);
        // No access to job after publication: the caller may free it immediately.
    }
}

bool muse_local_tts_configured(void) { return CONFIG_MUSE_LOCAL_TTS_URL[0]; }
bool muse_local_tts_pending(void) { return s_job != nullptr; }
void muse_local_tts_reap(void)
{
    if (s_job && s_job->epoch != s_epoch.load() && s_job->done.load(std::memory_order_acquire)) {
        release(s_job);
        s_job = nullptr;
    }
}
void muse_local_tts_cancel(void)
{
    ++s_epoch;
    muse_local_tts_reap();
}
bool muse_local_tts_begin(const char *text)
{
    if (!muse_local_tts_configured()) return false;
    if (s_job) {
        if (!s_job->done.load(std::memory_order_acquire)) return false; // Bounded backpressure.
        release(s_job);
        s_job = nullptr;
    }
    if (!s_queue) {
        s_queue = xQueueCreate(1, sizeof(job_t *));
        if (!s_queue) return false;
        if (xTaskCreatePinnedToCoreWithCaps(worker, "muse_tts", 16 * 1024, nullptr, 4, nullptr, 0,
                MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) != pdPASS) {
            vQueueDelete(s_queue);
            s_queue = nullptr;
            return false;
        }
    }
    auto *memory = allocate(sizeof(job_t));
    if (!memory) return false;
    auto *job = new (memory) job_t;
    job->epoch = ++s_epoch;
    job->deadline = esp_timer_get_time() + DEADLINE_US;
    if (!muse_tts_json(text, 700, job->json, sizeof(job->json), nullptr) ||
        xQueueSend(s_queue, &job, 0) != pdTRUE) {
        release(job);
        return false;
    }
    s_job = job;
    return true;
}
enum muse_local_tts_result muse_local_tts_take(uint8_t *out, size_t capacity, size_t *length)
{
    if (length) *length = 0;
    if (!s_job) return MUSE_LOCAL_FAILED;
    if (!s_job->done.load(std::memory_order_acquire)) return MUSE_LOCAL_PENDING;
    bool ok = alive(*s_job) && s_job->ok && out && length && s_job->length <= capacity;
    if (ok) {
        memcpy(out, s_job->audio, s_job->length);
        *length = s_job->length;
    }
    release(s_job);
    s_job = nullptr;
    return ok ? MUSE_LOCAL_READY : MUSE_LOCAL_FAILED;
}
