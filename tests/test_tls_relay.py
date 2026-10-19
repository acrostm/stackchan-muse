import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest

from companion.tls_relay import make_handler, private_lan


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_opaque_duplex_bytes_reach_only_fixed_upstream(self):
        async def echo(reader, writer):
            try:
                data = await reader.readexactly(256)
                writer.write(data[::-1])
                await writer.drain()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
        target = await asyncio.start_server(echo, '127.0.0.1', 0)
        port = target.sockets[0].getsockname()[1]
        calls = []

        async def connect(host, remote_port):
            calls.append((host, remote_port))
            return await asyncio.open_connection('127.0.0.1', port)
        relay = await asyncio.start_server(make_handler('127.0.0.1', 'api.muse.ai', connect), '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', relay.sockets[0].getsockname()[1])
            writer.write(bytes(range(256)))
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(256), 3), bytes(range(256))[::-1])
            self.assertEqual(calls, [('api.muse.ai', 443)])
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(.02)
        finally:
            relay.close()
            target.close()
            await relay.wait_closed()
            await target.wait_closed()

    async def test_other_clients_never_open_upstream(self):
        async def forbidden(*args):
            self.fail('denied client reached upstream')
        relay = await asyncio.start_server(make_handler('192.168.1.2', 'api.muse.ai', forbidden), '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', relay.sockets[0].getsockname()[1])
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b'')
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            await relay.wait_closed()

    def test_no_wildcard_loopback_or_public_listeners(self):
        for value in ('0.0.0.0', '127.0.0.1', '8.8.8.8', '::1', '224.0.0.1'):
            with self.assertRaises(ValueError):
                private_lan(value)
        self.assertEqual(private_lan('192.168.1.5'), '192.168.1.5')

    def test_firmware_routes_only_exact_official_origins(self):
        source = r'''
#include <assert.h>
#include "muse_tls_route.h"
bool sw_proxy_muse_enabled(void) { return false; }
int main(void) {
 char url[128];
 assert(muse_tls_route_api("https://api.muse.ai/fetch_vms",url,sizeof(url)));
 assert(!strcmp(url,"https://192.168.1.5:18443/fetch_vms"));
 assert(!muse_tls_route_api("https://api.muse.ai.evil/fetch_vms",url,sizeof(url)));
 assert(!muse_tls_route_api("http://api.muse.ai/fetch_vms",url,sizeof(url)));
 assert(!muse_tls_route_api("https://other.test/fetch_vms",url,sizeof(url)));
 assert(!muse_tls_route_api("https://api.muse.ai/fetch_vms",url,4));
 assert(muse_tls_route_noise("hatch.metaaivm.com"));
 assert(!muse_tls_route_noise("hatch.metaaivm.com.evil"));
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-DCONFIG_MUSE_TLS_RELAY_HOST="192.168.1.5"',
                            '-I', str(Path(__file__).resolve().parents[1] / 'firmware/esp32/components/muse'),
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True, capture_output=True)
            subprocess.run([str(path / 'test')], check=True)

    def test_socks_route_disables_legacy_relay(self):
        source = r'''
#include <assert.h>
#include "muse_tls_route.h"
bool sw_proxy_muse_enabled(void) { return true; }
int main(void) {
    char url[128];
    assert(!muse_tls_route_api("https://api.muse.ai/fetch_vms", url, sizeof(url)));
    assert(!muse_tls_route_noise("hatch.metaaivm.com"));
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-DCONFIG_MUSE_TLS_RELAY_HOST="192.168.1.5"',
                            '-I', str(Path(__file__).resolve().parents[1] / 'firmware/esp32/components/muse'),
                            str(path / 'test.c'), '-o', str(path / 'test')],
                           check=True, capture_output=True)
            subprocess.run([str(path / 'test')], check=True)
