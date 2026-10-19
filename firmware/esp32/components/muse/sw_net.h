// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#else
#include <sys/socket.h>
#include <netinet/in.h>
#endif

/* ESP HTTPD listens on an IPv6 dual-stack socket. IPv4 clients therefore
 * arrive as ::ffff:a.b.c.d; compare their normalized network-order IPv4. */
static inline bool sw_sockaddr_ipv4(const struct sockaddr *addr, socklen_t len, uint32_t *out)
{
    if (addr->sa_family == AF_INET && len >= sizeof(struct sockaddr_in)) {
        *out = ((const struct sockaddr_in *)addr)->sin_addr.s_addr;
        return true;
    }
    if (addr->sa_family == AF_INET6 && len >= sizeof(struct sockaddr_in6)) {
        static const unsigned char mapped[12] = {0,0,0,0,0,0,0,0,0,0,0xff,0xff};
        const unsigned char *ip = (const unsigned char *)&((const struct sockaddr_in6 *)addr)->sin6_addr;
        if (memcmp(ip, mapped, sizeof(mapped))) return false;
        memcpy(out, ip + 12, sizeof(*out));
        return true;
    }
    return false;
}

static inline bool sw_setup_peer_allowed(const struct sockaddr *peer, socklen_t peer_len,
        const struct sockaddr *local, socklen_t local_len, uint32_t ap_ip, uint32_t mask)
{
    uint32_t from, to;
    return sw_sockaddr_ipv4(peer, peer_len, &from) && sw_sockaddr_ipv4(local, local_len, &to) &&
        to == ap_ip && (from & mask) == (ap_ip & mask);
}
