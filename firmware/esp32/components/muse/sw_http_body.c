// SPDX-License-Identifier: Apache-2.0
#include "sw_http_body.h"

#include <limits.h>

bool sw_http_body_collect(sw_http_body_t *body, unsigned char *out,
                          size_t capacity, size_t *size)
{
    if (!body || !body->read || !body->complete || !out || capacity < 2 || !size)
        return false;
    *size = 0;
    for (;;) {
        if (body->now_us && body->deadline_us &&
            body->now_us(body->context) >= body->deadline_us)
            return false;
        if (*size >= capacity - 1) {
            const bool done = body->complete(body->context);
            if (done) out[*size] = 0;
            return done;
        }
        size_t left = capacity - 1 - *size;
        if (left > INT_MAX) left = INT_MAX;
        const int read = body->read(body->context, out + *size, left);
        if (read < 0 || (size_t)read > left) return false;
        if (!read) {
            const bool done = body->complete(body->context);
            if (done) out[*size] = 0;
            return done;
        }
        *size += (size_t)read;
        if (*size >= capacity - 1 && body->complete(body->context)) {
            out[*size] = 0;
            return true;
        }
    }
}
