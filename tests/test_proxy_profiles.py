"""SSID-scoped policy isolation, edits, bounded persistence and malformed input."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Profiles(unittest.TestCase):
    def test_profile_isolation_and_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'profiles.c'
            source.write_text('''#include "sw_proxy_core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
 sw_proxy_profiles_t p={0}; sw_proxy_config_t c={.host="192.168.1.4",.port=7897,.enabled=true},out;
 assert(sw_proxy_profile_set(&p,"home",&c));
 sw_proxy_config_t direct={0},disabled={.port=7897};
 assert(!sw_proxy_restart_needed(&direct,&disabled,true,false));
 assert(sw_proxy_restart_needed(&direct,&c,true,false));
 assert(!sw_proxy_restart_needed(&direct,&c,false,false));
 assert(!sw_proxy_restart_needed(&direct,&c,true,true));
 assert(sw_proxy_restart_needed(&c,&direct,true,false));
 sw_proxy_config_t changed=c;changed.port=1080;
 assert(sw_proxy_restart_needed(&c,&changed,true,false));
 assert(!sw_proxy_restart_needed(&c,&c,true,false));
 sw_proxy_profile_get(&p,"phone",&out); assert(!out.enabled && !out.host[0]);
 sw_proxy_profile_get(&p,"home",&out); assert(out.enabled && out.port==7897);
 c.enabled=false; assert(sw_proxy_profile_set(&p,"home",&c));
 sw_proxy_profile_get(&p,"home",&out); assert(!out.enabled && out.port==7897);
 c.enabled=true; c.port=1080; strcpy(c.host,"192.168.1.5");
 assert(sw_proxy_profile_set(&p,"home",&c));
 sw_proxy_profile_get(&p,"home",&out); assert(out.enabled && out.port==1080 && !strcmp(out.host,"192.168.1.5"));
 sw_proxy_profile_get(&p,"HOME",&out); assert(!out.enabled);
 for(unsigned i=1;i<SW_PROXY_PROFILES_MAX;i++){char name[33];snprintf(name,sizeof(name),"net%u",i);assert(sw_proxy_profile_set(&p,name,&c));}
 sw_proxy_profiles_t before=p;assert(!sw_proxy_profile_set(&p,"overflow",&c));assert(!memcmp(&p,&before,sizeof(p)));
 assert(sw_proxy_profile_set(&p,"home",&c)); assert(sw_proxy_profiles_valid(&p));
 assert(!sw_proxy_profile_set(&p,"",&c));
 assert(!sw_proxy_profile_set(&p,"123456789012345678901234567890123",&c));
 c.port=0; assert(!sw_proxy_profile_set(&p,"home",&c));
 c.port=7897;strcpy(c.host,"8.8.8.8");assert(!sw_proxy_profile_set(&p,"home",&c));
 memset(p.entries[0].ssid,'x',33);assert(!sw_proxy_profiles_valid(&p));
 p=before;strcpy(p.entries[1].ssid,"home");assert(!sw_proxy_profiles_valid(&p));
 p=before;c=(sw_proxy_config_t){0};assert(sw_proxy_profile_set(&p,"overflow",&c));
 assert(!memcmp(&p,&before,sizeof(p))); /* Unknown direct network consumes no slot. */
 assert(sw_proxy_profile_set(&p,"home",&c));assert(!p.entries[0].ssid[0]);
 c=(sw_proxy_config_t){.host="10.0.0.1",.port=1080,.enabled=true};assert(sw_proxy_profile_set(&p,"replacement",&c));
 return 0;
}''')
            binary=p/'profiles'
            subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(ROOT / 'firmware/esp32/components/muse'),str(source),str(ROOT/'firmware/esp32/components/muse/sw_proxy_core.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
