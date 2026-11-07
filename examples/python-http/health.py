"""A real Ubuntu HTTP probe for the bundled localtest smoke server."""
import os
import urllib.request

port = int(os.environ["PORT"])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(f"http://127.0.0.1:{port}/hello.txt", timeout=10) as response:
    body = response.read().decode().strip()
    if response.status != 200 or not body:
        raise SystemExit("Smoke endpoint is not ready")
    print(f"HTTP {response.status}: {body}")
