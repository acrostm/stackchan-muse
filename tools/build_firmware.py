#!/usr/bin/env python3
"""Build the pinned StackChan firmware with project-local IDF tools."""
import argparse
import json
import ipaddress
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-token', action='store_true',
                        help='Embed local Muse SDK token; keep generated binaries private')
    parser.add_argument('--board', choices=('stackchan', 'cores3'), default='stackchan')
    parser.add_argument('--text-replies', action='store_true',
                        help='Use the verified upstream text path for capability probing')
    parser.add_argument("--with-relay", action="store_true", help="Use private network.tls_relay_host; TLS verification stays enabled")
    parser.add_argument("--online", action="store_true",
                        help="Resolve components online instead of the verified local cache")
    parser.add_argument("--with-local-tts", action="store_true", help="Configure private authenticated Chinese TTS bridge")
    parser.add_argument('--with-camera', action='store_true',
                        help='Enable the experimental CoreS3 GC0308 still camera')
    parser.add_argument('--with-handsfree', action='store_true',
                        help='Build experimental local wake/VAD with a model partition')
    args = parser.parse_args()
    if args.with_camera and args.board != 'stackchan':
        parser.error('--with-camera is only supported for --board stackchan')
    if args.with_handsfree and args.board != 'stackchan':
        parser.error('--with-handsfree is only supported for --board stackchan')
    idf = ROOT / '.toolchains/esp-idf'
    tools = ROOT / '.toolchains/tools'
    python_env = tools / 'python_env/idf6.0_py3.14_env'
    compiler = tools / 'tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin'
    suffix = ('-' + args.board if args.board != 'stackchan' else '')
    suffix += '-camera' if args.with_camera else ''
    suffix += '-handsfree' if args.with_handsfree else ''
    suffix += '-text' if args.text_replies else ''
    suffix += '-private' if args.with_token or args.with_local_tts else ''
    build = ROOT / ('build-musestack' + suffix)
    build.mkdir(exist_ok=True, mode=0o700)
    project = ROOT / 'firmware/esp32'
    defaults = [project / 'sdkconfig.defaults', project / 'devices/sdkconfig.muse',
                project / ('devices/sdkconfig.muse-m5stack-' + args.board)]
    local_defaults = ['CONFIG_MUSE_TLS_RELAY_HOST=""',
                      'CONFIG_MUSE_LOCAL_TTS_URL=""', 'CONFIG_MUSE_LOCAL_TTS_TOKEN=""',
                      'CONFIG_MUSE_LOCAL_TTS_FALLBACK_URL=""', 'CONFIG_HOMEHUB_OTA_ENABLED=n']
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
    if args.with_local_tts:
        config = json.loads((ROOT / '.private/config.json').read_text())
        network = config.get('network', {})
        url = network.get('tts_url') or ('http://' + network.get('tls_relay_host', '') + ':8765/tts')
        parsed = urlsplit(url)
        try:
            address = ipaddress.ip_address(parsed.hostname or '')
            port = parsed.port
        except ValueError:
            parser.error('TTS bridge requires a valid private IPv4 URL')
        if (parsed.scheme not in ('http', 'https') or address.version != 4 or
                not address.is_private or address.is_loopback or address.is_unspecified or
                address.is_multicast or parsed.username or parsed.password or parsed.query or
                parsed.fragment or parsed.path != '/tts' or not port or not 1 <= port <= 65535):
            parser.error('TTS bridge requires one explicit private LAN IPv4 /tts endpoint')
        token = config.get('tts_proxy_token', '')
        if not isinstance(token, str) or len(token) < 24 or len(token) > 255 or not all(33 <= ord(c) <= 126 for c in token):
            parser.error('Invalid or missing private TTS bridge token')
        local_defaults[1] = 'CONFIG_MUSE_LOCAL_TTS_URL=' + json.dumps(url)
        local_defaults[2] = 'CONFIG_MUSE_LOCAL_TTS_TOKEN=' + json.dumps(token)
    if args.text_replies:
        local_defaults.append('CONFIG_MUSE_TEXT_REPLIES=y')
    if args.with_camera:
        local_defaults.append('CONFIG_MUSE_STACKCHAN_CAMERA=y')
    if args.with_handsfree:
        local_defaults.extend(['CONFIG_MUSE_HANDSFREE=y',
            'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_muse_handsfree.csv"'])
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_dependency_lock import constraints
    import yaml
    constraint_file = build / "reviewed.constraints"
    constraint_file.write_text(constraints(yaml.safe_load(
        (ROOT / "docs/firmware-dependencies.lock.yml").read_text())))
    env = dict(os.environ)
    env.pop("IDF_COMPONENT_CONSTRAINTS", None)
    env["IDF_COMPONENT_CONSTRAINT_FILES"] = str(constraint_file)
    if not args.online:
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
    result = subprocess.run(command, env=env).returncode
    if result == 0 and args.with_handsfree:
        for checker in ('check_speech_model.py', 'check_dependency_lock.py'):
            target = build if checker == 'check_speech_model.py' else project / 'dependencies.lock'
            result = subprocess.run([str(python_env / 'bin/python'),
                                     str(ROOT / 'tools' / checker), str(target)], env=env).returncode
            if result:
                break
    raise SystemExit(result)


if __name__ == '__main__':
    main()
