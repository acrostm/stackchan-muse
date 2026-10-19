// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool sw_proxy_target(const char *host);
bool sw_proxy_lan_ipv4(const char *host);
size_t sw_socks_request(const char *host, uint16_t port, unsigned char *out, size_t cap);

#define SW_PROXY_PROFILES_MAX 8
typedef struct { char host[16]; uint16_t port; bool enabled; } sw_proxy_config_t;
typedef struct { char ssid[33]; sw_proxy_config_t proxy; } sw_proxy_profile_t;
typedef struct { sw_proxy_profile_t entries[SW_PROXY_PROFILES_MAX]; } sw_proxy_profiles_t;
void sw_proxy_profile_get(const sw_proxy_profiles_t *profiles, const char *ssid, sw_proxy_config_t *out);
bool sw_proxy_profile_set(sw_proxy_profiles_t *profiles, const char *ssid, const sw_proxy_config_t *config);
bool sw_proxy_profiles_valid(const sw_proxy_profiles_t *profiles);

/* A Wi-Fi credential change already causes the SDK to reconnect after saving. */
bool sw_proxy_restart_needed(const sw_proxy_config_t *old, const sw_proxy_config_t *next, bool active_network, bool wifi_update);
