// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "muse_notice_core.h"

bool muse_notice_publish(const char *message_id, const char *text);
bool muse_notice_take(char *out, size_t cap);
bool muse_notice_pending(void);
