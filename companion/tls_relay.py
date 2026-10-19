"""Fixed-destination TCP relay. TLS bytes remain encrypted device-to-Muse."""
import argparse
import asyncio
import ipaddress

TARGETS = {18443: 'api.muse.ai', 18444: 'hatch.metaaivm.com'}


def private_lan(value):
    address = ipaddress.ip_address(value)
    if (address.version != 4 or not address.is_private or address.is_loopback
            or address.is_unspecified or address.is_multicast):
        raise ValueError('One explicit private LAN IPv4 address is required')
    return str(address)


async def forward(reader, writer):
    while True:
        data = await asyncio.wait_for(reader.read(16384), 90)
        if not data:
            return
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 15)


def make_handler(client_ip, host, connect=asyncio.open_connection):
    # Destination is configured locally; clients cannot request arbitrary hosts.
    active = asyncio.Semaphore(6)

    async def handle(reader, writer):
        upstream = None
        try:
            peer = writer.get_extra_info('peername')
            if not peer or peer[0] != client_ip or active.locked():
                return
            async with active:
                remote, upstream = await asyncio.wait_for(connect(host, 443), 12)
                tasks = [asyncio.create_task(forward(reader, upstream)),
                         asyncio.create_task(forward(remote, writer))]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, TimeoutError):
            pass  # Never log payloads, account/device identifiers or credentials.
        finally:
            for stream in (upstream, writer):
                if stream:
                    stream.close()
                    try:
                        await stream.wait_closed()
                    except OSError:
                        pass
    return handle


async def serve(bind, client):
    servers = []
    try:
        for port, host in TARGETS.items():
            servers.append(await asyncio.start_server(make_handler(client, host), bind, port))
        print('MuseStack TLS passthrough relay ready', flush=True)
        await asyncio.gather(*(server.serve_forever() for server in servers))
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True, type=private_lan)
    parser.add_argument('--client', required=True, type=private_lan)
    args = parser.parse_args()
    asyncio.run(serve(args.bind, args.client))


if __name__ == '__main__':
    main()
