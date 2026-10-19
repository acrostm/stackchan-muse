// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
/* Volcengine V4 signing for the fixed ListSpeakers endpoint. */
bool sw_voice_sign(const char *ak, const char *sk, const char *date,
                   const char *body, char hash[65], char *authorization, size_t cap);
