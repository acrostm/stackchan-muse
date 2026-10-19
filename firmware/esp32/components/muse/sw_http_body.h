// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *context;
    int (*read)(void *context, void *data, size_t capacity);
    bool (*complete)(void *context);
    int64_t (*now_us)(void *context);
    int64_t deadline_us;
} sw_http_body_t;

/*
 * Drain the response body before consulting the transport's completion flag.
 * ESP-IDF can cache a small body while fetch_headers() has already made the
 * client report complete, so completion alone does not prove the body is empty.
 */
bool sw_http_body_collect(sw_http_body_t *body, unsigned char *out,
                          size_t capacity, size_t *size);
