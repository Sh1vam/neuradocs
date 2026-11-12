# scripts/stress_test.py -- load test for a running NeuraDocs.
#   python scripts/stress_test.py --url http://127.0.0.1:8001 [--password PW] [--readers 10] [--chatters 10] [--runners 0] [--seconds 15]
# Start the server with FAKE_LLM=1 (FAKE_LLM_DELAY=1.0) to test the infrastructure without spending Groq tokens.
# --runners N also runs N users that execute Python in the sandbox (needs the sandbox; slow: it is the scarce resource).
import argparse
import asyncio
import statistics
import time

import httpx


async def timed(samples, name, call):
    t = time.perf_counter()
    try:
        ok = await call()
    except Exception:
        ok = False
    samples.setdefault(name, []).append((time.perf_counter() - t, bool(ok)))


async def reader(c, end, samples):
    async def get(path):
        return (await c.get(path)).status_code == 200
    while time.time() < end:
        await timed(samples, 'read chats', lambda: get('/api/chats'))
        await timed(samples, 'read projects', lambda: get('/api/projects'))


async def chatter(c, end, samples):
    async def ask():
        done = False
        async with c.stream('POST', '/api/chat', json={'message': 'stress test message', 'stream': True}) as r:
            async for line in r.aiter_lines():
                done = done or '"done": true' in line
        return done
    while time.time() < end:
        await timed(samples, 'chat stream', ask)


async def runner(c, end, samples):
    async def run():
        r = await c.post('/api/mcp/tool/call', json={'tool': 'run_python', 'args': {'code': 'print(sum(range(10**6)))'}}, timeout=90)
        return r.status_code == 200 and 'exit 0' in r.text
    while time.time() < end:
        await timed(samples, 'sandbox run', run)


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * q))] * 1000 if values else 0


async def main():
    a = argparse.ArgumentParser()
    a.add_argument('--url', default='http://127.0.0.1:8001')
    a.add_argument('--password', default='')
    a.add_argument('--readers', type=int, default=10)
    a.add_argument('--chatters', type=int, default=10)
    a.add_argument('--runners', type=int, default=0)
    a.add_argument('--seconds', type=int, default=15)
    o = a.parse_args()
    samples, end = {}, time.time() + o.seconds
    limits = httpx.Limits(max_connections=500)
    async with httpx.AsyncClient(base_url=o.url, auth=('u', o.password) if o.password else None, timeout=120, limits=limits) as c:
        tasks = [reader(c, end, samples) for _ in range(o.readers)] + [chatter(c, end, samples) for _ in range(o.chatters)] \
              + [runner(c, end, samples) for _ in range(o.runners)]
        await asyncio.gather(*tasks)
    print(f'{o.readers} readers, {o.chatters} chat streams, {o.runners} sandbox users for {o.seconds}s against {o.url}')
    print(f'{"scenario":14} {"requests":>8} {"errors":>6} {"req/s":>7} {"p50 ms":>8} {"p95 ms":>8} {"p99 ms":>8}')
    for name, rows in sorted(samples.items()):
        t = [r[0] for r in rows]
        print(f'{name:14} {len(rows):8} {sum(1 for r in rows if not r[1]):6} {len(rows) / o.seconds:7.1f} '
              f'{statistics.median(t) * 1000:8.0f} {pct(t, .95):8.0f} {pct(t, .99):8.0f}')


if __name__ == '__main__':
    asyncio.run(main())
