from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SpeechEngineTests(unittest.TestCase):
    def test_production_adapter_chunks_reset_and_failed_initialization(self):
        headers = {
            'esp_err.h': '''#pragma once
typedef int esp_err_t;
enum { ESP_OK, ESP_ERR_INVALID_ARG, ESP_ERR_INVALID_STATE, ESP_ERR_NOT_FOUND,
       ESP_ERR_NOT_SUPPORTED, ESP_ERR_NO_MEM };
const char *esp_err_to_name(int error);
''',
            'esp_heap_caps.h': '''#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
void *heap_caps_calloc(size_t count, size_t size, int caps);
void heap_caps_free(void *pointer);
''',
            'esp_log.h': '#define ESP_LOGI(tag, ...) ((void)(tag))\n#define ESP_LOGW(tag, ...) ((void)(tag))\n',
            'model_path.h': '''#pragma once
typedef struct { int num; char **model_name; } srmodel_list_t;
srmodel_list_t *esp_srmodel_init(const char *name);
void esp_srmodel_deinit(srmodel_list_t *models);
''',
            'esp_vad.h': '''#pragma once
#include <stdint.h>
typedef void *vad_handle_t;
enum { VAD_MODE_2 = 2, VAD_SILENCE = 0, VAD_SPEECH = 1 };
vad_handle_t vad_create(int mode);
void vad_destroy(vad_handle_t data);
void vad_reset_trigger(vad_handle_t data);
int vad_process(vad_handle_t data, int16_t *pcm, int rate, int milliseconds);
''',
            'esp_wn_models.h': '''#pragma once
#include <stdint.h>
typedef struct model_iface_data_t model_iface_data_t;
enum { DET_MODE_95 = 1, WAKENET_DETECTED = 1 };
typedef struct {
 model_iface_data_t *(*create)(const void *, int);
 int (*get_samp_rate)(model_iface_data_t *);
 int (*get_channel_num)(model_iface_data_t *);
 int (*get_samp_chunksize)(model_iface_data_t *);
 int (*detect)(model_iface_data_t *, int16_t *);
 void (*clean)(model_iface_data_t *);
 void (*destroy)(model_iface_data_t *);
} esp_wn_iface_t;
const esp_wn_iface_t *esp_wn_handle_from_name(const char *name);
''',
        }
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "muse_sr_engine.h"
#include "esp_wn_models.h"
#include "esp_vad.h"
#include "model_path.h"
struct model_iface_data_t { int unused; };
static struct model_iface_data_t instance;
static char *names[] = {"wn9_histackchan_tts3"};
static srmodel_list_t models = {1, names};
static int allocations, model_inits, detects, vads, cleans, destroys;
static int rate = 16000, channels = 1, samples = 512, expected = 1, detection = 1;
static bool fail_memory, fail_vad, fail_model;
esp_err_t muse_sr_partition_validate(void) { return ESP_OK; }
const char *esp_err_to_name(int error) { (void)error; return "test"; }
void *heap_caps_calloc(size_t n, size_t size, int caps) {
 (void)caps; if (fail_memory) return NULL;
 void *p = calloc(n, size); if (p) ++allocations; return p;
}
void heap_caps_free(void *p) { if (p) --allocations; free(p); }
srmodel_list_t *esp_srmodel_init(const char *name) {
 assert(!strcmp(name, "model")); ++model_inits; return fail_model ? NULL : &models;
}
void esp_srmodel_deinit(srmodel_list_t *m) { assert(m == &models); }
static model_iface_data_t *create(const void *name, int mode) {
 assert(!strcmp(name, names[0]) && mode == DET_MODE_95); return &instance;
}
static int get_rate(model_iface_data_t *m) { (void)m; return rate; }
static int get_channels(model_iface_data_t *m) { (void)m; return channels; }
static int get_samples(model_iface_data_t *m) { (void)m; return samples; }
static int detect(model_iface_data_t *m, int16_t *pcm) {
 assert(m == &instance);
 for (int i = 0; i < samples; ++i) assert(pcm[i] == expected);
 ++detects; return detection;
}
static void clean(model_iface_data_t *m) { assert(m == &instance); ++cleans; }
static void destroy(model_iface_data_t *m) { assert(m == &instance); ++destroys; }
const esp_wn_iface_t *esp_wn_handle_from_name(const char *name) {
 static const esp_wn_iface_t api = {create, get_rate, get_channels, get_samples, detect, clean, destroy};
 assert(!strcmp(name, names[0])); return &api;
}
vad_handle_t vad_create(int mode) { assert(mode == VAD_MODE_2); return fail_vad ? NULL : &instance; }
void vad_destroy(vad_handle_t m) { assert(m == &instance); }
void vad_reset_trigger(vad_handle_t m) { assert(m == &instance); }
int vad_process(vad_handle_t m, int16_t *pcm, int hz, int ms) {
 assert(m == &instance && hz == 16000 && ms == 30);
 for (int i = 0; i < 480; ++i) assert(pcm[i] == expected);
 ++vads; return VAD_SPEECH;
}
int main(void) {
 int16_t pcm[960]; for (int i = 0; i < 960; ++i) pcm[i] = 1;
 muse_sr_result_t r;
 assert(muse_sr_engine_feed(pcm, 320, true, true, &r) == ESP_ERR_INVALID_STATE);
 assert(muse_sr_engine_init() == ESP_OK && allocations == 1);
 int inits = model_inits; assert(muse_sr_engine_init() == ESP_OK && model_inits == inits);
 assert(muse_sr_engine_feed(pcm, 320, true, true, &r) == ESP_OK);
 assert(!r.wake && !r.speech_ms && !detects && !vads);
 assert(muse_sr_engine_feed(pcm, 192, true, true, &r) == ESP_OK);
 assert(r.wake && r.speech_ms == 30 && detects == 1 && vads == 1);
 assert(muse_sr_engine_feed(pcm, 960, true, true, &r) == ESP_OK);
 assert(r.wake && r.speech_ms == 60);
 int before = detects, before_vad = vads, before_clean = cleans;
 assert(muse_sr_engine_feed(pcm, 320, false, false, &r) == ESP_OK);
 assert(!r.wake && !r.speech_ms && detects == before && vads == before_vad && cleans > before_clean);
 for (int i = 0; i < 960; ++i) pcm[i] = 2; expected = 2;
 assert(muse_sr_engine_feed(pcm, 320, true, true, &r) == ESP_OK);
 assert(!r.wake && !r.speech_ms);
 assert(muse_sr_engine_feed(pcm, 192, true, true, &r) == ESP_OK);
 assert(r.wake && r.speech_ms == 30);
 muse_sr_engine_reset(); detection = -1;
 assert(muse_sr_engine_feed(pcm, 512, true, false, &r) == ESP_OK && !r.wake && !r.speech_ms);
 assert(muse_sr_engine_feed(pcm, 961, true, true, &r) == ESP_ERR_INVALID_ARG);
 assert(muse_sr_engine_feed(NULL, 320, true, true, &r) == ESP_ERR_INVALID_ARG);
 muse_sr_engine_deinit(); muse_sr_engine_deinit(); assert(allocations == 0);
 models.num = 0; assert(muse_sr_engine_init() == ESP_ERR_NOT_FOUND && allocations == 0); models.num = 1;
 rate = 48000; assert(muse_sr_engine_init() == ESP_ERR_NOT_SUPPORTED && allocations == 0); rate = 16000;
 channels = 2; assert(muse_sr_engine_init() == ESP_ERR_NOT_SUPPORTED && allocations == 0); channels = 1;
 samples = 4096; assert(muse_sr_engine_init() == ESP_ERR_NOT_SUPPORTED && allocations == 0); samples = 512;
 fail_memory = true; assert(muse_sr_engine_init() == ESP_ERR_NO_MEM && allocations == 0); fail_memory = false;
 fail_vad = true; assert(muse_sr_engine_init() == ESP_ERR_NO_MEM && allocations == 0); fail_vad = false;
 fail_model = true; assert(muse_sr_engine_init() == ESP_ERR_NOT_FOUND && allocations == 0); fail_model = false;
 assert(muse_sr_engine_init() == ESP_OK); muse_sr_engine_deinit(); assert(allocations == 0 && destroys > 0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, content in headers.items():
                (path / name).write_text(content)
            (path / 'test.c').write_text(source)
            base = ROOT / 'firmware/esp32/components/muse'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(path), '-I', str(base),
                            str(path / 'test.c'), str(base / 'muse_sr_engine.c'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)
