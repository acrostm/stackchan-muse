// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>
#include "sw_proxy_core.h"
esp_err_t sw_proxy_init(void);
void sw_proxy_get(sw_proxy_config_t *out);
void sw_proxy_get_for(const char *ssid, sw_proxy_config_t *out);
void sw_proxy_snapshot(sw_proxy_profiles_t *out);
esp_err_t sw_proxy_save_for(const char *ssid, const sw_proxy_config_t *config);
bool sw_proxy_request(const char *host, uint16_t port);
void sw_proxy_tick(void);
bool sw_proxy_muse_enabled(void);
