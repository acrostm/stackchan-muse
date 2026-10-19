#pragma once
#include <stdint.h>
using esp_err_t = int;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_HTTP_EAGAIN 10
#define HTTP_METHOD_POST 1
#define HTTP_EVENT_ON_HEADER 1
#define HTTP_EVENT_ON_DATA 2
struct fake_client;
using esp_http_client_handle_t = fake_client *;
struct esp_http_client_event_t {
 int event_id;
 const char *header_key, *header_value;
 void *user_data;
 esp_http_client_handle_t client;
};
struct esp_http_client_config_t {
 const char *url = nullptr;
 int method = 0, timeout_ms = 0, buffer_size = 0;
 esp_err_t (*event_handler)(esp_http_client_event_t *) = nullptr;
 void *user_data = nullptr;
 bool disable_auto_redirect = false;
 int (*crt_bundle_attach)(void *) = nullptr;
};
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *);
int esp_http_client_set_header(esp_http_client_handle_t, const char *, const char *);
int esp_http_client_open(esp_http_client_handle_t, int);
int esp_http_client_write(esp_http_client_handle_t, const char *, int);
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t);
int esp_http_client_get_status_code(esp_http_client_handle_t);
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t);
int esp_http_client_read(esp_http_client_handle_t, char *, int);
int esp_http_client_cleanup(esp_http_client_handle_t);

int esp_http_client_get_socket(esp_http_client_handle_t);
