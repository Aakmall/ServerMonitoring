#!/usr/bin/env python3
# monitor.py -- Apache log analysis + simple attack detection + Gemini summarization + Fonnte WhatsApp alert

import os
import re
import json
import time
import requests
from collections import Counter, defaultdict
from datetime import datetime, timedelta
# optional: from apache_log_parser import make_parser  # if installed

# CONFIG (ubah di Jenkins credentials / env)
APACHE_ACCESS_LOG = os.environ.get("APACHE_ACCESS_LOG", "/var/log/apache2/access.log")
APACHE_ERROR_LOG  = os.environ.get("APACHE_ERROR_LOG", "/var/log/apache2/error.log")
AUTH_LOG = os.environ.get("AUTH_LOG", "/var/log/auth.log")

# External services - ambil dari env vars (set di Jenkins Credentials)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")           # simpan sebagai Secret Text
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
FONNTE_TOKEN = os.environ.get("FONNTE_TOKEN")               # simpan sebagai Secret Text
FONNTE_ENDPOINT = os.environ.get("FONNTE_ENDPOINT", "https://api.fonnte.com/send")
ALERT_TARGET_NUMBER = os.environ.get("ALERT_TARGET_NUMBER", "")  # e.g. 62812xxxx (without +)

# detection patterns (simple, extendable)
SQLI_PATTERNS = re.compile(r"\b(union\b|select\b|drop\b|insert\b|update\b|concat\(|information_schema|benchmark\(|sleep\()",
                          re.IGNORECASE)
XSS_PATTERNS = re.compile(r"(<script\b|alert\s*\(|onerror=|onload=|javascript:)", re.IGNORECASE)
SCANNER_UA = re.compile(r"(sqlmap|nikto|masscan|nmap|zgrab|acunetix)", re.IGNORECASE)
IP_LINE_RE = re.compile(r'^(\S+)')  # simple: first token is remote IP

# Read last-N-lines since last run: use state file
STATE_FILE = "/var/tmp/monitor_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"access_pos": 0, "auth_pos":0, "access_mtime":0}
def save_state(st):
    json.dump(st, open(STATE_FILE, "w"))

def tail_from(path, start_pos):
    """Return (lines, end_pos). Uses file offset to resume."""
    if not os.path.exists(path):
        return [], start_pos
    with open(path, "rb") as f:
        f.seek(start_pos)
        data = f.read().decode(errors="replace")
        end_pos = f.tell()
    lines = data.splitlines()
    return lines, end_pos

def analyze_access_lines(lines):
    ip_counter = Counter()
    url_counter = Counter()
    status_counter = Counter()
    ua_counter = Counter()
    sqli_ips, xss_ips, scanner_ips = set(), set(), set()

    for line in lines:
        # Simple parsing: assume combined log format
        parts = line.split()
        if len(parts) < 9:
            continue
        ip = parts[0]
        # request is between quotes, naive:
        mreq = re.search(r'\"(GET|POST|HEAD|PUT|DELETE|OPTIONS) ([^"]+) HTTP/[\d\.]+\"', line)
        url = mreq.group(2) if mreq else "-"
        status = parts[-2] if len(parts)>=2 else "-"
        ua_match = re.search(r'\"[^\"]*\" \"([^\"]+)\"$', line)
        ua = ua_match.group(1) if ua_match else "-"

        ip_counter[ip]+=1
        url_counter[url]+=1
        status_counter[status]+=1
        ua_counter[ua]+=1

        if SQLI_PATTERNS.search(line):
            sqli_ips.add(ip)
        if XSS_PATTERNS.search(line):
            xss_ips.add(ip)
        if SCANNER_UA.search(ua):
            scanner_ips.add(ip)

    return {
        "top_ips": ip_counter.most_common(10),
        "top_urls": url_counter.most_common(10),
        "status_counts": dict(status_counter),
        "top_uas": ua_counter.most_common(10),
        "sqli_ips": list(sqli_ips),
        "xss_ips": list(xss_ips),
        "scanner_ips": list(scanner_ips)
    }

def analyze_auth_lines(lines):
    # detect failed password attempts and mapping ip -> count
    failed = Counter()
    for line in lines:
        if "Failed password" in line or "invalid user" in line:
            m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
            if m:
                failed[m.group(1)] += 1
    return failed

def send_fonnte_message(target_number, message):
    if not FONNTE_TOKEN:
        print("Fonnte token not configured; skipping WhatsApp send.")
        return False
    payload = {
        "target": target_number,
        "message": message
    }
    headers = {"Authorization": f"Bearer {FONNTE_TOKEN}"}
    try:
        r = requests.post(FONNTE_ENDPOINT, data=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print("Fonnte send failed:", e)
        return False

def summarize_with_gemini(prompt_text):
    if not GEMINI_API_KEY:
        return "Gemini API key not configured."
    # Simple REST call to Vertex-AI generateContent (example). Adjust based on official SDK
    url = "https://us-central1-aiplatform.googleapis.com/v1/projects/YOUR_PROJECT/locations/global/models/{}/:predict".format(GEMINI_MODEL)
    # NOTE: better to use official client libs or adjust endpoint/project. This is a placeholder example.
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type":"application/json"}
    body = {
        "instances": [{"content": prompt_text}]
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15)
        if r.status_code==200:
            j = r.json()
            # best-effort extraction
            return str(j)[:1500]
        else:
            return f"Gemini call failed: {r.status_code} {r.text[:200]}"
    except Exception as e:
        return f"Gemini call error: {e}"

def build_admin_message(analysis, auth_failed):
    now = datetime.utcnow().isoformat()
    lines = []
    lines.append(f"Server Log Summary @ {now} (UTC)")
    lines.append(f"Top IPs: {', '.join([f'{ip}({cnt})' for ip,cnt in analysis['top_ips'][:5]])}")
    lines.append(f"Top URLs: {', '.join([f'{u}({c})' for u,c in analysis['top_urls'][:5]])}")
    lines.append(f"Status breakdown: {analysis['status_counts']}")
    suspicious = []
    if analysis['sqli_ips']:
        suspicious.append(f"SQLi IPs: {analysis['sqli_ips'][:5]}")
    if analysis['xss_ips']:
        suspicious.append(f"XSS IPs: {analysis['xss_ips'][:5]}")
    if analysis['scanner_ips']:
        suspicious.append(f"Scanner UAs detected from {len(analysis['scanner_ips'])} IPs.")
    if auth_failed:
        topf = auth_failed.most_common(5)
        suspicious.append("Failed SSH logins: " + ", ".join([f"{ip}({c})" for ip,c in topf]))
    lines += suspicious
    return "\n".join(lines)

def main():
    state = load_state()
    access_lines, access_pos = tail_from(APACHE_ACCESS_LOG, state.get("access_pos",0))
    auth_lines, auth_pos = tail_from(AUTH_LOG, state.get("auth_pos",0))

    analysis = analyze_access_lines(access_lines)
    auth_failed = analyze_auth_lines(auth_lines)

    admin_message = build_admin_message(analysis, auth_failed)
    print(admin_message)

    # Use Gemini to create a smarter summary & recommendations
    gemini_prompt = "Analyze these findings and give short remediation steps:\n\n" + admin_message
    gemini_resp = summarize_with_gemini(gemini_prompt)

    full_alert = admin_message + "\n\nLLM Analysis:\n" + gemini_resp[:1500]

    # send WhatsApp if suspicious things found
    suspicious_found = bool(analysis['sqli_ips'] or analysis['xss_ips'] or analysis['scanner_ips'] or sum(auth_failed.values())>0)
    if suspicious_found and ALERT_TARGET_NUMBER:
        send_fonnte_message(ALERT_TARGET_NUMBER, full_alert)

    # Save state
    state["access_pos"] = access_pos
    state["auth_pos"] = auth_pos
    save_state(state)

if __name__=="__main__":
    main()
