from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HandsfreeStatusTests(unittest.TestCase):
    def test_owner_state_and_request_acknowledgement(self):
        base = ROOT / 'firmware/esp32/components/muse'
        source = (base / 'muse_voice.c').read_text()
        code = source[source.index('muse_voice_handsfree_status_t muse_voice_handsfree_status('):source.index('bool muse_voice_request_sr_probe(')]
        header = (base / 'muse_voice.h').read_text()
        declaration = header[header.index('typedef struct {'):header.index('muse_voice_handsfree_status_t;') + len('muse_voice_handsfree_status_t;')]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdatomic.h>
#include <string.h>
#include "muse_handsfree_core.h"
DECLARATION
#if CONFIG_MUSE_HANDSFREE
static atomic_bool s_hf_requested,s_hf_owner_running,s_hf_failed;
static atomic_uint s_hf_public;
typedef enum {MUSE_MODE_IDLE,MUSE_MODE_LISTENING,MUSE_MODE_THINKING,MUSE_MODE_SPEAKING} muse_mode_t;
static muse_mode_t mode;
static int stopped;
static muse_mode_t muse_state_mode(void *p) {(void)p;return mode;}
static void muse_voice_request_stop(void) {++stopped;}
static void muse_state_nudge(void) {}
#endif
CODE
int main(void) {
 muse_voice_handsfree_status_t status=muse_voice_handsfree_status();
#if CONFIG_MUSE_HANDSFREE
 assert(status.supported && !strcmp(status.state,"unavailable"));
 assert(!muse_voice_set_handsfree(true));
 atomic_store(&s_hf_owner_running,true);
 assert(!strcmp(muse_voice_handsfree_status().state,"off"));
 assert(muse_voice_set_handsfree(true));status=muse_voice_handsfree_status();
 assert(status.requested && !status.enabled && !strcmp(status.state,"starting"));
 atomic_store(&s_hf_public,256u|MUSE_HF_IDLE);status=muse_voice_handsfree_status();
 assert(status.enabled && !strcmp(status.state,"wake"));
 atomic_store(&s_hf_public,256u|MUSE_HF_FOLLOW);assert(!strcmp(muse_voice_handsfree_status().state,"follow"));
 mode=MUSE_MODE_LISTENING;assert(!strcmp(muse_voice_handsfree_status().state,"recording"));
 mode=MUSE_MODE_SPEAKING;assert(!strcmp(muse_voice_handsfree_status().state,"busy"));
 mode=MUSE_MODE_IDLE;atomic_store(&s_hf_public,256u|MUSE_HF_BLOCKED);assert(!strcmp(muse_voice_handsfree_status().state,"paused"));
 atomic_store(&s_hf_public,256u|MUSE_HF_COOLDOWN);assert(!strcmp(muse_voice_handsfree_status().state,"cooldown"));
 assert(muse_voice_set_handsfree(false) && stopped==1);
 status=muse_voice_handsfree_status();assert(!status.requested && status.enabled && !strcmp(status.state,"stopping"));
 atomic_store(&s_hf_public,0);assert(!strcmp(muse_voice_handsfree_status().state,"off"));
 atomic_store(&s_hf_failed,true);assert(!strcmp(muse_voice_handsfree_status().state,"error"));
 muse_voice_set_handsfree(false);assert(!strcmp(muse_voice_handsfree_status().state,"off"));
#else
 assert(!status.supported && !status.requested && !status.enabled && !strcmp(status.state,"unsupported"));
 assert(!muse_voice_set_handsfree(true));assert(!muse_voice_set_handsfree(false));
#endif
 return 0;
}
'''.replace('DECLARATION', declaration).replace('CODE', code)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(harness)
            for enabled in (0, 1):
                subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                '-fsanitize=address,undefined', f'-DCONFIG_MUSE_HANDSFREE={enabled}',
                                '-I', str(base), str(p / 'test.c'), '-o', str(p / 'test')], check=True)
                subprocess.run([str(p / 'test')], check=True)
