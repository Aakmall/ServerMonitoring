#!/usr/bin/env python3
"""
monitor.py
Automated log analysis, attack detection, whatsapp alerting, basic mitigation.
"""

import re
import os
import sys
import json
import time
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# ---------------------------
# CONFIG (sesuai permintaan: keys ada di sini)
# ---------------------------
GEMINI_API_KEY = "AIzaSyCleGyLzyLB4Ni08RiqJo3bq6E789pGWM4"   # <-- API key Gemini (user provided)
FONNTE_TOKEN = "R3JmjUG5sAmGbSEE7gcG"                      # <-- Fonnte token (user provided)
FONNTE_DEVICE = "YOUR_DEVICE_NUMBER_OR_ID"                  # <-- ganti dengan nomor device (contoh: "62812xxxx")
FONNTE_WEBHOOK_URL = "https://api.fonnte.example/send"      # <-- ganti dengan Webhook/endpoint Fonnte yang benar

# Paths
APACHE_ACCESS_LOG = "/var/log/apache2/access.log"
AUTH_LOG = "/var/log/auth.log"

# detection thresholds
BRUTE_FORCE_THRESHOLD = 5         # gagal login 5 kali -> dianggap bruteforce
BRUTE_FORCE_WINDOW_MIN = 60 * 60  # lihat 1 jam terakhir (deteksi)
BLOCK_COMMAND = "ufw deny from {ip} to any"  # perintah block (ubah jika mau iptables)

# patterns
SQLI_KEYWORDS = re.compile(r"\b(union|select|insert|update|delete|drop|--|#|;)\b", re.I)
XSS_KEYWORDS = re.compile(r"(<script|%3Cscript|onerror=|onload=|alert\()", re.I)
SCANNER_AGENTS = re.compile(r"(sqlmap|nikto|curl|masscan|nmap|acunetix|dirbuster)", re.I)

# ---------------------------
# Helpers
# ---------------------------
def tail_read(path, num_lines=10000):
    """Read last num_lines lines from file (efficientish)."""
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
    # simple combined log format parsing (best-effort)
    # example: 1.2.3.4 - - [10/Nov/2025:12:34:56 +0000] "GET /index.php?q=1 HTTP/1.1" 200 123 "-" "User-Agent"
    try:
        parts = line.split('"')
        pre = parts[0].strip()
        req = parts[1]
        ua = parts[-1].strip()
        # ip is first token of pre
        ip = pre.split()[0]
        status = int(parts[2].strip().split()[0])
        method, url, proto = req.split()
        return {"ip": ip, "method": method, "url": url, "status": status, "ua": ua, "raw": line}
    except Exception:
        return None

def parse_auth_line(line):
    return line  # we will regex-match for "Failed password" etc.

# ---------------------------
# Detection logic
# ---------------------------
def analyze_access_log(lines):
    ips = Counter()
    urls = Counter()
    status_codes = Counter()
    uas = Counter()
    sqli_hits = []
    xss_hits = []
    scanner_hits = []

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
            sqli_hits.append({"ip": ip, "url": url, "line": ln})
        if XSS_KEYWORDS.search(url) or XSS_KEYWORDS.search(ln):
            xss_hits.append({"ip": ip, "url": url, "line": ln})
        if SCANNER_AGENTS.search(ua):
            scanner_hits.append({"ip": ip, "ua": ua, "line": ln})

    return {
        "top_ips": ips.most_common(10),
        "top_urls": urls.most_common(10),
        "status_codes": status_codes.most_common(),
        "user_agents": uas.most_common(10),
        "sqli": sqli_hits,
        "xss": xss_hits,
        "scanners": scanner_hits
    }

def analyze_auth_log(lines, window_sec=BRUTE_FORCE_WINDOW_MIN):
    # find "Failed password" entries and count per IP within window
    now = datetime.utcnow()
    failed = defaultdict(list)
    for ln in lines:
        if "Failed password" in ln or "authentication failure" in ln:
            # try to extract timestamp and ip
            # auth.log often: "Nov 10 08:12:34 server sshd[1234]: Failed password for invalid user root from 1.2.3.4 port 34567 ssh2"
            m = re.search(r"from\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", ln)
            if m:
                ip = m.group(1)
                # no exact timestamp parsing (various formats) -> just append
                failed[ip].append(ln)
    # evaluate threshold
    suspects = []
    for ip, entries in failed.items():
        if len(entries) >= BRUTE_FORCE_THRESHOLD:
            suspects.append({"ip": ip, "count": len(entries), "lines": entries[:10]})
    return {"failed_counts": {ip: len(entries) for ip,entries in failed.items()}, "suspects": suspects}

# ---------------------------
# Mitigation
# ---------------------------
def block_ip(ip):
    """Try to block IP using UFW (requires sudo). Return (ok, msg)."""
    cmd = BLOCK_COMMAND.format(ip=ip)
    try:
        subprocess.run(cmd.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, f"Blocked {ip} with: {cmd}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to block {ip}: {e.stderr.decode().strip()}"

# ---------------------------
# Notifier: Fonnte (WhatsApp)
# ---------------------------
def send_whatsapp(message, to=FONNTE_DEVICE):
    """
    Example: POST JSON to Fonnte webhook. The real API might differ.
    Replace FONNTE_WEBHOOK_URL, TOKEN, payload format according to Fonnte docs.
    """
    import requests
    headers = {
        "Authorization": f"Bearer {FONNTE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": str(to),
        "type": "text",
        "message": message
    }
    try:
        resp = requests.post(FONNTE_WEBHOOK_URL, headers=headers, json=payload, timeout=15)
        return resp.status_code, resp.text
    except Exception as e:
        return None, str(e)

# ---------------------------
# (Optional) LLM analysis placeholder: Gemini
# ---------------------------
def ask_gemini(prompt):
    """
    Placeholder usage of Gemini API key. Replace with actual Google Cloud / MakerSuite
    calls per the up-to-date Gemini API spec.
    """
    # Minimal example: we won't call in real if key or endpoint incompatible.
    return "LLM_ANALYSIS_PLACEHOLDER: " + (prompt[:400] + "...")

# ---------------------------
# Main
# ---------------------------
def build_report(access_summary, auth_summary):
    t = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    report = []
    report.append(f"Monitoring Report - {t}")
    report.append("Top IPs:")
    for ip,c in access_summary["top_ips"][:10]:
        report.append(f" - {ip}: {c} requests")
    report.append("Top URLs:")
    for u,c in access_summary["top_urls"][:10]:
        report.append(f" - {u}: {c}")
    report.append("Status codes summary:")
    for sc,c in access_summary["status_codes"][:10]:
        report.append(f" - {sc}: {c}")
    report.append("Detected SQLi attempts: " + str(len(access_summary["sqli"])))
    report.append("Detected XSS attempts: " + str(len(access_summary["xss"])))
    report.append("Detected scanner UAs: " + str(len(access_summary["scanners"])))
    report.append("Suspected brute-force (>= {0} fails): {1}".format(BRUTE_FORCE_THRESHOLD, len(auth_summary["suspects"])))
    return "\n".join(report)

def main():
    # read logs
    access_lines = tail_read(APACHE_ACCESS_LOG, 5000)
    auth_lines = tail_read(AUTH_LOG, 5000)

    access_summary = analyze_access_log(access_lines)
    auth_summary = analyze_auth_log(auth_lines)

    report = build_report(access_summary, auth_summary)
    print(report)

    # If suspect brute-force, block and alert
    alerts = []
    for s in auth_summary["suspects"]:
        ip = s["ip"]
        ok, msg = block_ip(ip)
        alerts.append({"ip": ip, "blocked": ok, "msg": msg})

    # If any sqli/xss/scanner detected, prepare detail
    if access_summary["sqli"] or access_summary["xss"] or access_summary["scanners"]:
        alerts.append({"sqli": len(access_summary["sqli"]), "xss": len(access_summary["xss"]), "scanners": len(access_summary["scanners"])})

    # Send whatsapp message with summary
    # cut message length if necessary
    message = report + "\n\nAlerts:\n" + json.dumps(alerts, indent=2)[:3000]
    status, resp = send_whatsapp(message)
    print("WhatsApp send status:", status, resp)

    # Optionally ask LLM for smart recommendations
    llm_prompt = "Analyze this security summary and provide 5 action recommendations:\n\n" + report
    llm_result = ask_gemini(llm_prompt)
    print("LLM result (placeholder):", llm_result)

if __name__ == "__main__":
    main()
