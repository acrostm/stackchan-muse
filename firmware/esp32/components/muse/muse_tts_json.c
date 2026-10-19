// SPDX-License-Identifier: Apache-2.0
#include "muse_tts_json.h"
#include <string.h>

static size_t utf8_width(const unsigned char *p)
{
    if (p[0] < 0x80) return 1;
    size_t width = p[0] >= 0xc2 && p[0] <= 0xdf ? 2 :
                   p[0] >= 0xe0 && p[0] <= 0xef ? 3 :
                   p[0] >= 0xf0 && p[0] <= 0xf4 ? 4 : 0;
    if (!width) return 0;
    for (size_t i = 1; i < width; ++i) {
        if ((p[i] & 0xc0) != 0x80) return 0;
    }
    if ((p[0] == 0xe0 && p[1] < 0xa0) || (p[0] == 0xed && p[1] >= 0xa0) ||
        (p[0] == 0xf0 && p[1] < 0x90) || (p[0] == 0xf4 && p[1] >= 0x90)) return 0;
    return width;
}

bool muse_utf8_append(char *output, size_t capacity, const char *text)
{
    if (!output || !capacity || !text) return false;
    size_t used = 0;
    while (used < capacity && output[used]) ++used;
    if (used == capacity) return false;
    const unsigned char *p = (const unsigned char *)text;
    while (*p) {
        size_t width = utf8_width(p);
        if (!width || width > capacity - used - 1) return false;
        memcpy(output + used, p, width);
        used += width;
        output[used] = '\0';
        p += width;
    }
    return true;
}

bool muse_tts_json(const char *text, size_t max_chars, char *output,
                   size_t capacity, size_t *written)
{
    if (written) *written = 0;
    if (output && capacity) output[0] = '\0';
    const char prefix[] = "{\"text\":\"";
    size_t used = sizeof(prefix) - 1;
    if (!text || !text[0] || !max_chars || !output || capacity < used + 3) return false;
    memcpy(output, prefix, used);
    const unsigned char *p = (const unsigned char *)text;
    for (size_t chars = 0; *p && chars < max_chars; ++chars) {
        size_t width = utf8_width(p);
        bool escape = *p == '"' || *p == '\\';
        size_t take = escape ? 2 : width;
        if (!width || take > capacity - used - 3) {
            output[0] = '\0';
            return false;
        }
        if (escape) output[used++] = '\\';
        if (*p < 0x20) output[used++] = ' ';
        else { memcpy(output + used, p, width); used += width; }
        p += width;
    }
    output[used++] = '"';
    output[used++] = '}';
    output[used] = '\0';
    if (written) *written = used;
    return true;
}
