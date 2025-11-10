pipeline {
    agent any
    options { timestamps() }

    triggers {
        githubPush()               // Webhook GitHub
        pollSCM('H/2 * * * *')    // fallback polling setiap ~2 menit
    }

    environment {
        SCRIPT_FILE = "monitorAkmal.py"
        FONNTE_TOKEN = "YmDKKgGMMwRAYkyaaguc"
        FONNTE_TARGETS = "62882019908677"
        GEMINI_API_KEY = "AIzaSyD-lbp5g18WGTjLEpSTOjeucZkYN_8em-8"
        GEMINI_MODEL = "gemini-2.5-flash"
    }

    stages {
        stage('Checkout') {
            steps {
                echo "[CHECKOUT] Mengambil source code dari repo..."
                checkout scm
                sh '''
                    #!/bin/bash
                    ls -a | grep "$SCRIPT_FILE" || echo "[CHECKOUT] $SCRIPT_FILE tidak ditemukan di repo!"
                '''
            }
        }

        stage('Setup Python') {
            steps {
                sh '''
                    #!/bin/bash
                    set -euo pipefail
                    echo "[SETUP] Membuat virtual environment..."
                    if [ ! -d .venv ]; then
                        python3 -m venv .venv
                    fi
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install requests google-generativeai python-dotenv
                '''
            }
        }

        stage('Notify WhatsApp CI Start') {
            steps {
                sh '''
                    #!/bin/bash
                    . .venv/bin/activate
                    python - << 'PY'
import os, socket, datetime, requests

HOSTNAME = socket.gethostname()
ts = datetime.datetime.now().isoformat()
msg = f"[BotAkmal] Jenkins build monitorAkmal.py dimulai di {HOSTNAME} @ {ts}."

# Tes integrasi Gemini
try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    model = genai.GenerativeModel(os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'))
    resp = model.generate_content("uji koneksi Gemini")
    if getattr(resp, 'text', ''):
        msg += "\\nInsight Gemini: " + getattr(resp, 'text', '').strip()
except Exception as e:
    msg += f"\\nAI Gemini gagal: {e}"

# Kirim Fonnte
token = os.getenv("FONNTE_TOKEN")
targets = [t.strip() for t in os.getenv("FONNTE_TARGETS", "").split(',') if t.strip()]
for t in targets:
    try:
        r = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            data={"target": t, "message": msg},
            timeout=10
        )
        print(f"Fonnte {t} {r.status_code}")
    except Exception as e:
        print("Fonnte error", e)
PY
                '''
            }
        }

        stage('Run Monitor') {
            steps {
                sh '''
                    #!/bin/bash
                    set -euo pipefail

                    LOG_FILE="$(pwd)/monitor.log"
                    PID_FILE="$(pwd)/monitor.pid"
                    echo "[RUN] Menjalankan $SCRIPT_FILE..."

                    if [ ! -f "$SCRIPT_FILE" ]; then
                        echo "[RUN] FAIL: $SCRIPT_FILE tidak ditemukan di $(pwd)"
                        ls -la
                        exit 1
                    fi

                    if [ -f "$PID_FILE" ]; then
                        OLD=$(cat "$PID_FILE" || true)
                        if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
                            echo "[RUN] Menghentikan monitor lama ($OLD)..."
                            kill "$OLD" || true
                            sleep 1
                        fi
                    fi

                    export BUILD_ID=dontKillMe
                    export JENKINS_NODE_COOKIE=dontKillMe

                    pkill -f "$SCRIPT_FILE" 2>/dev/null || true
                    sleep 1

                    echo "[RUN] Python: $(.venv/bin/python -V)"
                    RUNNER=".venv/bin/python -u \"$SCRIPT_FILE\""
                    nohup setsid bash -c "$RUNNER" > "$LOG_FILE" 2>&1 < /dev/null &
                    echo $! > "$PID_FILE"
                    sleep 2

                    if ps -p $(cat "$PID_FILE") >/dev/null 2>&1; then
                        echo "[RUN] OK: $SCRIPT_FILE berjalan (PID=$(cat "$PID_FILE"))"
                    else
                        echo "[RUN] FAIL: Gagal menjalankan $SCRIPT_FILE"
                        tail -n 200 "$LOG_FILE" || true
                        exit 1
                    fi
                '''
            }
        }
    }

    post {
        always {
            echo "[POST] Arsipkan log & PID file..."
            archiveArtifacts artifacts: 'monitor.log,monitor.pid', allowEmptyArchive: true
        }
        success {
            echo "[POST] Build sukses."
        }
        failure {
            echo "[POST] Build gagal."
        }
    }
}
