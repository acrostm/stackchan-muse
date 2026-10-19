#!/usr/bin/env python3
"""Build the pinned StackChan firmware with project-local IDF tools."""
import argparse
import json
import ipaddress
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-token', action='store_true',
                        help='Embed local Muse SDK token; keep generated binaries private')
    parser.add_argument('--board', choices=('stackchan', 'cores3'), default='stackchan')
    parser.add_argument('--text-replies', action='store_true',
                        help='Use the verified upstream text path for capability probing')
    parser.add_argument("--with-relay", action="store_true", help="Use private network.tls_relay_host; TLS verification stays enabled")
    args = parser.parse_args()
    idf = ROOT / '.toolchains/esp-idf'
    tools = ROOT / '.toolchains/tools'
    python_env = tools / 'python_env/idf6.0_py3.14_env'
    compiler = tools / 'tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin'
    suffix = ('-' + args.board if args.board != 'stackchan' else '')
    suffix += '-text' if args.text_replies else ''
    suffix += '-private' if args.with_token else ''
    build = ROOT / ('build-musestack' + suffix)
    build.mkdir(exist_ok=True, mode=0o700)
    project = ROOT / 'firmware/esp32'
    defaults = [project / 'sdkconfig.defaults', project / 'devices/sdkconfig.muse',
                project / ('devices/sdkconfig.muse-m5stack-' + args.board)]
    local_defaults = ['CONFIG_MUSE_TLS_RELAY_HOST=""']
    if args.with_token:
        config = json.loads((ROOT / '.private/config.json').read_text())
        token = config.get('muse_sdk_token')
        if not isinstance(token, str) or not token.startswith('mgst_') or not token.isascii():
            parser.error('Invalid or missing local Muse SDK token')
        local_defaults.append('CONFIG_GADGET_SDK_TOKEN=' + json.dumps(token))
    if args.with_relay:
        config = json.loads((ROOT / '.private/config.json').read_text())
        address = ipaddress.ip_address(config.get('network', {}).get('tls_relay_host', ''))
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
            parser.error('TLS relay must be one explicit private LAN IPv4 address')
        local_defaults[0] = 'CONFIG_MUSE_TLS_RELAY_HOST=' + json.dumps(str(address))
    if args.text_replies:
        local_defaults.append('CONFIG_MUSE_TEXT_REPLIES=y')
    if local_defaults:
        overlay = ROOT / ('.private/sdkconfig' + suffix + '.defaults')
        overlay.touch(mode=0o600, exist_ok=True)
        overlay.chmod(0o600)
        overlay.write_text('\n'.join(local_defaults) + '\n')
        defaults.append(overlay)
        generated = build / 'sdkconfig'
        if generated.exists():
            keys = {line.split('=', 1)[0] for line in local_defaults}
            lines = [line for line in generated.read_text().splitlines()
                     if line.split('=', 1)[0] not in keys
                     and not any(line == '# ' + key + ' is not set' for key in keys)]
            generated.write_text('\n'.join(lines + local_defaults) + '\n')
            generated.chmod(0o600)
    env = dict(os.environ)
    for key in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'https_proxy', 'http_proxy', 'all_proxy'):
        env.pop(key, None)
    env.update(ESP_IDF_VERSION='6.0.1', IDF_PATH=str(idf), IDF_TOOLS_PATH=str(tools),
               IDF_PYTHON_ENV_PATH=str(python_env))
    env['PATH'] = os.pathsep.join([str(python_env / 'bin'), str(compiler),
                                  str(ROOT / '.venv/bin'), env.get('PATH', '')])
    command = [str(python_env / 'bin/python'), str(idf / 'tools/idf.py'),
               '-C', str(project), '-B', str(build), '-DIDF_TARGET=esp32s3',
               '-DSDKCONFIG=' + str(build / 'sdkconfig'),
               '-DSDKCONFIG_DEFAULTS=' + ';'.join(map(str, defaults)), 'build']
    raise SystemExit(subprocess.run(command, env=env).returncode)


if __name__ == '__main__':
    main()
