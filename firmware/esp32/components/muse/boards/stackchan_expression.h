// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>

/* Queue at most one short, content-derived gesture for a finished reply. */
void stackchan_express_reply(const char *text);

/* Use the token captured when the originating turn was submitted. */
void stackchan_express_reply_for_generation(const char *text, uint32_t generation);
