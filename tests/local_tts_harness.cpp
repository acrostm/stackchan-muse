// Exercise the actual firmware worker against a deterministic HTTP transport.
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <fstream>
#include <iterator>
#include <mutex>
#include <thread>
#include <vector>
#include "muse_local_tts.h"
#include "esp_http_client.h"
#include "freertos/queue.h"
#include "freertos/FreeRTOS.h"

struct fake_queue { std::mutex mutex; std::condition_variable wake; void *item = nullptr; };
QueueHandle_t xQueueCreate(size_t count, size_t size) {
 assert(count == 1 && size == sizeof(void *)); return new fake_queue;
}
int xQueueReceive(QueueHandle_t queue, void *out, uint32_t) {
 std::unique_lock<std::mutex> lock(queue->mutex);
 queue->wake.wait(lock, [&] { return queue->item; });
 memcpy(out, &queue->item, sizeof(void *)); queue->item = nullptr; return pdTRUE;
}
int xQueueSend(QueueHandle_t queue, const void *item, uint32_t) {
 std::lock_guard<std::mutex> lock(queue->mutex);
 if (queue->item) return 0;
 memcpy(&queue->item, item, sizeof(void *)); queue->wake.notify_one(); return pdTRUE;
}
void vQueueDelete(QueueHandle_t queue) { delete queue; }
int xTaskCreatePinnedToCoreWithCaps(void (*worker)(void *), const char *, size_t, void *arg, int, void *, int, int) {
 std::thread(worker, arg).detach(); return pdPASS;
}
static std::atomic<int64_t> clock_us{0};
int64_t esp_timer_get_time(void) { return clock_us.fetch_add(1000); }
static std::atomic<int> scenario{0}, entered{0}, closed{0};
static std::atomic<bool> interrupted{false};
int muse_fake_shutdown(int socket, int) { assert(socket == 7); interrupted = true; return 0; }
int esp_http_client_get_socket(esp_http_client_handle_t) { return 7; }
static std::vector<char> mp3;
struct fake_client { esp_http_client_config_t config; size_t offset = 0; int kind; };
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *config) {
 assert(config->disable_auto_redirect && config->timeout_ms <= 2000);
 assert(!strcmp(config->url, "http://private-bridge.test/tts"));
 interrupted = false;
 return new fake_client{*config, 0, scenario.load()};
}
int esp_http_client_set_header(esp_http_client_handle_t, const char *key, const char *value) {
 if (!strcmp(key, "X-Tts-Auth")) assert(!strcmp(value, "synthetic-bridge-test-credential"));
 return ESP_OK;
}
int esp_http_client_open(esp_http_client_handle_t, int) { return ESP_OK; }
int esp_http_client_write(esp_http_client_handle_t, const char *, int n) { return n > 7 ? 7 : n; }
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t client) {
 entered.store(1);
 if (client->kind == 1 || client->kind == 7) {
  if (client->kind == 7) clock_us.fetch_add(2000000);
  std::this_thread::sleep_for(std::chrono::milliseconds(2)); return -ESP_ERR_HTTP_EAGAIN;
 }
 esp_http_client_event_t event{HTTP_EVENT_ON_HEADER, "Content-Type",
   client->kind == 3 ? "application/json" : "audio/mpeg", client->config.user_data, client};
 client->config.event_handler(&event);
 return client->kind == 4 ? 512 * 1024 + 1 : static_cast<int64_t>(mp3.size());
}
int esp_http_client_get_status_code(esp_http_client_handle_t client) { return client->kind == 2 ? 429 : 200; }
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t client) {
 // Model cached data: IDF may already report complete immediately after headers.
 return client->kind != 5;
}
int esp_http_client_read(esp_http_client_handle_t client, char *out, int n) {
 if (client->kind == 9 || client->kind == 10) {
  entered = 1;
  while (!interrupted) {
   if (client->kind == 9) clock_us.fetch_add(2000000);
   esp_http_client_event_t event{HTTP_EVENT_ON_DATA, nullptr, nullptr, client->config.user_data, client};
   // Deliberately ignore callback return, exactly like IDF's HTTP parser.
   client->config.event_handler(&event);
   std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  return -1;
 }

 if (client->kind == 6) { const char *bad = "{not_mp3}"; size_t len = strlen(bad);
  if (client->offset) return 0; memcpy(out, bad, len); client->offset = len; return len; }
 if (client->kind == 8) {
  if (client->offset > 512 * 1024) return 0;
  memset(out, 'X', n); client->offset += n; return n;
 }
 size_t left = mp3.size() - client->offset;
 if (!left) return 0;
 size_t take = left < static_cast<size_t>(n) ? left : static_cast<size_t>(n);
 memcpy(out, mp3.data() + client->offset, take); client->offset += take; return take;
}
int esp_http_client_cleanup(esp_http_client_handle_t client) { delete client; ++closed; return ESP_OK; }
static muse_local_tts_result wait_result(std::vector<uint8_t> &out, size_t &length) {
 for (int i = 0; i < 2000; ++i) {
  auto result = muse_local_tts_take(out.data(), out.size(), &length);
  if (result != MUSE_LOCAL_PENDING) return result;
  std::this_thread::sleep_for(std::chrono::milliseconds(1));
 }
 assert(false && "worker did not finish"); return MUSE_LOCAL_FAILED;
}
int main(int argc, char **argv) {
 assert(argc == 2);
 std::ifstream file(argv[1], std::ios::binary);
 mp3.assign(std::istreambuf_iterator<char>(file), {}); assert(!mp3.empty());
 std::vector<uint8_t> out(512 * 1024, 0x5a); size_t length = 123;
 assert(muse_local_tts_configured());
 assert(muse_local_tts_begin("中文语音测试"));
 assert(wait_result(out, length) == MUSE_LOCAL_READY);
 assert(length == mp3.size() && !memcmp(out.data(), mp3.data(), length));
 // Cancel while HTTP is stalled, invalidate even a late result, then recover.
 scenario = 1; entered = 0;
 auto started = std::chrono::steady_clock::now();
 assert(muse_local_tts_begin("取消这一轮"));
 assert(std::chrono::steady_clock::now() - started < std::chrono::milliseconds(100));
 while (!entered) std::this_thread::sleep_for(std::chrono::milliseconds(1));
 muse_local_tts_cancel();
 assert(wait_result(out, length) == MUSE_LOCAL_FAILED && !length);
 for (int kind : {2, 3, 4, 5, 6, 7, 8, 9}) {
  scenario = kind; clock_us = 0; std::fill(out.begin(), out.end(), 0x5a);
  assert(muse_local_tts_begin("失败必须保留字幕"));
  assert(wait_result(out, length) == MUSE_LOCAL_FAILED && !length);
  assert(out.front() == 0x5a && out.back() == 0x5a);
 }
 scenario = 10; clock_us = 0; entered = 0;
 assert(muse_local_tts_begin("持续滴流时也要取消"));
 while (!entered) std::this_thread::sleep_for(std::chrono::milliseconds(1));
 muse_local_tts_cancel();
 assert(wait_result(out, length) == MUSE_LOCAL_FAILED && !length);
 scenario = 0; clock_us = 0;
 assert(muse_local_tts_begin("新一轮只播放新的音频"));
 assert(wait_result(out, length) == MUSE_LOCAL_READY && length == mp3.size());
 // Result completed before cancel must also be discarded, never handed off.
 assert(muse_local_tts_begin("完成后取消"));
 std::this_thread::sleep_for(std::chrono::milliseconds(30));
 muse_local_tts_cancel();
 assert(wait_result(out, length) == MUSE_LOCAL_FAILED && !length);
 assert(closed == 13);
}
