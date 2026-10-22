// SPDX-License-Identifier: Apache-2.0
#include "sw_runtime.h"
#include "sw_net.h"
#include "sw_voice.h"
#include "sw_proxy.h"
#include "sw_proxy_core.h"
#include "esp_system.h"
#include "muse_link.h"
#include "muse_settings.h"
#include "muse_wifi.h"
#include "muse_state.h"
#include "muse_voice.h"
#include "muse_notice.h"
#include "cJSON.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { sw_config_t tts; sw_proxy_config_t proxy; char ssid[33], pass[65], sdk[49]; bool wifi_update; } update_t;
static QueueHandle_t updates;
static SemaphoreHandle_t info_lock;
static atomic_bool requested, close_requested, pairing_requested;
static bool active;
static char ap_name[33], ap_pass[9], csrf[33];
static const char *TAG = "muse_setup";
static httpd_handle_t server;
static esp_netif_t *ap_netif;
extern const unsigned char sw_html_start[] asm("_binary_sw_portal_html_start");
extern const unsigned char sw_html_end[] asm("_binary_sw_portal_html_end");

void sw_portal_request(void) { atomic_store(&requested, true); }
void sw_portal_close(void) { atomic_store(&close_requested, true); }
void sw_pairing_request(void) { atomic_store(&pairing_requested, true); }

void sw_portal_info(char *ssid, size_t sc, char *pass, size_t pc, bool *on)
{
    xSemaphoreTake(info_lock, portMAX_DELAY);
    sw_text_copy(ssid, sc, ap_name); sw_text_copy(pass, pc, ap_pass); *on = active;
    xSemaphoreGive(info_lock);
}

static bool allowed(httpd_req_t *r)
{
    struct sockaddr_storage addr = {0}, local = {0};
    socklen_t size = sizeof(addr), local_size = sizeof(local);
    esp_netif_ip_info_t ip;
    if (!ap_netif || esp_netif_get_ip_info(ap_netif, &ip) != ESP_OK ||
        getpeername(httpd_req_to_sockfd(r), (struct sockaddr *)&addr, &size) ||
        getsockname(httpd_req_to_sockfd(r), (struct sockaddr *)&local, &local_size)) return false;
    return sw_setup_peer_allowed((const struct sockaddr *)&addr, size,
            (const struct sockaddr *)&local, local_size, ip.ip.addr, ip.netmask.addr);
}

static esp_err_t reply(httpd_req_t *r, const char *status, const char *body)
{
    httpd_resp_set_status(r, status);
    httpd_resp_set_type(r, "application/json");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    httpd_resp_set_hdr(r, "X-Content-Type-Options", "nosniff");
    httpd_resp_set_hdr(r, "Connection", "close");
    return httpd_resp_sendstr(r, body);
}

static esp_err_t page(httpd_req_t *r)
{
    if (!allowed(r)) return reply(r, "403 Forbidden", "{}");
    httpd_resp_set_type(r, "text/html; charset=utf-8");
    httpd_resp_set_hdr(r, "Connection", "close");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    httpd_resp_set_hdr(r, "Content-Security-Policy", "default-src 'self'; media-src 'self' blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'");
    return httpd_resp_send(r, (const char *)sw_html_start, sw_html_end - sw_html_start);
}

static void notice_json(cJSON *body)
{
    const muse_notice_status_t status = muse_notice_status();
    cJSON_AddBoolToObject(body, "ready", status.ready);
    cJSON_AddBoolToObject(body, "clock_ready", status.clock_ready);
    cJSON_AddBoolToObject(body, "quiet_now", status.quiet_now);
    cJSON_AddBoolToObject(body, "can_read", status.can_read);
    cJSON_AddBoolToObject(body, "read_requested", status.read_requested);
    cJSON_AddBoolToObject(body, "reading", status.reading);
    cJSON_AddNumberToObject(body, "unread", status.unread);
    cJSON_AddBoolToObject(body, "muted", status.policy.muted);
    cJSON_AddBoolToObject(body, "quiet_enabled", status.policy.quiet_enabled);
    cJSON_AddNumberToObject(body, "start_minute", status.policy.start_minute);
    cJSON_AddNumberToObject(body, "end_minute", status.policy.end_minute);
    cJSON_AddNumberToObject(body, "utc_offset_minute", status.policy.utc_offset_minute);
}

static bool notice_integer(cJSON *value, int minimum, int maximum)
{
    return cJSON_IsNumber(value) && value->valuedouble >= minimum &&
           value->valuedouble <= maximum && value->valuedouble == value->valueint;
}

static esp_err_t notice_control(httpd_req_t *r)
{
    char token[40];
    if (!allowed(r) || httpd_req_get_hdr_value_str(r, "X-Setup-Token", token, sizeof(token)) != ESP_OK || strcmp(token, csrf))
        return reply(r, "403 Forbidden", "{}");
    if (r->content_len < 2 || r->content_len > 160) return reply(r, "413 Content Too Large", "{}");
    char buf[161] = {0}; size_t got = 0;
    while (got < (size_t)r->content_len) {
        int n = httpd_req_recv(r, buf + got, r->content_len - got);
        if (n <= 0) return reply(r, "400 Bad Request", "{}");
        got += n;
    }
    const char *end = NULL;
    cJSON *body = cJSON_ParseWithLengthOpts(buf, got + 1, &end, true);
    if (end != buf + got || !cJSON_IsObject(body)) {
        cJSON_Delete(body); return reply(r, "400 Bad Request", "{}");
    }
    bool accepted = false;
    const bool read = !strcmp(r->uri, "/notice-read");
    if (read) {
        if (cJSON_GetArraySize(body) != 0) {
            cJSON_Delete(body); return reply(r, "400 Bad Request", "{}");
        }
        accepted = muse_notice_request_read();
    } else {
        cJSON *muted = cJSON_GetObjectItemCaseSensitive(body, "muted");
        cJSON *quiet = cJSON_GetObjectItemCaseSensitive(body, "quiet_enabled");
        cJSON *start = cJSON_GetObjectItemCaseSensitive(body, "start_minute");
        cJSON *finish = cJSON_GetObjectItemCaseSensitive(body, "end_minute");
        cJSON *offset = cJSON_GetObjectItemCaseSensitive(body, "utc_offset_minute");
        if (cJSON_GetArraySize(body) != 5 || !cJSON_IsBool(muted) || !cJSON_IsBool(quiet) ||
            !notice_integer(start, 0, 1439) || !notice_integer(finish, 0, 1439) ||
            !notice_integer(offset, -720, 840)) {
            cJSON_Delete(body); return reply(r, "400 Bad Request", "{}");
        }
        const muse_notice_policy_t policy = {.muted = cJSON_IsTrue(muted),
            .quiet_enabled = cJSON_IsTrue(quiet), .start_minute = start->valueint,
            .end_minute = finish->valueint, .utc_offset_minute = offset->valueint};
        accepted = muse_notice_set_policy(&policy) == ESP_OK;
    }
    cJSON_Delete(body);
    if (!accepted) return reply(r, read ? "409 Conflict" : "503 Service Unavailable", "{}");
    body = cJSON_CreateObject(); notice_json(body);
    char *text = cJSON_PrintUnformatted(body); cJSON_Delete(body);
    esp_err_t result = reply(r, text ? (read ? "202 Accepted" : "200 OK") : "503 Service Unavailable", text ? text : "{}");
    free(text); return result;
}

static void handsfree_json(cJSON *body)
{
    const muse_voice_handsfree_status_t status = muse_voice_handsfree_status();
    cJSON_AddBoolToObject(body, "supported", status.supported);
    cJSON_AddBoolToObject(body, "requested", status.requested);
    cJSON_AddBoolToObject(body, "enabled", status.enabled);
    cJSON_AddStringToObject(body, "state", status.state);
}

static esp_err_t handsfree_control(httpd_req_t *r)
{
    char token[40];
    if (!allowed(r) || httpd_req_get_hdr_value_str(r, "X-Setup-Token", token, sizeof(token)) != ESP_OK || strcmp(token, csrf))
        return reply(r, "403 Forbidden", "{}");
    if (r->content_len < 2 || r->content_len > 32) return reply(r, "413 Content Too Large", "{}");
    char buf[33] = {0};
    size_t got = 0;
    while (got < (size_t)r->content_len) {
        int n = httpd_req_recv(r, buf + got, r->content_len - got);
        if (n <= 0) return reply(r, "400 Bad Request", "{}");
        got += n;
    }
    const char *end = NULL;
    cJSON *body = cJSON_ParseWithLengthOpts(buf, got + 1, &end, true);
    cJSON *enabled = cJSON_GetObjectItemCaseSensitive(body, "enabled");
    if (end != buf + got || !cJSON_IsObject(body) || cJSON_GetArraySize(body) != 1 || !cJSON_IsBool(enabled)) {
        cJSON_Delete(body);
        return reply(r, "400 Bad Request", "{}");
    }
    const bool accepted = muse_voice_set_handsfree(cJSON_IsTrue(enabled));
    cJSON_Delete(body);
    if (!accepted) return reply(r, "503 Service Unavailable", "{}");
    body = cJSON_CreateObject();
    handsfree_json(body);
    char *text = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    const esp_err_t result = reply(r, text ? "202 Accepted" : "503 Service Unavailable", text ? text : "{}");
    free(text);
    return result;
}

static esp_err_t session(httpd_req_t *r)
{
    if (!allowed(r)) return reply(r, "403 Forbidden", "{}");
    sw_config_t config; sw_config_get(&config);
    cJSON *body = cJSON_CreateObject();
    cJSON_AddStringToObject(body, "csrf", csrf);
    notice_json(cJSON_AddObjectToObject(body, "notices"));
    handsfree_json(cJSON_AddObjectToObject(body, "handsfree"));
    cJSON_AddStringToObject(body, "speaker", config.speaker);
    cJSON_AddBoolToObject(body, "tts_configured", sw_config_ready(&config));
    cJSON_AddBoolToObject(body, "sdk_configured", muse_link_sdk_token() != NULL);
    cJSON_AddStringToObject(body, "bluetooth", sw_ble_state());
    cJSON_AddBoolToObject(body, "paired", muse_link_hatch_linked());
    char wifi_ssid[33], wifi_pass[65]; muse_settings_wifi(wifi_ssid, wifi_pass); memset(wifi_pass,0,sizeof(wifi_pass));
    wifi_ap_record_t current_ap;
    if (esp_wifi_sta_get_ap_info(&current_ap)==ESP_OK) { memcpy(wifi_ssid,current_ap.ssid,32);wifi_ssid[32]=0; }
    cJSON_AddStringToObject(body, "wifi_ssid", wifi_ssid);
    muse_wifi_saved_t saved[MUSE_WIFI_SAVED_MAX];
    int saved_count=muse_wifi_saved(saved,MUSE_WIFI_SAVED_MAX);
    cJSON *networks=cJSON_AddArrayToObject(body,"wifi_saved");
    for(int i=0;i<saved_count;++i) cJSON_AddItemToArray(networks,cJSON_CreateString(saved[i].ssid));
    sw_proxy_profiles_t profiles; sw_proxy_snapshot(&profiles);
    cJSON *list = cJSON_AddArrayToObject(body, "proxy_profiles");
    for (unsigned i=0; i<SW_PROXY_PROFILES_MAX; ++i) if (profiles.entries[i].ssid[0]) {
        cJSON *item = cJSON_CreateObject();
        cJSON_AddStringToObject(item,"ssid",profiles.entries[i].ssid);
        cJSON_AddBoolToObject(item,"enabled",profiles.entries[i].proxy.enabled);
        cJSON_AddStringToObject(item,"host",profiles.entries[i].proxy.host);
        cJSON_AddNumberToObject(item,"port",profiles.entries[i].proxy.port);
        cJSON_AddItemToArray(list,item);
    }
    sw_proxy_config_t proxy; sw_proxy_get_for(wifi_ssid,&proxy);
    cJSON_AddBoolToObject(body, "proxy_enabled", proxy.enabled);
    cJSON_AddStringToObject(body, "proxy_host", proxy.host);
    cJSON_AddNumberToObject(body, "proxy_port", proxy.port ? proxy.port : 7897);
    char *text = cJSON_PrintUnformatted(body); cJSON_Delete(body);
    memset(&config, 0, sizeof(config));
    esp_err_t err = reply(r, text ? "200 OK" : "503 Service Unavailable", text ? text : "{}");
    free(text); return err;
}

static bool field(cJSON *root, const char *key, char *out, size_t cap)
{
    cJSON *v = cJSON_GetObjectItemCaseSensitive(root, key);
    if (!v) return true; /* omitted or blank secrets preserve previous values */
    if (!cJSON_IsString(v) || strlen(v->valuestring) >= cap) return false;
    if (*v->valuestring) strcpy(out, v->valuestring);
    return true;
}

static bool proxy_fields(cJSON *root, sw_proxy_config_t *out)
{
    cJSON *enabled = cJSON_GetObjectItemCaseSensitive(root, "proxy_enabled");
    if (enabled) { if (!cJSON_IsBool(enabled)) return false; out->enabled = cJSON_IsTrue(enabled); }
    cJSON *host = cJSON_GetObjectItemCaseSensitive(root, "proxy_host");
    if (host) {
        if (!cJSON_IsString(host) || strlen(host->valuestring) >= sizeof(out->host)) return false;
        strcpy(out->host, host->valuestring);   /* empty + disabled deletes the profile */
    }
    cJSON *port = cJSON_GetObjectItemCaseSensitive(root, "proxy_port");
    if (port) {
        if (!cJSON_IsString(port) || !port->valuestring[0]) return false;
        char *end; unsigned long n = strtoul(port->valuestring, &end, 10);
        if (*end || n < 1 || n > 65535) return false;
        out->port = n;
    }
    return !out->enabled || (sw_proxy_lan_ipv4(out->host) && out->port);
}

static bool sdk_valid(const char *s)
{
    if (!*s) return true;
    if (strlen(s) != 48 || strncmp(s, "mgst_", 5)) return false;
    for (unsigned i = 5; i < 48; ++i)
        if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= 'a' && s[i] <= 'z') ||
              (s[i] >= '0' && s[i] <= '9') || s[i] == '_' || s[i] == '-')) return false;
    return strchr("AEIMQUYcgkosw048", s[47]) != NULL;
}

static esp_err_t save(httpd_req_t *r)
{
    char token[40];
    if (!allowed(r) || httpd_req_get_hdr_value_str(r, "X-Setup-Token", token, sizeof(token)) != ESP_OK || strcmp(token, csrf))
        return reply(r, "403 Forbidden", "{}");
    if (r->content_len < 2 || r->content_len > 4096)
        return reply(r, "413 Content Too Large", "{}");
    char *buf = calloc(1, r->content_len + 1);
    if (!buf) return reply(r, "503 Service Unavailable", "{}");
    size_t got = 0;
    while (got < r->content_len) {
        int n = httpd_req_recv(r, buf + got, r->content_len - got);
        if (n <= 0) { free(buf); return ESP_FAIL; }
        got += n;
    }
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(buf, got + 1, &end, true);
    update_t update = {0};
    sw_config_get(&update.tts);
    char current_ssid[33], current_pass[65];
    muse_settings_wifi(current_ssid,current_pass); memset(current_pass,0,sizeof(current_pass));
    wifi_ap_record_t active_ap;
    if(esp_wifi_sta_get_ap_info(&active_ap)==ESP_OK){memcpy(current_ssid,active_ap.ssid,32);current_ssid[32]=0;}
    bool ssid_ok = cJSON_IsObject(root) && field(root,"ssid",update.ssid,sizeof(update.ssid));
    if (!update.ssid[0]) strcpy(update.ssid,current_ssid);
    sw_proxy_get_for(update.ssid,&update.proxy);
    bool ok = ssid_ok && update.ssid[0] && proxy_fields(root, &update.proxy) &&
        field(root, "password", update.pass, sizeof(update.pass)) &&
        field(root, "sdk_token", update.sdk, sizeof(update.sdk)) &&
        field(root, "api_key", update.tts.api_key, sizeof(update.tts.api_key)) &&
        field(root, "app_id", update.tts.app_id, sizeof(update.tts.app_id)) &&
        field(root, "access_key", update.tts.access_key, sizeof(update.tts.access_key)) &&
        field(root, "speaker", update.tts.speaker, sizeof(update.tts.speaker)) && sdk_valid(update.sdk) &&
        sw_header_safe(update.tts.api_key, 256) && sw_header_safe(update.tts.access_key, 256) &&
        sw_header_safe(update.tts.app_id, 64) && sw_header_safe(update.tts.speaker, 128) &&
        (!update.pass[0] || (strlen(update.pass) >= 8 && strlen(update.pass) <= 63));
    if (ok) {
        bool known = !strcmp(update.ssid,current_ssid);
        muse_wifi_saved_t saved[MUSE_WIFI_SAVED_MAX];
        int count = muse_wifi_saved(saved,MUSE_WIFI_SAVED_MAX);
        for (int i=0;i<count;++i) if (!strcmp(saved[i].ssid,update.ssid)) known=true;
        update.wifi_update = update.pass[0] || !known;
        sw_proxy_profiles_t candidate; sw_proxy_snapshot(&candidate);
        ok = sw_proxy_profile_set(&candidate,update.ssid,&update.proxy);
    }
    cJSON_Delete(root);
    memset(buf, 0, got); free(buf);
    esp_err_t result;
    if (!ok) result = reply(r, "400 Bad Request", "{\"error\":\"Check field lengths, SDK token and Wi-Fi password\"}");
    else if (xQueueSend(updates, &update, 0) != pdTRUE)
        result = reply(r, "409 Conflict", "{\"error\":\"Configuration is being applied\"}");
    else result = reply(r, "202 Accepted", "{\"ok\":true,\"message\":\"Applying settings. Hotspot closes; SDK token changes restart the device.\"}");
    memset(&update, 0, sizeof(update));
    return result;
}

static esp_err_t voice_request(httpd_req_t *r)
{
    char token[40];
    if (!allowed(r) || httpd_req_get_hdr_value_str(r, "X-Setup-Token", token, sizeof(token)) != ESP_OK || strcmp(token, csrf))
        return reply(r, "403 Forbidden", "{}");
    if (r->method == HTTP_GET) return sw_voice_result(r);
    if (r->content_len < 2 || r->content_len > 2048) return reply(r, "413 Content Too Large", "{}");
    char *buf = calloc(1, r->content_len + 1);
    if (!buf) return reply(r, "503 Service Unavailable", "{}");
    size_t got = 0;
    while (got < r->content_len) {
        int n = httpd_req_recv(r, buf + got, r->content_len - got);
        if (n <= 0) { memset(buf, 0, r->content_len); free(buf); return ESP_FAIL; }
        got += n;
    }
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(buf, got + 1, &end, true);
    esp_err_t err = sw_voice_submit(r, root, !strcmp(r->uri, "/preview"));
    cJSON_Delete(root); memset(buf, 0, got); free(buf);
    return err;
}

static void close_portal(void)
{
    if (server) { httpd_stop(server); server = NULL; }
    esp_wifi_set_mode(WIFI_MODE_STA);
    xSemaphoreTake(info_lock, portMAX_DELAY);
    active = false;
    xSemaphoreGive(info_lock);
    ESP_LOGI(TAG, "Setup hotspot closed");
}

static esp_err_t ensure_password(void)
{
    if (ap_pass[0]) return ESP_OK;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("sw_setup", NVS_READWRITE, &nvs);
    if (err != ESP_OK) return err;
    char saved[17] = {0}, pin[9]; size_t size = sizeof(saved);
    esp_err_t got = nvs_get_str(nvs, "pin", saved, &size);
    if (got != ESP_OK && got != ESP_ERR_NVS_NOT_FOUND && got != ESP_ERR_NVS_INVALID_LENGTH) {
        nvs_close(nvs); return got;
    }
    if (sw_setup_pin(pin, got == ESP_OK ? saved : NULL, esp_random())) {
        err = nvs_set_str(nvs, "pin", pin);
        if (err == ESP_OK) err = nvs_commit(nvs);
    }
    if (err == ESP_OK) {
        xSemaphoreTake(info_lock, portMAX_DELAY);
        memcpy(ap_pass, pin, sizeof(ap_pass));
        xSemaphoreGive(info_lock);
    }
    memset(saved, 0, sizeof(saved)); memset(pin, 0, sizeof(pin));
    nvs_close(nvs); return err;
}

static bool open_portal(void)
{
    if (server) return true;
    esp_err_t saved = ensure_password();
    if (saved != ESP_OK) {
        ESP_LOGE(TAG, "Cannot save setup PIN: %s", esp_err_to_name(saved));
        return false;
    }
    wifi_mode_t mode;
    if (esp_wifi_get_mode(&mode) != ESP_OK) return false;
    if (!ap_netif) ap_netif = esp_netif_create_default_wifi_ap();
    if (!ap_netif) return false;
    uint8_t mac[6];
    if (esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP) != ESP_OK) return false;
    uint32_t random[4]; esp_fill_random(random, sizeof(random));
    wifi_config_t cfg = {0};
    xSemaphoreTake(info_lock, portMAX_DELAY);
    snprintf(ap_name, sizeof(ap_name), "Muse-Setup-%02X%02X%02X", mac[3], mac[4], mac[5]);
    snprintf(csrf, sizeof(csrf), "%08lx%08lx%08lx%08lx", (unsigned long)random[0], (unsigned long)random[1],
             (unsigned long)random[2], (unsigned long)random[3]);
    strcpy((char *)cfg.ap.ssid, ap_name); strcpy((char *)cfg.ap.password, ap_pass);
    xSemaphoreGive(info_lock);
    cfg.ap.ssid_len = strlen((char *)cfg.ap.ssid);
    cfg.ap.channel = 1; cfg.ap.max_connection = 1; cfg.ap.authmode = WIFI_AUTH_WPA2_PSK;
    if (esp_wifi_set_mode(WIFI_MODE_APSTA) != ESP_OK || esp_wifi_set_config(WIFI_IF_AP, &cfg) != ESP_OK) {
        esp_wifi_set_mode(WIFI_MODE_STA); return false;
    }
    httpd_config_t hc = HTTPD_DEFAULT_CONFIG();
    hc.max_uri_handlers = 12;
    hc.max_open_sockets = 3; hc.lru_purge_enable = true;
    hc.stack_size = 8192; hc.recv_wait_timeout = 3; hc.send_wait_timeout = 3;
    if (httpd_start(&server, &hc) != ESP_OK) { esp_wifi_set_mode(WIFI_MODE_STA); return false; }
    const httpd_uri_t routes[] = {
        { .uri = "/", .method = HTTP_GET, .handler = page },
        { .uri = "/session", .method = HTTP_GET, .handler = session },
        { .uri = "/config", .method = HTTP_POST, .handler = save },
        { .uri = "/notice-policy", .method = HTTP_POST, .handler = notice_control },
        { .uri = "/notice-read", .method = HTTP_POST, .handler = notice_control },
        { .uri = "/handsfree", .method = HTTP_POST, .handler = handsfree_control },
        { .uri = "/voices", .method = HTTP_POST, .handler = voice_request },
        { .uri = "/preview", .method = HTTP_POST, .handler = voice_request },
        { .uri = "/voice-result", .method = HTTP_GET, .handler = voice_request },
    };
    for (unsigned i = 0; i < sizeof(routes) / sizeof(routes[0]); ++i) if (httpd_register_uri_handler(server, &routes[i]) != ESP_OK) {
        close_portal(); return false;
    }
    xSemaphoreTake(info_lock, portMAX_DELAY); active = true; xSemaphoreGive(info_lock);
    ESP_LOGI(TAG, "Setup ready at http://192.168.4.1 (idle timeout 5 min)");
    return true;
}

static void worker(void *arg)
{
    (void)arg;
    int64_t expires = 0;
    bool first = true;
    for (;;) {
        sw_proxy_tick();
        sw_pairing_tick(atomic_exchange(&pairing_requested, false));
        wifi_mode_t mode;
        if (esp_wifi_get_mode(&mode) != ESP_OK) { vTaskDelay(pdMS_TO_TICKS(500)); continue; }
        if (first) {
            char ssid[33], pass[65]; muse_settings_wifi(ssid, pass);
            if (!ssid[0] || !muse_link_sdk_token()) sw_portal_request();
            memset(pass, 0, sizeof(pass)); first = false;
        }
        if (atomic_exchange(&requested, false)) {
            if (open_portal()) expires = esp_timer_get_time() + 5LL * 60 * 1000000;
            else sw_tts_set_status("Setup hotspot failed");
        }
        if (atomic_exchange(&close_requested, false) && server) close_portal();
        update_t u;
        if (xQueueReceive(updates, &u, pdMS_TO_TICKS(200)) == pdTRUE) {
            vTaskDelay(pdMS_TO_TICKS(500)); /* let the HTTP response leave */
            sw_proxy_config_t old_proxy; sw_proxy_get_for(u.ssid,&old_proxy);
            wifi_ap_record_t active_ap; char active_ssid[33]={0};
            if(esp_wifi_sta_get_ap_info(&active_ap)==ESP_OK){memcpy(active_ssid,active_ap.ssid,32);active_ssid[32]=0;}
            bool restart = sw_proxy_restart_needed(&old_proxy,&u.proxy,!strcmp(active_ssid,u.ssid),u.wifi_update);
            esp_err_t err = sw_config_save(&u.tts);
            if (err == ESP_OK) err = sw_proxy_save_for(u.ssid,&u.proxy);
            if (err == ESP_OK) {
                if (u.wifi_update) muse_settings_set_wifi(u.ssid,u.pass);
                close_portal();
                bool token_saved = true;
                if (u.sdk[0]) {
                    if (muse_link_sdk_token_set(u.sdk)) restart = true;
                    else {
                        token_saved = false;
                        sw_tts_set_status("SDK token save failed");
                    }
                }
                if (restart) esp_restart();
                else if (token_saved) {
                    sw_config_t current; sw_config_get(&current);
                    sw_tts_set_status(sw_config_ready(&current) ? "Ready (not tested)" : "Not configured");
                    memset(&current, 0, sizeof(current));
                }
            } else sw_tts_set_status("Configuration save failed");
            memset(&u, 0, sizeof(u));
        }
        if (server) {
            muse_state_poke();
            wifi_sta_list_t clients = {0};
            if (esp_wifi_ap_get_sta_list(&clients) == ESP_OK && clients.num)
                expires = esp_timer_get_time() + 5LL * 60 * 1000000;
        }
        if (server && esp_timer_get_time() >= expires) close_portal();
    }
}

esp_err_t sw_portal_init(void)
{
    info_lock = xSemaphoreCreateMutex();
    updates = xQueueCreate(1, sizeof(update_t));
    if (!info_lock || !updates) return ESP_ERR_NO_MEM;
    esp_err_t voice = sw_voice_init();
    if (voice != ESP_OK) return voice;
    return xTaskCreate(worker, "muse_setup", 6144, NULL, 3, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
