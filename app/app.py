
from flask import Flask, jsonify
import os
import socket
from datetime import datetime

app = Flask(__name__)

VERSION = os.getenv("VERSION", "1.0")
PORT = int(os.getenv("APP_PORT", "5001"))
HEALTHY = os.getenv("HEALTHY", "true").lower() == "true"

request_count = 0


@app.before_request
def count_requests():
    global request_count
    request_count += 1


@app.route("/")
def home():
    return f"""
    <html>
    <head>
        <title>ZeroDowntime Application</title>
        <style>
            body {{
                font-family: Arial;
                text-align: center;
                padding: 60px;
                background: #f3f4f6;
            }}
            .card {{
                background: white;
                padding: 35px;
                border-radius: 15px;
                max-width: 500px;
                margin: auto;
                box-shadow: 0 3px 15px #ddd;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>ZeroDowntime Demo</h1>
            <h2>Application Version {VERSION}</h2>
            <p>Application is running successfully!</p>
            <p>Container: {socket.gethostname()}</p>
            <p>Requests served: {request_count}</p>
        </div>
    </body>
    </html>
    """


@app.route("/health")
def health():
    if not HEALTHY:
        return jsonify({
            "status": "unhealthy",
            "version": VERSION
        }), 503

    return jsonify({
        "status": "healthy",
        "version": VERSION
    })


@app.route("/api/info")
def info():
    return jsonify({
        "version": VERSION,
        "container": socket.gethostname(),
        "requests": request_count,
        "status": "healthy" if HEALTHY else "unhealthy",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
