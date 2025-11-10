#!/usr/bin/env python3
"""
monitor.py
Automated log analysis, attack detection, WhatsApp alerting, and mitigation.
"""

import re
import os
import sys
import json
import time
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import requests

# ---------------------------
# CONFIG (keys & API endpoints)
# ---------------------------
GEMINI_API_KEY = "AIzaSyCleGyLzyLB4Ni08RiqJo3bq6E789pGWM4"    # <-- API key Gemini
FONNTE_TOKEN = "R3JmjUG5sAmGbSEE7gcG"                         # <-- Fonnte token
FONNTE_DEVICE = "6281933976553"                               # <-- nomor WA tujuan
FONNTE_WEBHOOK_URL = "https://api.fonnte.com/send"            # <-- endpoint Fonnte

# Paths
APACHE_ACCESS_LOG = "/var/log/apache2/access.log"
AUTH_LOG = "/var/log/auth.log"

# detection thresholds
BRUTE_FORCE_THRESHOLD = 5
BRUTE_FORCE_WINDOW_MIN = 60 * 60
BLOCK_COMMAND = "ufw deny from {ip} to any"

# patterns
SQLI_KEYWORDS = re.compile(r"\b(union|select|insert|update|delete|drop|--|#|;)\b", re.I)
XSS_KEYWORDS = re.compile(r"(<script|%3Cscript|onerror=|onload=|alert\()", re.I)
SCANNER_AGENTS = re.compile(r"(sqlmap|nikto|curl|masscan|nmap|acunetix|dirbuster)", re.I)

# ---------------------------
# Utility functions
# ---------------------------
def tail_read(path, num_lines=10000):
    """Read last num_lines lines from a file efficiently."""
    if not os.path.exists(path):
        return []
    with open(path, "r", errors="ignore") as f:
        try:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 1024
            data = ""
            while size > 0 and data.count("\n") < num_lines:
                size -= block
                if size < 0:
                    block += size
                    size = 0
                    f.seek(0)
                else:
                    f.seek(size)
                data = f.read() + data
            return data.splitlines()[-num_lines:]
        except Exception:
            f.seek(0)
            return f.read().splitlines()[-num_lines:]

def parse_apache_line(line):
    try:
        parts = line.split('"')
        pre = parts[0].strip()
        req = parts[1]
        ua = parts[-1].strip()
        ip = pre.split()[0]
        status = int(parts[2].strip().split()[0])
        method, url, proto = req.split()
        return {"ip": ip, "method": method, "url": url, "status": status, "ua": ua, "raw": line}
    except Exception:
        return None

# ---------------------------
# Detection logic
# ---------------------------
def analyze_access_log(lines):
    ips = Counter()
    urls = Counter()
    status_codes = Counter()
    uas = Counter()
    sqli_hits, xss_hits, scanner_hits = [], [], []

    for ln in lines:
        parsed = parse_apache_line(ln)
        if not parsed:
            continue
        ip = parsed["ip"]
        url = parsed["url"]
        status = parsed["status"]
        ua = parsed["ua"]

        ips[ip] += 1
        urls[url] += 1
        status_codes[status] += 1
        uas[ua] += 1

        if SQLI_KEYWORDS.search(url) or SQLI_KEYWORDS.search(ln):
            sqli_hits.append({"ip": ip, "url": url})
        if XSS_KEYWORDS.search(url) or XSS_KEYWORDS.search(ln):
            xss_hits.append({"ip": ip, "url": url})
        if SCANNER_AGENTS.search(ua):
            scanner_hits.append({"ip": ip, "ua": ua})

    return {
        "top_ips": ips.most_common(10),
        "top_urls": urls.most_common(10),
        "status_codes": status_codes.most_common(),
        "user_agents": uas.most_common(10),
        "sqli": sqli_hits,
        "xss": xss_hits,
        "scanners": scanner_hits
    }

def analyze_auth_log(lines):
    failed = defaultdict(list)
    for ln in lines:
        if "Failed password" in ln or "authentication failure" in ln:
            m = re.search(r"from\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", ln)
            if m:
                ip = m.group(1)
                failed[ip].append(ln)
    suspects = [{"ip": ip, "count": len(v)} for ip, v in failed.items() if len(v) >= BRUTE_FORCE_THRESHOLD]
    return {"failed_counts": {ip: len(v) for ip, v in failed.items()}, "suspects": suspects}

# ---------------------------
# Mitigation
# ---------------------------
def block_ip(ip):
    cmd = BLOCK_COMMAND.format(ip=ip)
    try:
        subprocess.run(cmd.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, f"Blocked {ip} via UFW"
    except subprocess.CalledProcessError as e:
        return False, f"Block failed {ip}: {e.stderr.decode()}"

# ---------------------------
# WhatsApp notification
# ---------------------------
def send_whatsapp(message, to=FONNTE_DEVICE):
    """
    Send message via Fonnte API.
    Docs: https://fonnte.com/docs
    """
    headers = {
        "Authorization": f"Bearer {FONNTE_TOKEN}",
    }
    data = {
        "target": str(to),
        "message": message
    }
    try:
        resp = requests.post(FONNTE_WEBHOOK_URL, headers=headers, data=data, timeout=15)
        log_line_
