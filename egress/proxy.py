# egress/proxy.py -- the only way out of the sandbox: an allowlist proxy (HTTPS CONNECT tunnels only).
# The sandbox has no route to the internet. It can reach THIS proxy, and the proxy only tunnels to allowed domains, on ports
# 80/443, and only to PUBLIC addresses: never localhost, your LAN, the other containers or the cloud metadata address.
import asyncio
import ipaddress
import os
import socket

DEFAULT_ALLOW = 'pypi.org,files.pythonhosted.org,github.com,api.github.com,raw.githubusercontent.com,codeload.github.com,registry.npmjs.org'
ALLOW = [d.strip().lower() for d in os.environ.get('EGRESS_ALLOW', DEFAULT_ALLOW).split(',') if d.strip()]
PORTS = {80, 443}
IDLE = 60


def domain_ok(host, allow):
    host = host.lower().rstrip('.')
    return any(host == d or host.endswith('.' + d) for d in allow)        # "notpypi.org" does not match "pypi.org"


def resolve(host, port):
    return [i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def check_target(host, port, allow=ALLOW, allow_private=False, resolver=resolve, ports=PORTS):
    """(None, ip) when the tunnel is allowed, otherwise (reason, None). We connect to the ip we checked, so DNS cannot be switched afterwards."""
    if port not in ports:
        return f'port {port} is not allowed', None
    if not domain_ok(host, allow):
        return f'{host} is not on the allowlist', None
    try:
        ips = resolver(host, port)
    except OSError:
        return f'cannot resolve {host}', None
    if not ips or (not allow_private and not all(ipaddress.ip_address(ip).is_global for ip in ips)):
        return f'{host} resolves to a non-public address', None
    return None, ips[0]


async def pipe(reader, writer):
    try:
        while data := await asyncio.wait_for(reader.read(65536), IDLE):
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(reader, writer, allow=ALLOW, allow_private=False, ports=PORTS):
    try:
        head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 10)
        method, target, _ = head.split(b'\r\n', 1)[0].decode().split(' ', 2)
        if method != 'CONNECT':
            writer.write(b'HTTP/1.1 405 Only CONNECT (https) is supported\r\n\r\n')
            return
        host, _, port = target.rpartition(':')
        why, ip = check_target(host, int(port), allow, allow_private, ports=ports)
        print(('deny  ' + target + '  ' + why) if why else ('allow ' + target), flush=True)       # an audit trail in the container log
        if why:
            writer.write(b'HTTP/1.1 403 Forbidden\r\n\r\n')
            return
        up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(ip, int(port)), 10)
        writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
        await writer.drain()
        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
    except Exception:
        pass
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handle, os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', '3128')))
    print('egress proxy allows:', ', '.join(ALLOW), flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
