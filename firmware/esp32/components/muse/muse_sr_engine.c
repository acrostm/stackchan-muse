// SPDX-License-Identifier: Apache-2.0
#include "muse_sr_engine.h"
#include "muse_sr_partition.h"
#include <string.h>
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_vad.h"
#include "esp_wn_models.h"
#include "model_path.h"

#define MODEL_NAME "wn9_histackchan_tts3"
#define SAMPLE_RATE 16000
#define VAD_SAMPLES 480
#define MAX_FEED_SAMPLES 960

static const char *TAG = "muse_sr";
static srmodel_list_t *s_models;
static const esp_wn_iface_t *s_wake;
static model_iface_data_t *s_wake_data;
static vad_handle_t s_vad;
static int16_t *s_wake_pcm;
static int16_t s_vad_pcm[VAD_SAMPLES];
static size_t s_wake_samples, s_wake_used, s_vad_used;
static bool s_ready, s_wake_active, s_vad_active;

void muse_sr_engine_reset(void)
{
    s_wake_used = s_vad_used = 0;
    s_wake_active = s_vad_active = false;
    if (s_wake_data && s_wake && s_wake->clean) s_wake->clean(s_wake_data);
    if (s_vad) vad_reset_trigger(s_vad);
    if (s_wake_pcm) memset(s_wake_pcm, 0, s_wake_samples * sizeof(int16_t));
    memset(s_vad_pcm, 0, sizeof(s_vad_pcm));
}

void muse_sr_engine_deinit(void)
{
    s_ready = false;
    muse_sr_engine_reset();
    if (s_wake_data && s_wake && s_wake->destroy) s_wake->destroy(s_wake_data);
    if (s_vad) vad_destroy(s_vad);
    if (s_models) esp_srmodel_deinit(s_models);
    heap_caps_free(s_wake_pcm);
    s_models = NULL; s_wake = NULL; s_wake_data = NULL;
    s_vad = NULL; s_wake_pcm = NULL; s_wake_samples = 0;
}

esp_err_t muse_sr_engine_init(void)
{
    if (s_ready) return ESP_OK;
    esp_err_t checked = muse_sr_partition_validate();
    if (checked != ESP_OK) return checked;
    s_models = esp_srmodel_init("model");
    if (!s_models) return ESP_ERR_NOT_FOUND;
    const char *name = NULL;
    for (int i = 0; i < s_models->num; ++i)
        if (!strcmp(s_models->model_name[i], MODEL_NAME)) name = s_models->model_name[i];
    esp_err_t error = ESP_ERR_NOT_FOUND;
    if (!name) goto failed;
    s_wake = esp_wn_handle_from_name(name);
    error = ESP_ERR_NOT_SUPPORTED;
    if (!s_wake || !s_wake->create || !s_wake->detect || !s_wake->clean ||
        !s_wake->destroy || !s_wake->get_samp_rate || !s_wake->get_channel_num ||
        !s_wake->get_samp_chunksize) goto failed;
    s_wake_data = s_wake->create(name, DET_MODE_95);
    error = ESP_ERR_NO_MEM;
    if (!s_wake_data) goto failed;
    error = ESP_ERR_NOT_SUPPORTED;
    if (s_wake->get_samp_rate(s_wake_data) != SAMPLE_RATE ||
        s_wake->get_channel_num(s_wake_data) != 1) goto failed;
    const int samples = s_wake->get_samp_chunksize(s_wake_data);
    if (samples < 80 || samples > 2048) goto failed;
    s_wake_samples = (size_t)samples;
    s_wake_pcm = heap_caps_calloc(s_wake_samples, sizeof(int16_t),
                                  MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    s_vad = vad_create(VAD_MODE_2);
    error = ESP_ERR_NO_MEM;
    if (!s_wake_pcm || !s_vad) goto failed;
    muse_sr_engine_reset();
    s_ready = true;
    ESP_LOGI(TAG, "local wake model ready: %s, %u samples", MODEL_NAME, (unsigned)s_wake_samples);
    return ESP_OK;
failed:
    ESP_LOGW(TAG, "local wake unavailable: %s; manual talk remains available", esp_err_to_name(error));
    muse_sr_engine_deinit();
    return error;
}

esp_err_t muse_sr_engine_feed(const int16_t *pcm, size_t frames,
                               bool allow_wake, bool allow_vad,
                               muse_sr_result_t *result)
{
    if (!result) return ESP_ERR_INVALID_ARG;
    *result = (muse_sr_result_t){0};
    if (!s_ready) return ESP_ERR_INVALID_STATE;
    if (!pcm || !frames || frames > MAX_FEED_SAMPLES) return ESP_ERR_INVALID_ARG;
    if (!allow_wake && s_wake_active) {
        s_wake_used = 0;
        s_wake->clean(s_wake_data);
        memset(s_wake_pcm, 0, s_wake_samples * sizeof(int16_t));
    }
    if (!allow_vad && s_vad_active) {
        s_vad_used = 0;
        vad_reset_trigger(s_vad);
        memset(s_vad_pcm, 0, sizeof(s_vad_pcm));
    }
    s_wake_active = allow_wake;
    s_vad_active = allow_vad;
    for (size_t i = 0; i < frames; ++i) {
        if (allow_wake) {
            s_wake_pcm[s_wake_used++] = pcm[i];
            if (s_wake_used == s_wake_samples) {
                result->wake |= s_wake->detect(s_wake_data, s_wake_pcm) == WAKENET_DETECTED;
                s_wake_used = 0;
            }
        }
        if (allow_vad) {
            s_vad_pcm[s_vad_used++] = pcm[i];
            if (s_vad_used == VAD_SAMPLES) {
                if (vad_process(s_vad, s_vad_pcm, SAMPLE_RATE, 30) == VAD_SPEECH)
                    result->speech_ms += 30;
                s_vad_used = 0;
            }
        }
    }
    return ESP_OK;
}
