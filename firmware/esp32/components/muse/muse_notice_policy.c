// SPDX-License-Identifier: Apache-2.0
#include "muse_notice_policy.h"

muse_notice_policy_t muse_notice_policy_default(void)
{
    return (muse_notice_policy_t){.start_minute = 22 * 60, .end_minute = 8 * 60,
                                 .utc_offset_minute = 8 * 60};
}

bool muse_notice_policy_valid(const muse_notice_policy_t *p)
{
    return p && p->start_minute < 1440 && p->end_minute < 1440 &&
           p->utc_offset_minute >= -720 && p->utc_offset_minute <= 840;
}

bool muse_notice_policy_quiet(const muse_notice_policy_t *p, int64_t utc)
{
    if (!muse_notice_policy_valid(p)) return true;
    if (p->muted) return true;
    if (!p->quiet_enabled) return false;
    if (utc < MUSE_NOTICE_CLOCK_MIN) return true;
    /* Reduce first, so even an extreme valid int64 clock cannot overflow. */
    int local = (int)((utc / 60) % 1440) + p->utc_offset_minute;
    local = (local + 1440) % 1440;
    if (p->start_minute == p->end_minute) return true;
    if (p->start_minute < p->end_minute)
        return local >= p->start_minute && local < p->end_minute;
    return local >= p->start_minute || local < p->end_minute;
}

bool muse_notice_policy_encode(const muse_notice_policy_t *p, uint8_t out[MUSE_NOTICE_POLICY_BYTES])
{
    if (!out || !muse_notice_policy_valid(p)) return false;
    out[0] = 1;
    out[1] = (p->muted ? 1 : 0) | (p->quiet_enabled ? 2 : 0);
    out[2] = 0;
    const uint16_t values[] = {p->start_minute, p->end_minute,
                               (uint16_t)p->utc_offset_minute};
    for (unsigned i = 0; i < 3; ++i) {
        out[3 + 2*i] = values[i] & 255;
        out[4 + 2*i] = values[i] >> 8;
    }
    return true;
}

bool muse_notice_policy_decode(muse_notice_policy_t *p, const uint8_t *data, size_t size)
{
    if (!p || !data || size != MUSE_NOTICE_POLICY_BYTES || data[0] != 1 ||
        (data[1] & ~3U) || data[2]) return false;
    unsigned offset = data[7] | ((unsigned)data[8] << 8);
    muse_notice_policy_t value = {.muted = (data[1] & 1) != 0,
        .quiet_enabled = (data[1] & 2) != 0,
        .start_minute = data[3] | ((unsigned)data[4] << 8),
        .end_minute = data[5] | ((unsigned)data[6] << 8),
        .utc_offset_minute = offset <= 32767 ? (int)offset : (int)offset - 65536};
    if (!muse_notice_policy_valid(&value)) return false;
    *p = value;
    return true;
}
