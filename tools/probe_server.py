"""Tiny, unauthenticated, READ-ONLY XP connectivity probe test server."""
import argparse
import asyncio
import ipaddress
import re

async def handler(reader, writer):
    try:
        line = (await asyncio.wait_for(reader.readline(), 3)).decode('ascii', 'replace').strip()
        okay = re.fullmatch(r'HXP1 [A-Za-z0-9-]{1,63}', line) is not None
        writer.write(b'HXP1 OK\r\n' if okay else b'HXP1 BAD\r\n')
        await writer.drain()
        if okay:
            print('Probe from',writer.get_extra_info('peername'),':',line[5:])
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()

async def main(ip):
    addr=ipaddress.ip_address(ip)
    if addr.version != 4 or not (addr.is_private or addr.is_loopback):
        raise SystemExit('Bind must be a private IPv4 or loopback address, never 0.0.0.0')
    server = await asyncio.start_server(handler, ip, 18765)
    print(f'XP connectivity probe listening on {ip}:18765. Read-only test; no authentication.')
    async with server: await server.serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bind', required=True, help='Host LAN IPv4, e.g. 192.168.1.20')
    args=parser.parse_args()
    asyncio.run(main(args.bind))
