"""Sovereign P2P Wire, Redundant Mempool Broadcaster, and Native Tor/SOCKS5 Tunneling.

Allows sending raw transactions and gasless withdrawal payloads directly
to peers and relayers without leaking the user's IP or identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import socket
import ssl
from typing import Any, List, Optional
import urllib.parse
import urllib.request

from kohaku.edw.tx_builder import GaslessWithdrawPayload, SignedTransaction


class Socks5Error(Exception):
    """Raised when SOCKS5 proxy handshake or connection fails."""
    pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Reads exactly `n` bytes from `sock`, preventing short reads on high-latency Tor circuits."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise Socks5Error(f"Unexpected EOF from SOCKS5 proxy (expected {n} bytes, got {len(buf)})")
        buf.extend(chunk)
    return bytes(buf)


def socks5_connect(
    dest_host: str,
    dest_port: int,
    proxy_host: str = "127.0.0.1",
    proxy_port: int = 9050,
    timeout: float = 10.0,
) -> socket.socket:
    """Establishes a TCP connection through a SOCKS5 proxy (RFC 1928) in pure Python.

    Supports both IPv4 addresses and DNS domains (resolved by the proxy, preventing DNS leaks).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((proxy_host, proxy_port))
    except Exception as e:
        sock.close()
        raise Socks5Error(f"Could not connect to SOCKS5 proxy at {proxy_host}:{proxy_port}: {e}")

    try:
        # 1. Handshake greeting: [VER=5, NMETHODS=1, METHOD=0 (No Authentication)]
        sock.sendall(b"\x05\x01\x00")
        resp = _recv_exact(sock, 2)
        if resp[0] != 5 or resp[1] != 0:
            raise Socks5Error(f"SOCKS5 proxy rejected authentication: {resp.hex()}")

        # 2. Connection request: [VER=5, CMD=1 (CONNECT), RSV=0, ATYP, DEST_ADDR, DEST_PORT]
        req = bytearray(b"\x05\x01\x00")
        try:
            # Check if dest_host is IPv4
            ip_bytes = socket.inet_aton(dest_host)
            req.append(1)  # ATYP = 1 (IPv4)
            req.extend(ip_bytes)
        except OSError:
            # Domain name: ATYP = 3, [len(domain), domain_bytes]
            domain_bytes = dest_host.encode("utf-8")
            if len(domain_bytes) > 255:
                raise Socks5Error(f"Destination domain exceeds 255 bytes: {dest_host}")
            req.append(3)
            req.append(len(domain_bytes))
            req.extend(domain_bytes)

        req.extend(dest_port.to_bytes(2, "big"))
        sock.sendall(req)

        # 3. Connection response: [VER, REP, RSV, ATYP, BND.ADDR, BND.PORT]
        resp = _recv_exact(sock, 4)
        if resp[1] != 0:
            status_code = resp[1]
            raise Socks5Error(f"SOCKS5 proxy connection failed with code {status_code}")

        # Consume exact remaining BND.ADDR and BND.PORT bytes
        atyp = resp[3]
        if atyp == 1:
            _recv_exact(sock, 4 + 2)  # IPv4 + port
        elif atyp == 3:
            addr_len = _recv_exact(sock, 1)[0]
            _recv_exact(sock, addr_len + 2)
        elif atyp == 4:
            _recv_exact(sock, 16 + 2)  # IPv6 + port
        else:
            raise Socks5Error(f"Unsupported SOCKS5 address type: {atyp}")
    except Exception:
        sock.close()
        raise

    return sock


def post_json_rpc(
    url: str,
    payload: dict[str, Any],
    proxy: Optional[str] = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Posts JSON-RPC payload to endpoint. Supports routing via SOCKS5/Tor proxy."""
    data = json.dumps(payload).encode("utf-8")
    parsed = urllib.parse.urlparse(url)
    is_ssl = parsed.scheme == "https"
    port = parsed.port or (443 if is_ssl else 80)
    host = parsed.hostname or "127.0.0.1"
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    if proxy:
        # Extract proxy host and port
        proxy_parsed = urllib.parse.urlparse(proxy if "://" in proxy else f"socks5://{proxy}")
        p_host = proxy_parsed.hostname or "127.0.0.1"
        p_port = proxy_parsed.port or 9050

        # Tunnel socket through SOCKS5 proxy
        raw_sock = socks5_connect(host, port, p_host, p_port, timeout=timeout)
        if is_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            sock = raw_sock

        # Use HTTP/1.0 (RFC 1945) so upstream proxies (Cloudflare/Nginx) never wrap the
        # response in `Transfer-Encoding: chunked` hex framing.
        req_headers = (
            f"POST {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(data)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8") + data

        sock.sendall(req_headers)

        response_bytes = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_bytes.extend(chunk)
        sock.close()

        # Parse HTTP body
        header_end = response_bytes.find(b"\r\n\r\n")
        if header_end == -1:
            raise ValueError("Malformed HTTP response from proxy")
        body = response_bytes[header_end + 4:]
        return json.loads(body.decode("utf-8"))

    # Direct connection without proxy
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "edw-py/0.2.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json_via_proxy(
    url: str,
    proxy: Optional[str] = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Performs an HTTP GET and parses JSON response, supporting SOCKS5/Tor proxy."""
    parsed = urllib.parse.urlparse(url)
    is_ssl = parsed.scheme == "https"
    port = parsed.port or (443 if is_ssl else 80)
    host = parsed.hostname or "127.0.0.1"
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    if proxy:
        proxy_parsed = urllib.parse.urlparse(proxy if "://" in proxy else f"socks5://{proxy}")
        p_host = proxy_parsed.hostname or "127.0.0.1"
        p_port = proxy_parsed.port or 9050

        raw_sock = socks5_connect(host, port, p_host, p_port, timeout=timeout)
        if is_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            sock = raw_sock

        req_headers = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: edw-py/0.2.1\r\n"
            f"Accept: application/json\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8")
        sock.sendall(req_headers)

        response_bytes = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_bytes.extend(chunk)
        sock.close()

        header_end = response_bytes.find(b"\r\n\r\n")
        if header_end == -1:
            raise ValueError("Malformed HTTP response from proxy")
        body = bytes(response_bytes[header_end + 4 :])
        return json.loads(body.decode("utf-8", errors="replace"))

    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "edw-py/0.1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# Default privacy-preserving and public broadcast endpoints
DEFAULT_BROADCAST_PEERS: list[str] = [
    "https://rpc.flashbots.net",               # MEV-protected mempool (no frontrunning)
    "https://ethereum-rpc.publicnode.com",     # Decentralized public node
    "https://cloudflare-eth.com",              # Fallback CDN node
]


@dataclass
class BroadcastResult:
    tx_hash: str
    peer: str
    success: bool
    response: Any
    error: Optional[str] = None


class P2PBroadcaster:
    """Manages redundant broadcast of transactions and payloads across peers and Tor."""

    def __init__(
        self,
        peers: Optional[List[str]] = None,
        tor_proxy: Optional[str] = None,
        timeout: float = 12.0,
        rpc_urls: Optional[List[str]] = None,
        socks5_proxy: Optional[str] = None,
    ):
        self.peers = peers or rpc_urls or list(DEFAULT_BROADCAST_PEERS)
        self.tor_proxy = tor_proxy if tor_proxy is not None else socks5_proxy
        self.timeout = timeout

    def rpc_call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """Executes a JSON-RPC call across configured peers (with optional Tor SOCKS5 proxy)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1,
        }
        last_error = None
        for peer in self.peers:
            try:
                res = post_json_rpc(peer, payload, proxy=self.tor_proxy, timeout=self.timeout)
                if "result" in res:
                    return res["result"]
                if "error" in res:
                    last_error = str(res["error"])
            except Exception as e:
                last_error = str(e)
                continue
        raise ConnectionError(f"Failed JSON-RPC {method} across all peers. Last error: {last_error}")

    def broadcast_raw_tx(self, raw_hex: str) -> BroadcastResult:
        """Attempts broadcast across peers in order until accepted."""
        clean_hex = raw_hex if raw_hex.startswith("0x") else f"0x{raw_hex}"
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_sendRawTransaction",
            "params": [clean_hex],
            "id": 1,
        }

        last_error = None
        for peer in self.peers:
            try:
                res = post_json_rpc(peer, payload, proxy=self.tor_proxy, timeout=self.timeout)
                if "result" in res:
                    return BroadcastResult(
                        tx_hash=res["result"],
                        peer=peer,
                        success=True,
                        response=res,
                    )
                elif "error" in res:
                    last_error = str(res["error"])
            except Exception as e:
                last_error = str(e)
                continue

        raise ConnectionError(f"Failed to broadcast tx across all peers. Last error: {last_error}")

    def dispatch_gasless_withdrawal(
        self,
        payload: GaslessWithdrawPayload,
        relayer_endpoints: List[str],
    ) -> dict[str, Any]:
        """Dispatches a gasless withdrawal payload to autonomous relayer peers."""
        data = payload.to_dict()
        last_error = None

        for endpoint in relayer_endpoints:
            try:
                res = post_json_rpc(endpoint, data, proxy=self.tor_proxy, timeout=self.timeout)
                if res.get("status") in ("accepted", "broadcast", "success") or "tx_hash" in res:
                    return res
                last_error = res.get("error", "Unknown relayer rejection")
            except Exception as e:
                last_error = str(e)
                continue

        raise ConnectionError(f"Failed to dispatch gasless payload to relayers. Last error: {last_error}")
