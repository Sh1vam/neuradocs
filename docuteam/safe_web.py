# safe_web.py -- guarded fetching (Chapter 07, Part C)
import ipaddress
import re
import socket
from functools import lru_cache
from urllib.parse import urljoin, urlparse

MAX_BYTES = 2_000_000
ALLOWED_TYPES = ('text/html', 'text/plain', 'application/json', 'application/xhtml')


@lru_cache(maxsize=2048)
def resolves_public(host, port):
    for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        a = ipaddress.ip_address(info[4][0])
        if (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_reserved or a.is_unspecified):
            return False
    return True


def check_url(url, allow_domains=None):
    u = urlparse(url)
    if u.scheme not in ('http', 'https') or not u.hostname:
        raise ValueError('blocked scheme or host')
    host = u.hostname.lower()
    if allow_domains and not any(host == d or host.endswith('.' + d) for d in allow_domains):
        raise ValueError('domain not allowed')
    if not resolves_public(host, u.port or (443 if u.scheme == 'https' else 80)):
        raise ValueError('resolves to a non-public address')
    return url


def safe_fetch(url, allow_domains=None, timeout=10, max_redirects=3):
    import requests
    for _ in range(max_redirects + 1):
        check_url(url, allow_domains)
        r = requests.get(url, timeout=timeout, allow_redirects=False, stream=True,
                         headers={'User-Agent': 'DocuTeam/1.0 (personal research agent)'})
        if r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get('Location', ''))
            continue                                   # re-checked at the top of the loop
        if not r.headers.get('Content-Type', '').startswith(ALLOWED_TYPES):
            raise ValueError('content type not allowed')
        body = b''
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                raise ValueError('response too large')
        return body.decode(r.encoding or 'utf-8', errors='replace'), url
    raise ValueError('too many redirects')


def to_untrusted_text(html, max_chars=6000):
    import trafilatura
    text = trafilatura.extract(html, include_comments=False, include_tables=True) or ''
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060\ufeff]', '', text)   # invisible characters
    return text[:max_chars]


def wrap(url, text):
    return '<untrusted_web_content source=' + url + '>\n' + text + '\n</untrusted_web_content>'
