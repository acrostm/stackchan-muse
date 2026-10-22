// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "muse_notice_core.h"
#include "muse_notice_policy.h"
#include "esp_err.h"

bool muse_notice_publish(const char *message_id, const char *text);
bool muse_notice_pending(void);

typedef struct {
    muse_notice_policy_t policy;
    bool ready;
    bool clock_ready;
    bool quiet_now;
    unsigned unread;
    bool can_read;
    bool read_requested;
    bool reading;
} muse_notice_status_t;

muse_notice_status_t muse_notice_status(void);
esp_err_t muse_notice_set_policy(const muse_notice_policy_t *policy);
bool muse_notice_request_read(void);
bool muse_notice_take_next(char *out, size_t cap, bool *explicit_read);
bool muse_notice_automatic_allowed(void);
/* Nonblocking; the queue owner applies it before any later automatic read. */
void muse_notice_cancel_pending(void);

/* The sole voice owner must finish every claimed message. Only a complete
 * successful synthesis, writes and real output drain may pass played=true.
 * Failure/cancel returns it to unread, never automatic replay. */
void muse_notice_finish(bool played);
