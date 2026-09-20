"""WSL2 Port Proxy for Windows Host.
Forwards localhost:8000, localhost:5432, and localhost:6379 to WSL2 Docker container ports.
"""
import asyncio
import subprocess
import sys

def get_wsl_ip() -> str:
    try:
        out = subprocess.check_output(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"],
            text=True
        )
        return out.split()[0]
    except Exception as e:
        print(f"Error getting WSL IP: {e}")
        return "172.22.9.130"

async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

def create_proxy_handler(target_host: str, target_port: int):
    async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
        try:
            remote_reader, remote_writer = await asyncio.open_connection(target_host, target_port)
        except Exception as e:
            client_writer.close()
            return

        asyncio.create_task(pipe(client_reader, remote_writer))
        asyncio.create_task(pipe(remote_reader, client_writer))

    return handle_client

async def main():
    wsl_ip = get_wsl_ip()
    print(f"[WSL Proxy] Target WSL IP: {wsl_ip}")

    ports = [8000, 5432, 6379]
    servers = []
    for port in ports:
        try:
            handler = create_proxy_handler(wsl_ip, port)
            server = await asyncio.start_server(handler, "127.0.0.1", port)
            servers.append(server)
            print(f"[WSL Proxy] Forwarding 127.0.0.1:{port} -> {wsl_ip}:{port}")
        except Exception as e:
            print(f"[WSL Proxy] Could not bind 127.0.0.1:{port}: {e}")

    if not servers:
        print("[WSL Proxy] No servers started, exiting.")
        return

    print("[WSL Proxy] Running. Press Ctrl+C to stop.")
    await asyncio.gather(*(server.serve_forever() for server in servers))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
