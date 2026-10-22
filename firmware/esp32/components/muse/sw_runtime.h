// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "sw_core.h"
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    char api_key[257], app_id[65], access_key[257], speaker[129];
} sw_config_t;
static inline bool sw_config_ready(const sw_config_t *c) {
    return c->speaker[0] && (c->api_key[0] || (c->app_id[0] && c->access_key[0]));
}
void sw_capture_press(void);
void sw_capture_release(void);
void sw_capture_cancel(void);
sw_ptt_result_t sw_capture_result(void);
esp_err_t sw_runtime_start(void);
/* Non-blocking console diagnostics; never prints credentials. */
bool sw_console_command(const char *line);
void sw_pairing_request(void);
const char *sw_ble_state(void);
/* Link bridge: called only by the setup worker, never from a button callback. */
void sw_pairing_tick(bool restart);
bool sw_pairing_connected(void);
void sw_config_get(sw_config_t *out);
esp_err_t sw_config_save(const sw_config_t *config);
void sw_tts_status(char *out, size_t cap);
void sw_tts_set_status(const char *text);
void sw_portal_request(void);
void sw_portal_close(void);
void sw_portal_info(char *ssid, size_t ssid_cap, char *pass, size_t pass_cap, bool *on);
/* A single TTS worker, generation-cancelled; PCM16 mono at 16 kHz. */
bool sw_tts_start(const char *text);
void sw_tts_cancel(void);
size_t sw_tts_read(void *out, size_t cap);
bool sw_tts_done(void);
bool sw_tts_succeeded(void);
#ifdef __cplusplus
}
#endif
