from __future__ import annotations

import queue
import socket
import threading

from httpx import AsyncClient


def _start_tcp_listener() -> tuple[int, queue.Queue[bytes], threading.Thread, socket.socket]:
    received: queue.Queue[bytes] = queue.Queue()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = int(server.getsockname()[1])

    def target() -> None:
        conn, _ = server.accept()
        with conn:
            received.put(conn.recv(4096))
        server.close()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return port, received, thread, server


def _start_udp_listener() -> tuple[int, queue.Queue[bytes], threading.Thread, socket.socket]:
    received: queue.Queue[bytes] = queue.Queue()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = int(server.getsockname()[1])

    def target() -> None:
        data, _ = server.recvfrom(4096)
        received.put(data)
        server.close()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return port, received, thread, server


class TestNotificationSocketSmoke:
    async def test_socket_instance_test_endpoint_sends_tcp_bytes(self, async_client: AsyncClient):
        port, received, thread, server = _start_tcp_listener()
        try:
            create_resp = await async_client.post(
                "/api/notifications/instances",
                json={
                    "name": "TCP Socket",
                    "type": "socket",
                    "enabled": True,
                    "config": {
                        "protocol": "tcp",
                        "host": "127.0.0.1",
                        "port": port,
                        "message_mode": "string",
                        "message_text": "Alert from {source_name}",
                        "encoding": "utf-8",
                    },
                },
            )
            assert create_resp.status_code == 201, create_resp.text

            test_resp = await async_client.post(
                f"/api/notifications/instances/{create_resp.json()['id']}/test"
            )

            assert test_resp.status_code == 200, test_resp.text
            assert received.get(timeout=2) == b"Alert from Test Source"
            thread.join(timeout=2)
        finally:
            server.close()

    async def test_socket_instance_test_endpoint_sends_udp_hex_bytes(self, async_client: AsyncClient):
        port, received, thread, server = _start_udp_listener()
        try:
            create_resp = await async_client.post(
                "/api/notifications/instances",
                json={
                    "name": "UDP Socket",
                    "type": "socket",
                    "enabled": True,
                    "config": {
                        "protocol": "udp",
                        "host": "127.0.0.1",
                        "port": port,
                        "message_mode": "hex",
                        "message_hex": "41424344",
                    },
                },
            )
            assert create_resp.status_code == 201, create_resp.text

            test_resp = await async_client.post(
                f"/api/notifications/instances/{create_resp.json()['id']}/test"
            )

            assert test_resp.status_code == 200, test_resp.text
            assert received.get(timeout=2) == b"ABCD"
            thread.join(timeout=2)
        finally:
            server.close()

    async def test_socket_instance_test_endpoint_waits_for_tcp_response(self, async_client: AsyncClient):
        received: queue.Queue[bytes] = queue.Queue()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = int(server.getsockname()[1])

        def target() -> None:
            conn, _ = server.accept()
            with conn:
                received.put(conn.recv(4096))
                conn.sendall(b"ACK")
            server.close()

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        try:
            create_resp = await async_client.post(
                "/api/notifications/instances",
                json={
                    "name": "TCP Socket Wait",
                    "type": "socket",
                    "enabled": True,
                    "config": {
                        "protocol": "tcp",
                        "host": "127.0.0.1",
                        "port": port,
                        "message_mode": "string",
                        "message_text": "Alert from {source_name}",
                        "encoding": "utf-8",
                        "wait_for_response": True,
                        "response_timeout_seconds": 2,
                    },
                },
            )
            assert create_resp.status_code == 201, create_resp.text

            test_resp = await async_client.post(
                f"/api/notifications/instances/{create_resp.json()['id']}/test"
            )

            assert test_resp.status_code == 200, test_resp.text
            assert received.get(timeout=2) == b"Alert from Test Source"
            assert test_resp.json()["message"].endswith("response: ACK)")
            thread.join(timeout=2)
        finally:
            server.close()