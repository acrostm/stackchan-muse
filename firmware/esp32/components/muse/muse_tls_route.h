// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

/* A fixed-destination TCP relay changes only the socket destination. TLS must
 * still verify (and send SNI for) the original service name. No TLS termination. */
#ifndef CONFIG_MUSE_TLS_RELAY_HOST
#define CONFIG_MUSE_TLS_RELAY_HOST ""
#endif

static inline bool muse_tls_route_api(const char *url, char *out, size_t cap)
{
    const char prefix[] = "https://api.muse.ai/";
    if (!CONFIG_MUSE_TLS_RELAY_HOST[0] || !url ||
        strncmp(url, prefix, sizeof(prefix) - 1)) return false;
    int n = snprintf(out, cap, "https://%s:18443/%s", CONFIG_MUSE_TLS_RELAY_HOST,
                     url + sizeof(prefix) - 1);
    return n > 0 && (size_t)n < cap;
}

static inline bool muse_tls_route_noise(const char *host)
{
    return CONFIG_MUSE_TLS_RELAY_HOST[0] && host && !strcmp(host, "hatch.metaaivm.com");
}
