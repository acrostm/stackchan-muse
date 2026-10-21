// SPDX-License-Identifier: Apache-2.0
#include "sw_runtime.h"
#include "sw_proxy.h"
#include "muse_chat.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "muse_link.h"
#include "muse_notice.h"
#include "muse_voice.h"
#include "muse_ptt_guard.h"
#include "host/ble_gap.h"
#include "host/ble_hs.h"
#include "esp_heap_caps.h"
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include <string.h>

static SemaphoreHandle_t lock;
static sw_config_t config;
static char tts_status[48] = "Not configured";
extern esp_err_t sw_tts_init(void);
extern esp_err_t sw_portal_init(void);

esp_err_t sw_runtime_start(void)
{
    lock = xSemaphoreCreateMutex();
    if (!lock) return ESP_ERR_NO_MEM;
    strcpy(config.speaker, "zh_female_vv_uranus_bigtts");
#if !CONFIG_SPIRAM
    strlcpy(tts_status, "Unavailable without PSRAM", sizeof(tts_status));
    return ESP_OK;   /* preserve the board's original Link text path */
#else
    nvs_handle_t nvs;
    if (nvs_open("sw_muse", NVS_READONLY, &nvs) == ESP_OK) {
        size_t n = sizeof(config);
        sw_config_t saved = {0};
        if (nvs_get_blob(nvs, "tts_v1", &saved, &n) == ESP_OK && n == sizeof(saved)) {
            saved.api_key[256] = saved.access_key[256] = 0;
            saved.app_id[64] = saved.speaker[128] = 0;
            config = saved;
        }
        nvs_close(nvs);
    }
    strcpy(tts_status, sw_config_ready(&config) ? "Ready (not tested)" : "Not configured");
    esp_err_t err = sw_proxy_init();
    if (err != ESP_OK) return err;
    err = sw_tts_init();
    if (err != ESP_OK) return err;
    return sw_portal_init();
#endif
}

void sw_config_get(sw_config_t *out)
{
    xSemaphoreTake(lock, portMAX_DELAY); *out = config; xSemaphoreGive(lock);
}

esp_err_t sw_config_save(const sw_config_t *c)
{
    if (!sw_header_safe(c->api_key, 256) || !sw_header_safe(c->access_key, 256) ||
        !sw_header_safe(c->app_id, 64) || !sw_header_safe(c->speaker, 128) || !c->speaker[0])
        return ESP_ERR_INVALID_ARG;
    nvs_handle_t nvs;
    xSemaphoreTake(lock, portMAX_DELAY);
    esp_err_t err = nvs_open("sw_muse", NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "tts_v1", c, sizeof(*c));
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err == ESP_OK) {
        config = *c;
        strcpy(tts_status, sw_config_ready(&config) ? "Ready (not tested)" : "Not configured");
    }
    xSemaphoreGive(lock);
    return err;
}

void sw_tts_set_status(const char *s)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    sw_text_copy(tts_status, sizeof(tts_status), s);
    xSemaphoreGive(lock);
}
void sw_tts_status(char *out, size_t cap)
{
    xSemaphoreTake(lock, portMAX_DELAY); sw_text_copy(out, cap, tts_status); xSemaphoreGive(lock);
}

extern bool sw_voice_probe(void);
bool sw_console_command(const char *line)
{
    if (!strcmp(line, "sr.probe")) {
        printf("@sr.probe %s\n", muse_voice_request_sr_probe() ? "queued" : "unavailable");
        return true;
    }
#if !CONFIG_SPIRAM
    if (!strcmp(line, "sw.cancel")) {
        sw_capture_cancel();
        printf("@sw.cancel requested\n");
        return true;
    }
    return false;
#else
    if (!strcmp(line, "sw.setup")) {
        sw_portal_request(); printf("@sw.setup requested\n");
    } else if (!strcmp(line, "sw.setup.close")) {
        sw_portal_close(); printf("@sw.setup.close requested\n");
    } else if (!strcmp(line, "sw.setup.info")) {
        char ssid[33], pin[17]; bool on;
        sw_portal_info(ssid, sizeof(ssid), pin, sizeof(pin), &on);
        printf("@sw.setup.info {\"on\":%s,\"ssid\":\"%s\",\"pin\":\"%s\"}\n",
               on ? "true" : "false", ssid, pin);
        memset(pin, 0, sizeof(pin));
    } else if (!strncmp(line, "sw.notice=", 10)) {
        printf("@sw.notice %s\n",
               muse_notice_publish("sw-console-test", line + 10) ? "queued" : "rejected");
    } else if (!strcmp(line, "sw.cancel")) {
        sw_capture_cancel(); printf("@sw.cancel requested\n");
    } else if (!strncmp(line, "sw.proxy=", 9)) {
        const char *value = line + 9;char host[16], tail;unsigned port;
        bool ok = !strcmp(value, "off") ? sw_proxy_request("",0) :
            sscanf(value,"%15[0-9.]:%u%c",host,&port,&tail)==2 && port>0 && port<=65535 && sw_proxy_request(host,port);
        printf("@sw.proxy %s\n",ok?"queued; restarts after save":"invalid LAN IPv4 or port");
    } else if (!strcmp(line, "sw.pair")) {
        sw_pairing_request(); printf("@sw.pair requested\n");
    } else if (!strcmp(line, "sw.preview")) {
        printf("@sw.preview %s\n", sw_voice_probe() ? "queued" : "busy or no TTS credentials");
    } else if (!strcmp(line, "sw.status")) {
        sw_config_t c; sw_config_get(&c);
        sw_proxy_config_t proxy; sw_proxy_get(&proxy);
        muse_hatch_status_t hatch; muse_hatch_status(&hatch);
        printf("@sw.status {\"sdk_configured\":%s,\"tts_configured\":%s,\"tts_api_key\":%s,\"tts_legacy\":%s,\"ble_started\":%s,\"ble_advertising\":%s,\"ble_synced\":%s,\"ble_connection\":%s,\"paired\":%s,\"proxy_enabled\":%s,\"internal_free\":%u,\"internal_largest\":%u}\n",
            muse_link_sdk_token() ? "true" : "false", sw_config_ready(&c) ? "true" : "false",
            c.api_key[0] ? "true" : "false", c.app_id[0] && c.access_key[0] ? "true" : "false",
            muse_link_ble_started() ? "true" : "false", ble_gap_adv_active() ? "true" : "false",
            ble_hs_synced() ? "true" : "false", sw_pairing_connected() ? "true" : "false",
            muse_link_hatch_linked() ? "true" : "false",
            proxy.enabled ? "true" : "false",
            (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
            (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));
        printf("@sw.cloud state=%s\n",muse_hatch_state_name(hatch.state));
        memset(&c, 0, sizeof(c));
    } else return false;
    fflush(stdout); return true;
#endif
}

const char *sw_ble_state(void)
{
    if (!muse_link_ble_started() || !ble_hs_synced()) return "starting";
    if (sw_pairing_connected()) return "connected";
    return ble_gap_adv_active() ? "advertising" : "idle";
}

static uint32_t s_capture_turn;
void sw_capture_press(void) {
    s_capture_turn = muse_ptt_press(esp_timer_get_time());
}
void sw_capture_release(void) {
    muse_ptt_release_current(esp_timer_get_time());
}
void sw_capture_cancel(void) {
    muse_ptt_cancel_current();
}
sw_ptt_result_t sw_capture_result(void) {
    const sw_ptt_result_t result = (sw_ptt_result_t)muse_ptt_result(s_capture_turn);
    muse_ptt_retire(s_capture_turn);
    s_capture_turn = 0;
    return result;
}
