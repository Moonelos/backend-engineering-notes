"""Verify a local Docker image's health state and bounded shutdown without shared state."""
import concurrent.futures
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def wait_until(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.1)
    raise AssertionError("condition not observed before deadline")


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "notes-lifecycle:lab"
    name = "notes-lifecycle-" + uuid.uuid4().hex[:12]
    docker("run", "-d", "--name", name, "-p", "127.0.0.1::8000", image)
    try:
        image_id = docker("inspect", "-f", "{{.Image}}", name)
        port = docker("port", name, "8000/tcp").rsplit(":", 1)[1]
        base = "http://127.0.0.1:" + port

        def status(path):
            try:
                with urllib.request.urlopen(base + path, timeout=8) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)

        wait_until(lambda: docker("inspect", "-f", "{{.State.Health.Status}}", name) == "healthy")
        assert docker("exec", name, "id", "-u") == "10001"
        assert status("/health")[0] == status("/ready")[0] == 200
        docker("exec", name, "touch", "/tmp/fail-ready")
        assert status("/ready")[0] == 503 and status("/health")[0] == 200
        docker("exec", name, "touch", "/tmp/fail-health")
        wait_until(lambda: docker("inspect", "-f", "{{.State.Health.Status}}", name) == "unhealthy")
        assert docker("inspect", "-f", "{{.State.Running}}", name) == "true"
        assert docker("inspect", "-f", "{{.RestartCount}}", name) == "0"
        docker("exec", name, "rm", "/tmp/fail-health", "/tmp/fail-ready")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            pending = executor.submit(status, "/slow?seconds=3")
            wait_until(lambda: "slow request started" in docker("logs", name))
            started = time.monotonic()
            docker("stop", "--time", "12", name)
            assert pending.result() == (200, {"state": "complete"})
            elapsed = time.monotonic() - started
        assert elapsed < 12
        state = json.loads(docker("inspect", name))[0]["State"]
        assert state["ExitCode"] == 0, state
        assert "cleanup complete" in docker("logs", name)
        print("image", image_id)
        print("PASS non-root uid=10001; ready=503 while health=200")
        print("PASS unhealthy stays running; restart count=0")
        print("PASS in-flight response=200; cleanup complete; exit=0; stop under 12s")
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
