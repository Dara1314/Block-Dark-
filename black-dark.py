#!/usr/bin/env python3
"""
DDoS Block Dark - Advanced DDoS Protection Tool
Founder: Dara Dav (imDara)
"""

import socket
import threading
import time
import json
import os
import sys
import logging
from datetime import datetime
from collections import defaultdict
import subprocess

# Dependencies check
try:
    from flask import Flask, request, jsonify, render_template_string
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# --- CONFIGURATION ---
LOG_FILE = 'ddos_block_dark.log'
BLOCKED_FILE = 'blocked_ips.json'
WHITELIST_FILE = 'whitelist.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("DDoSBlockDark")

class DDoSBlocker:
    def __init__(self):
        self.blocked_ips = set()
        self.whitelisted_ips = {'127.0.0.1', 'localhost'}
        self.request_counts = defaultdict(list)
        self.running = True
        
        # Security Thresholds
        self.rate_limit = 100   # Max requests per minute
        self.burst_limit = 20   # Max requests per second
        self.auto_block = True
        
        # Stats
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'start_time': time.time()
        }
        
        self.load_data()
        self.start_cleanup_thread()

    def load_data(self):
        if os.path.exists(BLOCKED_FILE):
            with open(BLOCKED_FILE, 'r') as f:
                self.blocked_ips = set(json.load(f))
        if os.path.exists(WHITELIST_FILE):
            with open(WHITELIST_FILE, 'r') as f:
                self.whitelisted_ips.update(json.load(f))

    def save_data(self):
        with open(BLOCKED_FILE, 'w') as f:
            json.dump(list(self.blocked_ips), f)
        with open(WHITELIST_FILE, 'w') as f:
            json.dump(list(self.whitelisted_ips), f)

    def block_ip(self, ip, reason="Anomalous Traffic"):
        if ip not in self.blocked_ips and ip not in self.whitelisted_ips:
            self.blocked_ips.add(ip)
            self.stats['blocked_requests'] += 1
            logger.warning(f"🔒 [BLOCKED] {ip} | Reason: {reason}")
            self.save_data()
            self.apply_system_firewall(ip)

    def apply_system_firewall(self, ip):
        try:
            if sys.platform == "win32":
                subprocess.run(f'netsh advfirewall firewall add rule name="DDoS_Block_{ip}" dir=in action=block remoteip={ip}', shell=True, capture_output=True)
            else:
                subprocess.run(['iptables', '-A', 'INPUT', '-s', ip, '-j', 'DROP'], capture_output=True)
        except Exception as e:
            logger.error(f"System block failed: {e}")

    def check_traffic(self, ip):
        if ip in self.blocked_ips: return False
        
        now = time.time()
        self.request_counts[ip] = [t for t in self.request_counts[ip] if now - t < 60]
        
        # Check Minute Limit
        if len(self.request_counts[ip]) >= self.rate_limit:
            self.block_ip(ip, "Rate Limit Exceeded")
            return False
            
        # Check Burst Limit (last 1 second)
        burst = [t for t in self.request_counts[ip] if now - t < 1]
        if len(burst) >= self.burst_limit:
            self.block_ip(ip, "Burst Attack Detected")
            return False

        self.request_counts[ip].append(now)
        self.stats['total_requests'] += 1
        return True

    def start_cleanup_thread(self):
        def clean():
            while self.running:
                time.sleep(300)
                now = time.time()
                for ip in list(self.request_counts.keys()):
                    if not self.request_counts[ip] or now - self.request_counts[ip][-1] > 300:
                        del self.request_counts[ip]
        threading.Thread(target=clean, daemon=True).start()

# --- WEB INTERFACE TEMPLATE ---
HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>DDoS Block Dark | Dashboard</title>
    <style>
        body { background: #0f0f13; color: #00f2ff; font-family: 'Courier New', monospace; padding: 40px; }
        .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(0, 242, 255, 0.2); border-radius: 15px; padding: 25px; }
        .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px; }
        .stat-box { text-align: center; border-left: 3px solid #00f2ff; }
        .btn-red { background: #ff4b2b; color: white; border: none; padding: 5px 10px; cursor: pointer; border-radius: 5px; }
        h1 { text-transform: uppercase; letter-spacing: 5px; text-shadow: 0 0 10px #00f2ff; }
        table { width: 100%; margin-top: 30px; border-collapse: collapse; }
        th, td { padding: 12px; border-bottom: 1px solid rgba(0, 242, 255, 0.1); text-align: left; }
    </style>
</head>
<body>
    <div class="glass">
        <h1>DDoS Block Dark</h1>
        <p>Founder: Dara Dav | System Status: <span style="color:#00ff88">PROTECTING</span></p>
        
        <div class="grid">
            <div class="stat-box"><h3>TOTAL REQ</h3><h2>{{ stats.total_requests }}</h2></div>
            <div class="stat-box"><h3>BLOCKED</h3><h2>{{ stats.blocked_requests }}</h2></div>
            <div class="stat-box"><h3>UPTIME</h3><h2>{{ uptime }}</h2></div>
        </div>

        <h3>Blocked IP Registry</h3>
        <table>
            <tr><th>IP Address</th><th>Status</th><th>Action</th></tr>
            {% for ip in blocked %}
            <tr>
                <td>{{ ip }}</td>
                <td style="color: #ff4b2b;">DROPPED</td>
                <td><form action="/unblock" method="post"><input type="hidden" name="ip" value="{{ip}}"><button class="btn-red">UNBLOCK</button></form></td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

# --- SERVER CORE ---
blocker = DDoSBlocker()
app = Flask(__name__)

@app.route('/')
def index():
    uptime = str(datetime.now() - datetime.fromtimestamp(blocker.stats['start_time'])).split('.')[0]
    return render_template_string(HTML_TPL, stats=blocker.stats, blocked=list(blocker.blocked_ips), uptime=uptime)

@app.route('/unblock', methods=['POST'])
def unblock():
    ip = request.form.get('ip')
    if ip in blocker.blocked_ips:
        blocker.blocked_ips.remove(ip)
        blocker.save_data()
    return """<script>window.location.href='/';</script>"""

def start_socket_node():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 8888))
    server.listen(100)
    logger.info("🛡️  Socket Protection Node Active on Port 8888")
    
    while True:
        client, addr = server.accept()
        if blocker.check_traffic(addr[0]):
            client.send(b"HTTP/1.1 200 OK\r\n\r\n[DDoS Block Dark] Connection Secure.")
        client.close()

if __name__ == "__main__":
    # Start Socket Listener
    threading.Thread(target=start_socket_node, daemon=True).start()
    
    # Start Web Dashboard
    print("\n🚀 DDoS Block Dark is running!")
    print("👉 Dashboard: http://127.0.0.1:5000")
    print("👉 Protection Port: 8888\n")
    
    if FLASK_AVAILABLE:
        app.run(port=5000, debug=False, use_reloader=False)
    else:
        print("Please install Flask for the Dashboard: pip install flask")
