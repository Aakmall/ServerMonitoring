#!/usr/bin/env python3
import os
import re
import time
import socket
import logging
import requests
import concurrent.futures
import subprocess
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Iterator
import sys
import atexit

# ==========================================================
# 🧩 LOCK FILE: agar tidak bentrok dengan BotFajri
# ==========================================================
LOCK_FILE = "/tmp/ssh_monitor_Akmal.lock"

if os.path.exists(LOCK_FILE):
    print(f"⚠️  Monitor Akmal sudah berjalan (lock file: {LOCK_FILE}). Keluar.")
    sys.exit(0)

with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

@atexit.register
def cleanup():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

# ==========================================================
# Konfigurasi utama (ubah bagian ini sesuai user temanmu)
# ==========================================================
HOSTNAME = socket.gethostname()

# >>> GANTI BAGIAN INI <<<
FONNTE_TOKEN = "R3JmjUG5sAmGbSEE7gcGqy"
FONNTE_TARGETS = ["6281933976553"]

GEMINI_API_KEY = "AIzaSyCleGyLzyLB4Ni08RiqJo3bq6E789pGWM4"
GEMINI_MODEL = "gemini-2.5-flash"

BOT_NAME = "BotAkmal"  # nama bot untuk pesan WhatsApp

LOG_PATHS = ["/var/log/auth.log", "/var/log/secure"]
POLL_INTERVAL = 1.0
FAIL_WINDOW_SEC = 300
SUCCESS_WINDOW_SEC = 300
FAIL_THRESHOLD = 5
SUCCESS_THRESHOLD = 2
ALERT_SESSION_OPEN = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

RE_SUCCESS = re.compile(r"Accepted\s+(?P<method>\S+)\s+for\s+(?P<user>\S+)\s+from\s+(?P<ip>\S+)", re.IGNORECASE)
RE_FAIL = re.compile(r"Failed\s+password\s+for\s+(?:invalid user\s+)?(?P<user>\S+)\s+from\s+(?P<ip>\S+)", re.IGNORECASE)

def utc_now_iso(): return datetime.now(timezone.utc).isoformat()

def analyze_with_gemini(summary: str) -> str | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = (
            f"Nama kamu {BOT_NAME}. Analisis singkat untuk: {summary}. "
            "Gunakan format:\n*Tingkat Risiko:* <Low|Medium|High>\n*Alasan:* <1-3 kalimat>"
        )
        resp = model.generate_content(prompt)
        return getattr(resp, 'text', '').strip() or None
    except Exception as e:
        logging.warning("Gemini gagal: %s", e)
        return None

def send_fonnte_message(msg: str):
    for t in FONNTE_TARGETS:
        try:
            r = requests.post("https://api.fonnte.com/send",
                headers={"Authorization": FONNTE_TOKEN},
                data={"target": t, "message": msg},
                timeout=10)
            logging.info("Fonnte %s: %s", t, r.status_code)
        except Exception as e:
            logging.warning("Fonnte error ke %s: %s", t, e)

def gemini_with_timeout(summary: str, timeout=6.0) -> str | None:
    def _call(): return analyze_with_gemini(summary)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_call).result(timeout=timeout)
    except Exception:
        return None

def parse_event(line: str):
    now = utc_now_iso()
    m = RE_SUCCESS.search(line)
    if m:
        return {"ts": now, "type": "login_success", "user": m["user"], "ip": m["ip"], "method": m["method"]}
    m = RE_FAIL.search(line)
    if m:
        return {"ts": now, "type": "login_fail", "user": m["user"], "ip": m["ip"]}
    return None

def tail_file(path: str):
    pos = None; init = False
    while True:
        try:
            with open(path, "r", errors="ignore") as f:
                if not init:
                    f.seek(0, os.SEEK_END)
                    pos = f.tell()
                    init = True
                else:
                    f.seek(pos)
                chunk = f.read()
                if chunk:
                    pos = f.tell()
                    for line in chunk.splitlines():
                        yield line
        except FileNotFoundError:
            pass
        time.sleep(POLL_INTERVAL)
        yield None

def format_msg(event, analysis: str | None = None) -> str:
    base = f"[{BOT_NAME}] Host: {HOSTNAME}\nUser: {event['user']}\nIP: {event['ip']}\nType: {event['type']}\nTime: {event['ts']}"
    base += "\n\nAnalisis BotTeman:\n" + (analysis or "-")
    return base

def main():
    logging.info(f"[{BOT_NAME}] Mulai monitor log SSH...")
    ip_fail = defaultdict(deque)
    last_sent = {}
    DEDUP_TTL_SEC = 60
    paths = [p for p in LOG_PATHS if os.path.exists(p)]
    tails = [(p, tail_file(p)) for p in paths]

    while True:
        for _, gen in tails:
            line = next(gen, None)
            if not line: continue
            evt = parse_event(line)
            if not evt: continue

            key = (evt["type"], evt.get("user"), evt.get("ip"))
            now = time.time()
            if last_sent.get(key, 0) + DEDUP_TTL_SEC > now:
                continue

            summary = f"{evt['type']} user={evt['user']} ip={evt['ip']} host={HOSTNAME}"
            analysis = gemini_with_timeout(summary)
            msg = format_msg(evt, analysis)
            send_fonnte_message(msg)
            last_sent[key] = now

if __name__ == "__main__":
    logging.info("[BotTeman] start")
    threading.Thread(target=lambda: send_fonnte_message(f"[BotTeman] monitor aktif di {socket.gethostname()}"), daemon=True).start()
    main()