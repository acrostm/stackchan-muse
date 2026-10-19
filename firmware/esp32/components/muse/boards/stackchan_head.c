/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * StackChan's optional M5IOE1 base and two Feetech SCSCL servos. The servo
 * protocol and per-unit NVS keys follow M5Stack's StackChan-BSP. Motion is
 * owned by one task: requests carry a priority, the spring reaches a bounded
 * target at a bounded speed, and torque is released after the head settles.
 */
#include "driver/i2c_master.h"
#include "driver/uart.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"
#include "sdkconfig.h"

#include <stdio.h>
#include <string.h>

#include "muse_state.h"
#include "stackchan_head.h"
#include "stackchan_motion_core.h"

static const char *TAG = "stackchan_head";

#define IOE_ADDR 0x6F
#define IOE_VERSION 0x02
#define IOE_GPIO_M_L 0x03
#define IOE_GPIO_O_L 0x05
#define IOE_GPIO_PU_L 0x09
#define IOE_SERVO_POWER BIT(0)
#define IOE_GPIO_M_H 0x04
#define IOE_GPIO_PU_H 0x0A
#define IOE_GPIO_PD_H 0x0C
#define IOE_GPIO_DRV_H 0x14
#define IOE_LED_CFG 0x24
#define IOE_LED_RAM 0x30
#define IOE_LED_DATA_BIT 5
#define BASE_LED_COUNT 12

#define SERVO_UART UART_NUM_1
#define SERVO_TX GPIO_NUM_6
#define SERVO_RX GPIO_NUM_7
#define SERVO_YAW_ID 1
#define SERVO_PITCH_ID 2
#define SERVO_YAW_DEFAULT_ZERO 460
#define SERVO_PITCH_DEFAULT_ZERO 620
#define SERVO_REG_TORQUE 40
#define SERVO_REG_GOAL_POS 42
#define SERVO_REG_PRESENT_POS 56
#define SERVO_RAW_MIN 0
#define SERVO_RAW_MAX 1000
#define MUSE_CAL_KEY "muse_cal"
#define SCS_INST_READ 0x02
#define SCS_INST_WRITE 0x03
#define MOTION_PERIOD_MS 20
#define TORQUE_REST_MS 250

static i2c_master_dev_handle_t s_ioe;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_motion_task;
static stackchan_motion_t s_motion;
static int s_yaw_zero = SERVO_YAW_DEFAULT_ZERO;
static int s_pitch_zero = SERVO_PITCH_DEFAULT_ZERO;
static int s_last_yaw = -100000;
static int s_last_pitch = -100000;
static int64_t s_rest_since_us;
static bool s_present;
static bool s_uart_ready;
static bool s_calibrated;
static bool s_torque_on;
static uint32_t s_generation = 1;

static esp_err_t ioe_read(uint8_t reg, uint8_t *val)
{
    return i2c_master_transmit_receive(s_ioe, &reg, 1, val, 1, 100);
}

static esp_err_t ioe_write(uint8_t reg, uint8_t val)
{
    const uint8_t buf[2] = { reg, val };
    return i2c_master_transmit(s_ioe, buf, sizeof(buf), 100);
}

static esp_err_t ioe_update(uint8_t reg, uint8_t mask, bool on)
{
    uint8_t value;
    ESP_RETURN_ON_ERROR(ioe_read(reg, &value), TAG, "ioe read %02x", reg);
    const uint8_t wanted = on ? value | mask : value & ~mask;
    return wanted == value ? ESP_OK : ioe_write(reg, wanted);
}

#if CONFIG_MUSE_STACKCHAN_PENDING_LED
static esp_err_t base_leds_show(uint8_t r, uint8_t g, uint8_t b)
{
    const uint16_t color = ((uint16_t)(r & 0xF8) << 8) |
                           ((uint16_t)(g & 0xFC) << 3) | (uint16_t)(b >> 3);
    uint8_t buf[1 + BASE_LED_COUNT * 2];
    buf[0] = IOE_LED_RAM;
    for (int i = 0; i < BASE_LED_COUNT; ++i) {
        buf[1 + i * 2] = (uint8_t)(color & 0xFF);
        buf[2 + i * 2] = (uint8_t)(color >> 8);
    }
    ESP_RETURN_ON_ERROR(i2c_master_transmit(s_ioe, buf, sizeof(buf), 100),
                        TAG, "led frame");
    uint8_t cfg;
    ESP_RETURN_ON_ERROR(ioe_read(IOE_LED_CFG, &cfg), TAG, "led cfg read");
    return ioe_write(IOE_LED_CFG, cfg | BIT(6));
}

static esp_err_t base_leds_init(void)
{
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_M_H, BIT(IOE_LED_DATA_BIT), true),
                        TAG, "led pin output");
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_PU_H, BIT(IOE_LED_DATA_BIT), true),
                        TAG, "led pin pull-up");
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_PD_H, BIT(IOE_LED_DATA_BIT), false),
                        TAG, "led pin pull-down");
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_DRV_H, BIT(IOE_LED_DATA_BIT), false),
                        TAG, "led pin push-pull");
    ESP_RETURN_ON_ERROR(ioe_write(IOE_LED_CFG, BASE_LED_COUNT), TAG, "led count");
    return base_leds_show(0, 0, 0);
}

static void pending_led_task(void *arg)
{
    (void)arg;
    bool was_pending = false, lit = false;
    int64_t phase_ms = 0;
    for (;;) {
        const bool pending = muse_state_reply_pending();
        const int64_t now_ms = esp_timer_get_time() / 1000;
        if (pending && !was_pending) {
            was_pending = true;
            phase_ms = now_ms - 600;
        }
        if (!pending && was_pending) {
            base_leds_show(0, 0, 0);
            was_pending = false;
            lit = false;
        }
        if (pending && now_ms - phase_ms >= 500) {
            phase_ms = now_ms;
            lit = !lit;
            base_leds_show(lit ? 255 : 0, lit ? 140 : 0, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
#endif

static esp_err_t scs_write(uint8_t id, uint8_t addr, const uint8_t *data, size_t n)
{
    if (!s_uart_ready) return ESP_ERR_INVALID_STATE;
    uint8_t packet[16];
    const size_t length = n + 3;
    if (length + 3 > sizeof(packet)) return ESP_ERR_INVALID_SIZE;
    packet[0] = 0xFF;
    packet[1] = 0xFF;
    packet[2] = id;
    packet[3] = (uint8_t)length;
    packet[4] = SCS_INST_WRITE;
    packet[5] = addr;
    unsigned sum = id + length + SCS_INST_WRITE + addr;
    for (size_t i = 0; i < n; ++i) {
        packet[6 + i] = data[i];
        sum += data[i];
    }
    packet[6 + n] = (uint8_t)~sum;
    if (uart_write_bytes(SERVO_UART, packet, (int)(n + 7)) < 0)
        return ESP_FAIL;
    return uart_wait_tx_done(SERVO_UART, pdMS_TO_TICKS(50));
}

static esp_err_t scs_read_word(uint8_t id, uint8_t addr, int *out)
{
    if (!s_uart_ready || !out) return ESP_ERR_INVALID_STATE;
    uart_flush_input(SERVO_UART);
    uint8_t request[8] = { 0xFF, 0xFF, id, 4, SCS_INST_READ, addr, 2, 0 };
    unsigned sum = id + request[3] + SCS_INST_READ + addr + 2;
    request[7] = (uint8_t)~sum;
    if (uart_write_bytes(SERVO_UART, request, sizeof(request)) < 0)
        return ESP_FAIL;
    if (uart_wait_tx_done(SERVO_UART, pdMS_TO_TICKS(50)) != ESP_OK)
        return ESP_ERR_TIMEOUT;

    uint8_t reply[8];
    if (uart_read_bytes(SERVO_UART, reply, sizeof(reply), pdMS_TO_TICKS(50)) !=
        (int)sizeof(reply))
        return ESP_ERR_TIMEOUT;
    if (reply[0] != 0xFF || reply[1] != 0xFF || reply[2] != id ||
        reply[3] != 4 || reply[4] != 0)
        return ESP_ERR_INVALID_RESPONSE;
    unsigned reply_sum = reply[2] + reply[3] + reply[4] + reply[5] + reply[6];
    if ((uint8_t)~reply_sum != reply[7]) return ESP_ERR_INVALID_CRC;
    const int raw = (reply[5] << 8) | reply[6];
    if (raw < SERVO_RAW_MIN || raw > SERVO_RAW_MAX) return ESP_ERR_INVALID_RESPONSE;
    *out = raw;
    return ESP_OK;
}

static esp_err_t servo_write_raw(uint8_t id, int raw)
{
    raw = raw < SERVO_RAW_MIN ? SERVO_RAW_MIN : raw > SERVO_RAW_MAX ? SERVO_RAW_MAX : raw;
    const uint8_t data[6] = {
        (uint8_t)(raw >> 8), (uint8_t)raw,
        0, 20,
        0, 0,
    };
    return scs_write(id, SERVO_REG_GOAL_POS, data, sizeof(data));
}

static esp_err_t servo_torque(uint8_t id, bool on)
{
    const uint8_t data[1] = { on ? 1 : 0 };
    return scs_write(id, SERVO_REG_TORQUE, data, sizeof(data));
}

static int valid_raw(int raw)
{
    return raw >= SERVO_RAW_MIN && raw <= SERVO_RAW_MAX ? raw : -1;
}

static int angle_to_raw(int tenths, int zero, int min_tenths, int max_tenths)
{
    tenths = tenths < min_tenths ? min_tenths
             : tenths > max_tenths ? max_tenths : tenths;
    const int raw = zero + tenths * 16 / 50;
    return raw < SERVO_RAW_MIN ? SERVO_RAW_MIN : raw > SERVO_RAW_MAX ? SERVO_RAW_MAX : raw;
}

static int raw_to_angle(int raw, int zero)
{
    return (raw - zero) * 50 / 16;
}

static bool read_position(uint8_t id, int *raw)
{
    return scs_read_word(id, SERVO_REG_PRESENT_POS, raw) == ESP_OK;
}

static bool load_calibration(void)
{
    nvs_handle_t nvs;
    if (nvs_open("servo", NVS_READONLY, &nvs) != ESP_OK) {
        ESP_LOGW(TAG, "no per-unit servo calibration; centre the head and run head.calibrate");
        return false;
    }
    int32_t yaw = -1, pitch = -1;
    uint8_t muse_confirmed = 0;
    const bool valid = nvs_get_u8(nvs, MUSE_CAL_KEY, &muse_confirmed) == ESP_OK &&
                       muse_confirmed == 1 &&
                       nvs_get_i32(nvs, "zero_pos_1", &yaw) == ESP_OK &&
                       nvs_get_i32(nvs, "zero_pos_2", &pitch) == ESP_OK &&
                       valid_raw(yaw) >= 0 && valid_raw(pitch) >= 0;
    nvs_close(nvs);
    if (!valid) {
        ESP_LOGW(TAG, "servo calibration is missing or invalid");
        return false;
    }
    s_yaw_zero = yaw;
    s_pitch_zero = pitch;
    ESP_LOGI(TAG, "servo calibration: yaw=%d pitch=%d", s_yaw_zero, s_pitch_zero);
    return true;
}

static esp_err_t save_calibration(int yaw, int pitch)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("servo", NVS_READWRITE, &nvs);
    if (err != ESP_OK) return err;
    err = nvs_set_i32(nvs, "zero_pos_1", yaw);
    if (err == ESP_OK) err = nvs_set_i32(nvs, "zero_pos_2", pitch);
    if (err == ESP_OK) err = nvs_set_u8(nvs, MUSE_CAL_KEY, 1);
    if (err == ESP_OK) err = nvs_commit(nvs);
    nvs_close(nvs);
    return err;
}

static void motion_task(void *arg)
{
    (void)arg;
    int64_t previous_us = esp_timer_get_time();
    for (;;) {
        const int64_t now_us = esp_timer_get_time();
        float dt_s = (float)(now_us - previous_us) / 1000000.0f;
        previous_us = now_us;
        if (dt_s < 0.001f) dt_s = 0.001f;
        if (dt_s > 0.05f) dt_s = 0.05f;

        xSemaphoreTake(s_lock, portMAX_DELAY);
        int yaw_tenths = 0, pitch_tenths = 0;
        const bool moving = stackchan_motion_tick(&s_motion, now_us, dt_s,
                                                  &yaw_tenths, &pitch_tenths);
        if (moving && !s_torque_on) {
            const esp_err_t yaw_err = servo_torque(SERVO_YAW_ID, true);
            const esp_err_t pitch_err = servo_torque(SERVO_PITCH_ID, true);
            if (yaw_err == ESP_OK && pitch_err == ESP_OK) {
                s_torque_on = true;
            } else {
                ESP_LOGW(TAG, "could not enable servo torque");
            }
        }
        if (yaw_tenths != s_last_yaw || pitch_tenths != s_last_pitch) {
            const esp_err_t yaw_err = servo_write_raw(SERVO_YAW_ID,
                angle_to_raw(yaw_tenths, s_yaw_zero, -STACKCHAN_YAW_LIMIT_TENTHS,
                             STACKCHAN_YAW_LIMIT_TENTHS));
            const esp_err_t pitch_err = servo_write_raw(SERVO_PITCH_ID,
                angle_to_raw(pitch_tenths, s_pitch_zero, 0,
                             STACKCHAN_PITCH_LIMIT_TENTHS));
            if (yaw_err == ESP_OK && pitch_err == ESP_OK) {
                s_last_yaw = yaw_tenths;
                s_last_pitch = pitch_tenths;
            }
        }
        if (moving) {
            s_rest_since_us = 0;
        } else if (s_rest_since_us == 0) {
            s_rest_since_us = now_us;
        } else if (s_torque_on &&
                   now_us - s_rest_since_us >= TORQUE_REST_MS * 1000LL) {
            servo_torque(SERVO_YAW_ID, false);
            servo_torque(SERVO_PITCH_ID, false);
            s_torque_on = false;
        }
        xSemaphoreGive(s_lock);
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(MOTION_PERIOD_MS));
    }
}

esp_err_t stackchan_head_init(i2c_master_bus_handle_t bus)
{
    if (!bus) return ESP_ERR_INVALID_ARG;
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return ESP_ERR_NO_MEM;
    const i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = IOE_ADDR,
        .scl_speed_hz = 100000,
    };
    ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(bus, &dev_cfg, &s_ioe),
                        TAG, "ioe");

    uint8_t version = 0;
    for (int waited = 0; waited < 1200; waited += 50) {
        if (ioe_read(IOE_VERSION, &version) == ESP_OK &&
            version != 0x00 && version != 0xFF)
            break;
        version = 0;
        vTaskDelay(pdMS_TO_TICKS(50));
    }
    if (!version) return ESP_ERR_NOT_FOUND;
    ESP_LOGI(TAG, "M5IOE1 expander, version %u", version);

    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_M_L, IOE_SERVO_POWER, true),
                        TAG, "servo pin output");
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_PU_L, IOE_SERVO_POWER, true),
                        TAG, "servo pin pull-up");
    ESP_RETURN_ON_ERROR(ioe_update(IOE_GPIO_O_L, IOE_SERVO_POWER, true),
                        TAG, "servo power on");

#if CONFIG_MUSE_STACKCHAN_PENDING_LED
    if (base_leds_init() == ESP_OK)
        xTaskCreate(pending_led_task, "stackchan_led", 3072, NULL, 2, NULL);
    else
        ESP_LOGW(TAG, "base LEDs unavailable");
#endif

    const uart_config_t uart_cfg = {
        .baud_rate = 1000000,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_RETURN_ON_ERROR(uart_param_config(SERVO_UART, &uart_cfg),
                        TAG, "servo uart cfg");
    ESP_RETURN_ON_ERROR(uart_set_pin(SERVO_UART, SERVO_TX, SERVO_RX,
                                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE),
                        TAG, "servo uart pins");
    ESP_RETURN_ON_ERROR(uart_driver_install(SERVO_UART, 256, 0, 0, NULL, 0),
                        TAG, "servo uart");
    s_uart_ready = true;
    servo_torque(SERVO_YAW_ID, false);
    servo_torque(SERVO_PITCH_ID, false);

    s_calibrated = load_calibration();
    int yaw_raw = -1, pitch_raw = -1;
    if (!read_position(SERVO_YAW_ID, &yaw_raw) ||
        !read_position(SERVO_PITCH_ID, &pitch_raw)) {
        ESP_LOGW(TAG, "servo feedback unavailable; motion stays disabled");
        return ESP_ERR_NOT_FOUND;
    }
    int yaw = raw_to_angle(yaw_raw, s_yaw_zero);
    int pitch = raw_to_angle(pitch_raw, s_pitch_zero);
    yaw = yaw < -STACKCHAN_YAW_LIMIT_TENTHS ? -STACKCHAN_YAW_LIMIT_TENTHS
          : yaw > STACKCHAN_YAW_LIMIT_TENTHS ? STACKCHAN_YAW_LIMIT_TENTHS : yaw;
    pitch = pitch < 0 ? 0 : pitch > STACKCHAN_PITCH_LIMIT_TENTHS
                                  ? STACKCHAN_PITCH_LIMIT_TENTHS : pitch;
    stackchan_motion_init(&s_motion, yaw, pitch);
    s_last_yaw = yaw;
    s_last_pitch = pitch;
    if (xTaskCreate(motion_task, "stackchan_motion", 4096, NULL, 4, &s_motion_task) != pdPASS)
        return ESP_ERR_NO_MEM;
    s_present = true;
    ESP_LOGI(TAG, "servos ready%s (yaw raw %d, pitch raw %d)",
             s_calibrated ? "" : ", calibration required", yaw_raw, pitch_raw);
    return ESP_OK;
}

bool stackchan_head_present(void)
{
    return s_present;
}

bool stackchan_head_ready(void)
{
    return stackchan_head_ready_generation() != 0;
}

uint32_t stackchan_head_ready_generation(void)
{
    if (!s_lock) return 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const bool ready = s_present && s_calibrated && s_motion_task;
    const uint32_t generation = ready ? s_generation : 0;
    xSemaphoreGive(s_lock);
    return generation;
}

esp_err_t stackchan_head_move(int yaw_deg, int pitch_deg, int speed,
                              stackchan_move_priority_t priority,
                              int64_t expires_us)
{
    return stackchan_head_move_for_generation(yaw_deg, pitch_deg, speed, priority,
                                              expires_us, 0);
}

esp_err_t stackchan_head_move_for_generation(int yaw_deg, int pitch_deg, int speed,
                                             stackchan_move_priority_t priority,
                                             int64_t expires_us,
                                             uint32_t generation)
{
    if (!s_lock) return ESP_ERR_NOT_FOUND;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (!s_present) {
        xSemaphoreGive(s_lock);
        return ESP_ERR_NOT_FOUND;
    }
    if (!s_calibrated || !s_motion_task) {
        xSemaphoreGive(s_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (generation && generation != s_generation) {
        xSemaphoreGive(s_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (!generation && priority >= STACKCHAN_MOVE_COMMAND) {
        ++s_generation;
        if (!s_generation) ++s_generation;
    }
    yaw_deg = yaw_deg < -128 ? -128 : yaw_deg > 128 ? 128 : yaw_deg;
    pitch_deg = pitch_deg < 0 ? 0 : pitch_deg > 90 ? 90 : pitch_deg;
    const bool accepted = stackchan_motion_set_target(
        &s_motion, yaw_deg * 10, pitch_deg * 10, speed, priority,
        esp_timer_get_time(), expires_us);
    TaskHandle_t task = s_motion_task;
    xSemaphoreGive(s_lock);
    if (!accepted) return ESP_ERR_INVALID_STATE;
    xTaskNotifyGive(task);
    return ESP_OK;
}

esp_err_t stackchan_head_look(int yaw_deg, int pitch_deg)
{
    return stackchan_head_move(yaw_deg, pitch_deg, 500, STACKCHAN_MOVE_COMMAND, 0);
}

esp_err_t stackchan_head_center(void)
{
    return stackchan_head_look(0, 0);
}

static void stop_locked(void)
{
    stackchan_motion_cancel(&s_motion);
    const int yaw = (int)s_motion.yaw;
    const int pitch = (int)s_motion.pitch;
    servo_write_raw(SERVO_YAW_ID,
                    angle_to_raw(yaw, s_yaw_zero, -STACKCHAN_YAW_LIMIT_TENTHS,
                                 STACKCHAN_YAW_LIMIT_TENTHS));
    servo_write_raw(SERVO_PITCH_ID,
                    angle_to_raw(pitch, s_pitch_zero, 0,
                                 STACKCHAN_PITCH_LIMIT_TENTHS));
    servo_torque(SERVO_YAW_ID, false);
    servo_torque(SERVO_PITCH_ID, false);
    s_last_yaw = yaw;
    s_last_pitch = pitch;
    s_torque_on = false;
    s_rest_since_us = esp_timer_get_time();
}

uint32_t stackchan_head_stop_and_generation(void)
{
    if (!s_lock) return 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    stop_locked();
    ++s_generation;
    if (!s_generation) ++s_generation;
    const uint32_t generation =
        s_present && s_calibrated && s_motion_task ? s_generation : 0;
    xSemaphoreGive(s_lock);
    return generation;
}

void stackchan_head_stop(void)
{
    (void)stackchan_head_stop_and_generation();
}

esp_err_t stackchan_head_calibrate_current(void)
{
    if (!s_present) return ESP_ERR_NOT_FOUND;
    stackchan_head_stop();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    int yaw_raw = -1, pitch_raw = -1;
    esp_err_t err = read_position(SERVO_YAW_ID, &yaw_raw) ? ESP_OK : ESP_FAIL;
    if (err == ESP_OK && !read_position(SERVO_PITCH_ID, &pitch_raw))
        err = ESP_FAIL;
    if (err == ESP_OK) err = save_calibration(yaw_raw, pitch_raw);
    if (err == ESP_OK) {
        s_yaw_zero = yaw_raw;
        s_pitch_zero = pitch_raw;
        stackchan_motion_init(&s_motion, 0, 0);
        s_last_yaw = s_last_pitch = 0;
        s_calibrated = true;
        ESP_LOGI(TAG, "calibrated yaw=%d pitch=%d", yaw_raw, pitch_raw);
    }
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t stackchan_head_set_power(bool on)
{
    if (!s_present) return ESP_OK;
    if (!on) stackchan_head_stop();
    return ioe_update(IOE_GPIO_O_L, IOE_SERVO_POWER, on);
}

bool stackchan_head_console_command(const char *line)
{
    if (!line) return false;
    if (!strcmp(line, "head.calibrate")) {
        const esp_err_t err = stackchan_head_calibrate_current();
        printf("@head.calibrate %s\n", esp_err_to_name(err));
        return true;
    }
    if (!strcmp(line, "head.stop")) {
        stackchan_head_stop();
        printf("@head.stop ok\n");
        return true;
    }
    if (!strcmp(line, "head.status")) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        const int yaw = (int)s_motion.yaw, pitch = (int)s_motion.pitch;
        const bool moving = s_motion.active, torque = s_torque_on;
        const bool present = s_present, calibrated = s_calibrated;
        const int zero_yaw = s_yaw_zero, zero_pitch = s_pitch_zero;
        xSemaphoreGive(s_lock);
        printf("@head.status {\"present\":%s,\"calibrated\":%s,\"moving\":%s,"
               "\"torque\":%s,\"yaw_deg\":%.1f,\"pitch_deg\":%.1f,"
               "\"zero_yaw\":%d,\"zero_pitch\":%d}\n",
               present ? "true" : "false", calibrated ? "true" : "false",
               moving ? "true" : "false", torque ? "true" : "false",
               yaw / 10.0, pitch / 10.0, zero_yaw, zero_pitch);
        return true;
    }
    int yaw = 0, pitch = 0;
    char tail = 0;
    if (sscanf(line, "head.look=%d,%d%c", &yaw, &pitch, &tail) == 2) {
        const esp_err_t err = stackchan_head_look(yaw, pitch);
        printf("@head.look %s\n", esp_err_to_name(err));
        return true;
    }
    return false;
}
