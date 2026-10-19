from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VoiceHttpBodyTests(unittest.TestCase):
    def test_cached_complete_response_is_drained_before_completion(self):
        source = r'''
#include "sw_http_body.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    const char *text;
    size_t offset;
    int reads;
    bool complete;
    int64_t now;
} fake_t;

static int read_body(void *context, void *data, size_t capacity) {
    fake_t *fake = context;
    ++fake->reads;
    size_t left = strlen(fake->text) - fake->offset;
    if (!left) return 0;
    size_t take = left < capacity ? left : capacity;
    memcpy(data, fake->text + fake->offset, take);
    fake->offset += take;
    return (int)take;
}
static bool is_complete(void *context) { return ((fake_t *)context)->complete; }
static int64_t now_us(void *context) { return ((fake_t *)context)->now; }

int main(void) {
    unsigned char out[64];
    size_t size = 99;
    fake_t cached = {.text = "{\"Result\":[]}", .complete = true};
    sw_http_body_t body = {.context = &cached, .read = read_body,
                           .complete = is_complete, .now_us = now_us,
                           .deadline_us = 100};
    assert(sw_http_body_collect(&body, out, sizeof(out), &size));
    assert(size == strlen(cached.text) && cached.reads == 2);
    assert(!memcmp(out, cached.text, size) && out[size] == 0);

    fake_t incomplete = {.text = "partial", .complete = false};
    body.context = &incomplete;
    assert(!sw_http_body_collect(&body, out, sizeof(out), &size));

    fake_t exact = {.text = "1234567", .complete = true};
    body.context = &exact;
    assert(sw_http_body_collect(&body, out, 8, &size));
    assert(size == 7 && !memcmp(out, "1234567", 7) && out[7] == 0);

    fake_t overflow = {.text = "12345678", .complete = false};
    body.context = &overflow;
    assert(!sw_http_body_collect(&body, out, 8, &size));

    fake_t late = {.text = "abc", .complete = false, .now = 100};
    body.context = &late;
    assert(!sw_http_body_collect(&body, out, sizeof(out), &size));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "test.c").write_text(source)
            binary = path / "test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined",
                "-I", str(ROOT / "firmware/esp32/components/muse"),
                str(path / "test.c"),
                str(ROOT / "firmware/esp32/components/muse/sw_http_body.c"),
                "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
