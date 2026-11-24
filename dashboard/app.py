
from flask import Flask, jsonify, render_template_string
from functools import wraps
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError
import subprocess
import time
import json
import threading

app = Flask(__name__)

ROOT = Path(__file__).resolve().parent.parent
NGINX_CONFIG = ROOT / "nginx" / "default.conf"
ENV_FILE = ROOT / ".env"
ACTIVE_FILE = ROOT / "active.txt"
PREVIOUS_FILE = ROOT / "previous.txt"
AUTO_LOG_FILE = ROOT / "auto_rollback.log"
HISTORY_FILE = ROOT / "deployment_history.json"
DEPLOYMENT_LOCK = threading.Lock()


def exclusive_operation(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not DEPLOYMENT_LOCK.acquire(blocking=False):
            return jsonify({
                "status": "busy",
                "message": "Another deployment operation is in progress."
            }), 409
        try:
            return func(*args, **kwargs)
        finally:
            DEPLOYMENT_LOCK.release()

    return wrapper


if not ACTIVE_FILE.exists():
    ACTIVE_FILE.write_text("blue")


def run_compose(*args):
    try:
        return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90
    )

    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "Docker operation timed out.")


def log_event(event, environment, status, message, duration=None):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except Exception:
            history = []

    history.insert(0, {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": event,
        "environment": environment,
        "status": status,
        "message": message,
        "duration": duration
    })
    temp = HISTORY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(history[:100], indent=4))
    temp.replace(HISTORY_FILE)


def check_health(color):
    port = 5001 if color == "blue" else 5002
    url = f"http://127.0.0.1:{port}/health"

    for _ in range(10):
        try:
            with urlopen(url, timeout=2) as response:
                data = json.loads(response.read().decode())

                if data.get("status") == "healthy":
                    return True

        except Exception:
            pass

        time.sleep(1)

    return False


def make_nginx_config(color):
    port = 5001 if color == "blue" else 5002

    return f"""
server {{
    listen 80;

    location / {{
        proxy_pass http://{color}:{port};

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""


def activate_version(color):
    old_config = NGINX_CONFIG.read_text()

    NGINX_CONFIG.write_text(make_nginx_config(color))

    test = run_compose("exec", "-T", "nginx", "nginx", "-t")

    if test.returncode != 0:
        NGINX_CONFIG.write_text(old_config)
        return False, "Nginx configuration test failed."

    reload_result = run_compose(
        "exec", "-T", "nginx", "nginx", "-s", "reload"
    )

    if reload_result.returncode != 0:
        NGINX_CONFIG.write_text(old_config)
        run_compose("exec", "-T", "nginx", "nginx", "-s", "reload")
        return False, "Nginx reload failed."

    return True, "Traffic switched successfully."


def deploy(color, event="Deployment"):
    started = time.monotonic()
    def finish(success, message):
        log_event(event, color, "Success" if success else "Failed", message, round(time.monotonic() - started, 2))
        return success, message
    if color not in ("blue", "green"):
        return finish(False, "Invalid environment.")
    current = ACTIVE_FILE.read_text().strip()
    if current == color:
        return True, f"{color.upper()} is already active. No switch needed."
    start = run_compose("up", "-d", color)
    if start.returncode != 0:
        return finish(False, start.stderr[-1000:])
    if not check_health(color):
        return finish(False, f"{color.upper()} failed its health check. Existing traffic was not switched.")
    success, message = activate_version(color)
    if not success:
        return finish(False, message)
    PREVIOUS_FILE.write_text(current)
    ACTIVE_FILE.write_text(color)
    return finish(True, message)


def monitor_active_environment():
    failures = 0
    last_active = None

    while True:
        if not DEPLOYMENT_LOCK.acquire(blocking=False):
            time.sleep(5)
            continue
        try:
            active = ACTIVE_FILE.read_text().strip()

            if active != last_active:
                failures = 0
                last_active = active

            port = 5001 if active == "blue" else 5002

            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/health",
                    timeout=3
                ) as response:
                    data = json.loads(response.read().decode())

                    if response.status == 200 and data.get("status") == "healthy":
                        failures = 0
                    else:
                        failures += 1

            except Exception:
                failures += 1

            if failures >= 3:
                if PREVIOUS_FILE.exists():
                    previous = PREVIOUS_FILE.read_text().strip()

                    if previous != active and check_health(previous):
                        success, message = activate_version(previous)

                        if success:
                            PREVIOUS_FILE.write_text(active)
                            ACTIVE_FILE.write_text(previous)
                            log_event(
                                "Automatic Rollback",
                                previous,
                                "Success",
                                f"Unhealthy {active} environment automatically replaced by {previous}."
                            )

                            AUTO_LOG_FILE.write_text(
                                f"Automatic rollback: {active} -> {previous}\n"
                            )

                            last_active = previous

                failures = 0

        except Exception as error:
            print("Monitoring error:", error)

        finally:
            DEPLOYMENT_LOCK.release()

        time.sleep(5)


@app.route("/")
def dashboard():
    return render_template_string(PAGE)


@app.route("/api/state")
def state():
    active = ACTIVE_FILE.read_text().strip()

    try:
        previous = PREVIOUS_FILE.read_text().strip()
    except FileNotFoundError:
        previous = "None"

    try:
        with urlopen("http://127.0.0.1:8080/api/info", timeout=3) as response:
            live_info = json.loads(response.read().decode())
    except Exception:
        live_info = {"status": "Application unavailable"}

    return jsonify({
        "active": active,
        "previous": previous,
        "version": "1.0" if active == "blue" else "2.0",
        "live_info": live_info
    })


@app.route("/api/deploy", methods=["POST"])
@exclusive_operation
def deploy_green():
    success, message = deploy("green")

    return jsonify({
        "success": success,
        "message": message
    }), 200 if success else 400


@app.route("/api/rollback", methods=["POST"])
@exclusive_operation
def rollback():
    if not PREVIOUS_FILE.exists():
        return jsonify({
            "success": False,
            "message": "No previous deployment is available."
        }), 400

    previous = PREVIOUS_FILE.read_text().strip()

    success, message = deploy(previous, "Manual Rollback")

    return jsonify({
        "success": success,
        "message": "Rollback completed. " + message
        if success else message
    }), 200 if success else 400


@app.route("/api/failure", methods=["POST"])
@exclusive_operation
def simulate_failure():
    started = time.monotonic()
    ENV_FILE.write_text(
        "BLUE_HEALTHY=true\nGREEN_HEALTHY=false\n"
    )

    result = run_compose(
        "up", "-d", "--force-recreate", "green"
    )

    if result.returncode != 0:
        log_event("Failure Simulation", "green", "Failed", result.stderr[-1000:], round(time.monotonic()-started, 2))
        return jsonify({
            "success": False,
            "message": result.stderr[-1000:]
        }), 500

    log_event("Failure Simulation", "green", "Success", "Green failure injected.", round(time.monotonic()-started, 2))
    return jsonify({
        "success": True,
        "message": "Green application recreated in unhealthy mode."
    })


@app.route("/api/restore", methods=["POST"])
@exclusive_operation
def restore_green():
    started = time.monotonic()
    if ACTIVE_FILE.read_text().strip() == "green":
        return jsonify({"success": False, "message": "Switch to Blue before recreating Green."}), 409
    ENV_FILE.write_text(
        "BLUE_HEALTHY=true\nGREEN_HEALTHY=true\n"
    )

    result = run_compose(
        "up", "-d", "--force-recreate", "green"
    )

    if result.returncode != 0:
        log_event("Restore Green", "green", "Failed", result.stderr[-1000:], round(time.monotonic()-started, 2))
        return jsonify({
            "success": False,
            "message": result.stderr[-1000:]
        }), 500

    if not check_health("green"):
        log_event("Restore Green", "green", "Failed", "Green is still unhealthy.", round(time.monotonic()-started, 2))
        return jsonify({
            "success": False,
            "message": "Green is still unhealthy."
        }), 500

    log_event("Restore Green", "green", "Success", "Green restored.", round(time.monotonic()-started, 2))
    return jsonify({
        "success": True,
        "message": "Green is healthy again."
    })


@app.route("/api/test-request", methods=["POST"])
def test_request():
    try:
        with urlopen("http://127.0.0.1:8080/api/info", timeout=3) as response:
            data = json.loads(response.read().decode())

        return jsonify({
            "success": True,
            "data": data
        })

    except Exception as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 500


@app.route("/api/history")
def deployment_history():
    if not HISTORY_FILE.exists():
        return jsonify([])

    try:
        history = json.loads(HISTORY_FILE.read_text())
        return jsonify(history)
    except Exception:
        return jsonify({
            "error": "Unable to read deployment history."
        }), 500


PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>ZeroDowntime Dashboard</title>

<style>
body {
    font-family: Arial, sans-serif;
    background: linear-gradient(135deg, #0b1220, #17263e);
    color: white;
    padding: 30px;
    margin: 0;
}

.container {
    max-width: 1100px;
    margin: auto;
}

h1 {
    color: #60a5fa;
}

.card {
    background: #1e293b;
    padding: 22px;
    border-radius: 12px;
    margin: 18px 0;
    border: 1px solid #334155;
    box-shadow: 0 8px 24px #0002;
}

.status {
    font-size: 25px;
    font-weight: bold;
    color: #4ade80;
}

button {
    padding: 13px 18px;
    margin: 7px 5px 7px 0;
    border: none;
    border-radius: 7px;
    cursor: pointer;
    font-weight: bold;
    background: #2563eb;
    color: white;
}

button:disabled { opacity: .45; cursor: wait; }
button:hover {
    opacity: 0.8;
}

.danger {
    background: #dc2626;
}

.success {
    background: #16a34a;
}

pre {
    background: #0f172a;
    padding: 15px;
    border-radius: 8px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

iframe {
    width: 100%;
    height: 400px;
    border: 1px solid #475569;
    border-radius: 8px;
    background: white;
}

.small {
    color: #94a3b8;
    font-size: 13px;
}
</style>
</head>

<body>
<div class="container">

<h1>ZERO DOWNTIME</h1>
<p class="small">Blue-Green Deployment & Automated Rollback System</p>

<div class="card">
    <h2>Deployment Status</h2>
    <p>Active Environment: <span class="status" id="active">Loading...</span></p>
    <p>Previous Environment: <span id="previous">Loading...</span></p>
    <p>Application Version: <span id="version">Loading...</span></p>
    <button onclick="refresh()">Refresh Status</button>
</div>

<div class="card">
    <h2>Deployment Controls</h2>

    <button class="success" onclick="action('/api/deploy')">
        Deploy Version 2
    </button>

    <button onclick="action('/api/rollback')">
        Rollback
    </button>

    <button class="danger" onclick="action('/api/failure')">
        Simulate Green Failure
    </button>

    <button onclick="action('/api/restore')">
        Restore Green
    </button>

    <button onclick="action('/api/test-request')">
        Send Test Request
    </button>
</div>

<div class="card">
    <h2>Live Application</h2>
    <iframe id="live-frame" src="http://localhost:8080"></iframe>
</div>

<div class="card">
    <h2>Deployment Activity</h2>
    <pre id="log">Ready to deploy.</pre>
</div>

<div class="card">
    <h2>Deployment History</h2>
    <div id="history">Loading history...</div>
</div>

<div class="card">
    <h2>Live Request Information</h2>
    <pre id="info">Waiting for requests...</pre>
</div>

</div>

<script>

async function refresh() {
    try {
        const response = await fetch('/api/state');
        const data = await response.json();

        document.getElementById('active').innerText =
            data.active.toUpperCase();

        document.getElementById('previous').innerText =
            data.previous;

        document.getElementById('version').innerText =
            data.live_info.version ?? data.version;
        document.getElementById('active').style.color = data.active === "blue" ? "#60a5fa" : "#4ade80";

        document.getElementById('info').innerText =
            JSON.stringify(data.live_info, null, 2);

    } catch (error) {
        log('Unable to refresh status: ' + error);
    }

    await loadHistory();
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        if (!response.ok) {
            throw new Error('History request failed.');
        }

        const history = await response.json();
        if (!Array.isArray(history)) {
            throw new Error('Invalid history response.');
        }

        const container = document.getElementById('history');
        container.replaceChildren();

        if (!history.length) {
            const emptyMessage = document.createElement('p');
            emptyMessage.textContent = 'No deployment history yet.';
            container.appendChild(emptyMessage);
            return;
        }

        history.forEach(item => {
            const entry = document.createElement('div');
            entry.style.cssText =
                'background:#0f172a;padding:14px;margin:10px 0;' +
                'border-radius:8px;border-left:4px solid ' +
                (item.status === 'Success' ? '#4ade80' : '#ef4444');

            const heading = document.createElement('strong');
            heading.textContent = String(item.event ?? '');

            const status = document.createElement('span');
            status.style.float = 'right';
            status.textContent = String(item.status ?? '');

            const environment = document.createElement('p');
            environment.textContent =
                `Environment: ${String(item.environment ?? '').toUpperCase()}`;

            const message = document.createElement('p');
            message.textContent = String(item.message ?? '');

            const timestamp = document.createElement('small');
            timestamp.textContent = String(item.timestamp ?? '') + (item.duration != null ? ` | ${item.duration} s` : '');

            entry.append(heading, status, environment, message, timestamp);
            container.appendChild(entry);
        });

    } catch (error) {
        document.getElementById('history').innerText =
            'Unable to load deployment history.';
    }
}

let busy = false;
async function action(endpoint) {
    if (busy) return;
    busy = true;
    const buttons = document.querySelectorAll("button");
    buttons.forEach(b => b.disabled = true);
    log('Processing request: ' + endpoint);

    try {
        const response = await fetch(endpoint, {
            method: 'POST'
        });

        const data = await response.json();

        log(data.message || JSON.stringify(data));

        if (data.data) {
            document.getElementById('info').innerText =
                JSON.stringify(data.data, null, 2);
        }

        await refresh();
        document.getElementById("live-frame").src = "http://localhost:8080";

    } catch (error) {
        log('Error: ' + error);
    } finally {
        busy = false;
        buttons.forEach(b => b.disabled = false);
    }
}

function log(message) {
    const time = new Date().toLocaleTimeString();
    const element = document.getElementById('log');

    element.innerText =
        '[' + time + '] ' + message + '\\n' +
        element.innerText;

    localStorage.setItem('deploymentActivity', element.innerText);
}

document.getElementById('log').innerText =
    localStorage.getItem('deploymentActivity') ||
    'Ready to deploy.';

refresh();
setInterval(refresh, 5000);

</script>

</body>
</html>
"""


if __name__ == "__main__":
    monitor = threading.Thread(
        target=monitor_active_environment,
        daemon=True
    )
    monitor.start()
    app.run(host="127.0.0.1", port=5050, debug=False)
