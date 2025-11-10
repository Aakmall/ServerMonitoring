pipeline {
    agent any
    options { timestamps() }

    triggers {
        // Webhook GitHub (utama)
        githubPush()
        // Fallback polling SCM setiap ~2 menit
        pollSCM('H/2 * * * *')
    }

    environment {
        // >>> GANTI BAGIAN INI <<< 
        SCRIPT_FILE = "monitorAkmal.py"

        FONNTE_TOKEN = "R3JmjUG5sAmGbSEE7gcGqy"
        FONNTE_TARGETS = "6281933976553"

        GEMINI_API_KEY = "AIzaSyCleGyLzyLB4Ni08RiqJo3bq6E789pGWM4"
        GEMINI_MODEL = "gemini-2.5-flash"
    }

    stages {
        stage('Checkout') {
            steps {
                echo "[CHECKOUT] Ambil source code dari repo..."
                checkout scm
                sh 'ls -a | grep "$SCRIPT_FILE" || echo "[CHECKOUT] $SCRIPT_FILE tidak ditemukan di repo!"'
            }
        }

        stage('Setup Python') {
            steps {
                sh '''
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
                    . .venv/bin/activate
                    python - << 'PY'
import os, socket, datetime, requests
HOSTNAME = socket.gethostname()
ts = datetime.datetime.now().isoformat()
msg = f"[BotTeman] Jenkins build $SCRIPT_FILE dimulai di {HOSTNAME} @ {ts}."

# Cek Gemini
try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    model = genai.GenerativeModel(os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'))
    resp = model.generate_content("beri dua kata kalau Gemini aktif.")
    if getattr(resp, 'text', ''):
        msg += "\\nGemini OK: " + getattr(resp, 'text', '').strip()
except Exception as e:
    msg += f"\\nGemini gagal: {e}"

# Kirim pesan ke Fonnte
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
                    set -euo pipefail

                    LOG_FILE="$(pwd)/monitorAkmal.log"
                    PID_FILE="$(pwd)/monitorAkmal.pid"
                    echo "[RUN] Menjalankan $SCRIPT_FILE..."

                    # Cek script ada
                    if [ ! -f "$SCRIPT_FILE" ]; then
                        echo "[RUN] FAIL: $SCRIPT_FILE tidak ditemukan!"
                        exit 1
                    fi

                    # Hentikan instance lama dari PID_FILE
                    if [ -f "$PID_FILE" ]; then
                        OLD_PID=$(cat "$PID_FILE" || true)
                        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                            echo "[RUN] Stop monitor lama (PID=$OLD_PID)..."
                            kill "$OLD_PID" || true
                            sleep 1
                        fi
                    fi

                    # Hentikan proses lama lain
                    pkill -f "$SCRIPT_FILE" 2>/dev/null || true
                    sleep 1

                    # Environment agar proses tidak dibunuh Jenkins
                    export BUILD_ID=dontKillMe
                    export JENKINS_NODE_COOKIE=dontKillMe

                    # Jalankan Python monitor
                    echo "[RUN] Python version: $(.venv/bin/python -V)"
                    RUNNER=".venv/bin/python -u \"$SCRIPT_FILE\""
                    nohup setsid bash -c "$RUNNER" > "$LOG_FILE" 2>&1 < /dev/null &
                    echo $! > "$PID_FILE"
                    sleep 2

                    # Cek proses berhasil jalan
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
            echo "[POST] Arsipkan log..."
            archiveArtifacts artifacts: 'monitorAkmal.log,monitorAkmal.pid', allowEmptyArchive: true
        }
        success { echo "[POST] Build sukses." }
        failure { echo "[POST] Build gagal." }
    }
}
