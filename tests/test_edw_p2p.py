import http.server
import json
import socket
import threading
import time
import pytest

from kohaku.edw.p2p import P2PBroadcaster, Socks5Error, post_json_rpc, socks5_connect
from kohaku.edw.tx_builder import GaslessWithdrawPayload


def test_socks5_handshake_mock_server():
    """Starts a local mock SOCKS5 proxy to verify RFC 1928 handshake in pure Python."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)

    def _mock_proxy():
        conn, _ = server.accept()
        # 1. Read greeting
        greet = conn.recv(3)
        assert greet == b"\x05\x01\x00"
        conn.sendall(b"\x05\x00")  # Accept no auth

        # 2. Read connect request
        req = conn.recv(10)
        assert req[0] == 5 and req[1] == 1  # CONNECT
        # Respond success [VER=5, REP=0, RSV=0, ATYP=1, IP=0.0.0.0, PORT=0]
        conn.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        conn.close()

    t = threading.Thread(target=_mock_proxy, daemon=True)
    t.start()

    # Connect client
    sock = socks5_connect("1.2.3.4", 80, proxy_host="127.0.0.1", proxy_port=port, timeout=2.0)
    assert sock is not None
    sock.close()
    server.close()


def test_p2p_broadcaster_with_failover():
    """Verifies that P2PBroadcaster fails over from broken peers to healthy peers."""
    received_requests = []

    class MockRpcHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(content_length).decode())
            received_requests.append((self.server.server_port, body))

            if self.server.server_port == port1:
                # Primary peer returns 500 error
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Internal Error")
            else:
                # Secondary peer returns success
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                resp = {"jsonrpc": "2.0", "result": "0xdeadbeef1234567890", "id": 1}
                self.wfile.write(json.dumps(resp).encode())

        def log_message(self, format, *args):
            pass

    server1 = http.server.HTTPServer(("127.0.0.1", 0), MockRpcHandler)
    port1 = server1.server_port
    t1 = threading.Thread(target=server1.serve_forever, daemon=True)
    t1.start()

    server2 = http.server.HTTPServer(("127.0.0.1", 0), MockRpcHandler)
    port2 = server2.server_port
    t2 = threading.Thread(target=server2.serve_forever, daemon=True)
    t2.start()

    broadcaster = P2PBroadcaster(peers=[f"http://127.0.0.1:{port1}", f"http://127.0.0.1:{port2}"])
    res = broadcaster.broadcast_raw_tx("0x02deadbeef")

    assert res.success is True
    assert res.tx_hash == "0xdeadbeef1234567890"
    assert res.peer == f"http://127.0.0.1:{port2}"

    server1.shutdown()
    server2.shutdown()


def test_dispatch_gasless_withdrawal():
    """Verifies dispatching gasless withdrawal payload to relayer."""
    class MockRelayerHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {"status": "accepted", "tx_hash": "0x9876543210"}
            self.wfile.write(json.dumps(resp).encode())

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), MockRelayerHandler)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    payload = GaslessWithdrawPayload(
        ticket_id="ticket-1",
        pool_id="tornado-cash-1-eth-0.1",
        pool_address="0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
        recipient_address="0x1111111111111111111111111111111111111111",
        relayer_address="0x2222222222222222222222222222222222222222",
        relayer_fee_wei=1000,
        relayer_fee_eth=0.001,
        net_recipient_wei=99000,
        net_recipient_eth=0.099,
        calldata="0x21a0adb6...",
        chain_id=1,
        nullifier_hash="0x3333...",
        root="0x4444...",
    )

    broadcaster = P2PBroadcaster()
    res = broadcaster.dispatch_gasless_withdrawal(payload, [f"http://127.0.0.1:{port}"])
    assert res["status"] == "accepted"
    assert res["tx_hash"] == "0x9876543210"

    server.shutdown()
