// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "sw_runtime.h"
#include "cJSON.h"
#include "esp_http_server.h"
esp_err_t sw_voice_init(void);
/* Called only after AP/subnet and CSRF validation by the portal. */
esp_err_t sw_voice_submit(httpd_req_t *request, cJSON *body, bool preview);
esp_err_t sw_voice_result(httpd_req_t *request);
/* Preview uses its own bounded PCM sink and never changes the dialogue queue. */
bool sw_tts_preview(const sw_config_t *config, unsigned char *pcm, size_t cap, size_t *size,
                    char *error, size_t error_cap);
