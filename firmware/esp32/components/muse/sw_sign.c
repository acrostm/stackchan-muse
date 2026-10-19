// SPDX-License-Identifier: Apache-2.0
#include "sw_sign.h"
#include "sw_core.h"
#include "mbedtls/md.h"
#include <stdio.h>
#include <string.h>

static bool digest(const void *key, size_t kn, const char *s, unsigned char out[32])
{
    const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!md) return false;
    if (!key) return mbedtls_md(md, (const unsigned char *)s, strlen(s), out) == 0;
    /* Mbed TLS 4 removed the legacy HMAC API. RFC 2104, SHA-256 block=64. */
    unsigned char block[64] = {0}, inner[32] = {0}, input[320] = {0};
    size_t n = strlen(s);
    if (n > sizeof(input) - 64) return false;
    bool ok = true;
    if (kn > 64) ok = mbedtls_md(md, key, kn, block) == 0;
    else memcpy(block, key, kn);
    for (unsigned i = 0; i < 64; ++i) input[i] = block[i] ^ 0x36;
    memcpy(input + 64, s, n);
    ok = ok && mbedtls_md(md, input, 64 + n, inner) == 0;
    for (unsigned i = 0; i < 64; ++i) input[i] = block[i] ^ 0x5c;
    memcpy(input + 64, inner, 32);
    ok = ok && mbedtls_md(md, input, 96, out) == 0;
    memset(block, 0, sizeof(block)); memset(inner, 0, sizeof(inner)); memset(input, 0, sizeof(input));
    return ok;
}
static void hex(const unsigned char bytes[32], char out[65])
{
    static const char chars[] = "0123456789abcdef";
    for (unsigned i = 0; i < 32; ++i) { out[2*i] = chars[bytes[i] >> 4]; out[2*i+1] = chars[bytes[i] & 15]; }
    out[64] = 0;
}
bool sw_voice_sign(const char *ak, const char *sk, const char *date,
                   const char *body, char hash[65], char *authorization, size_t cap)
{
    if (!ak || !sk || !date || !body || !*ak || !*sk || !sw_header_safe(ak, 128) ||
        !sw_header_safe(sk, 256) || strlen(date) != 16) return false;
    for (unsigned i = 0; i < 16; ++i)
        if (i == 8 ? date[i] != 'T' : i == 15 ? date[i] != 'Z' : date[i] < '0' || date[i] > '9') return false;
    for (const char *p = ak; *p; ++p)
        if (!((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
              (*p >= '0' && *p <= '9') || *p == '-' || *p == '_')) return false;
    char day[9], canonical[640], canonical_hash[65], scope[96], signing[256], signature[65];
    unsigned char bytes[32] = {0}, key[32] = {0}, next[32] = {0};
    memcpy(day, date, 8); day[8] = 0;
    bool ok = digest(NULL, 0, body, bytes);
    hex(bytes, hash);
    snprintf(canonical, sizeof(canonical), "POST\n/\nAction=ListSpeakers&Version=2025-05-20\nhost:open.volcengineapi.com\nx-content-sha256:%s\nx-date:%s\n\nhost;x-content-sha256;x-date\n%s", hash, date, hash);
    ok = ok && digest(NULL, 0, canonical, bytes);
    hex(bytes, canonical_hash);
    snprintf(scope, sizeof(scope), "%s/cn-beijing/speech_saas_prod/request", day);
    snprintf(signing, sizeof(signing), "HMAC-SHA256\n%s\n%s\n%s", date, scope, canonical_hash);
    ok = ok && digest(sk, strlen(sk), day, key) && digest(key, 32, "cn-beijing", next) &&
        digest(next, 32, "speech_saas_prod", key) && digest(key, 32, "request", next) && digest(next, 32, signing, bytes);
    hex(bytes, signature);
    int n = snprintf(authorization, cap, "HMAC-SHA256 Credential=%s/%s, SignedHeaders=host;x-content-sha256;x-date, Signature=%s", ak, scope, signature);
    memset(key, 0, sizeof(key)); memset(next, 0, sizeof(next)); memset(bytes, 0, sizeof(bytes));
    return ok && n > 0 && (size_t)n < cap;
}
