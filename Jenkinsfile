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
        // Nama file Python monitor khusus teman kamu
        SCRIPT_FILE = "monitorTeman.py"

        // Token Fonnte teman kamu
        FONNTE_TOKEN = "GANTI_DENGAN_TOKEN_FONNTE_TEMAN"

        // Nomor WhatsApp target Fonnte (bisa lebih dari 1, pisahkan dengan koma)
        FONNTE_TARGETS = "6281234567890"

        // API Key Gemini milik teman kamu
        GEMINI_API_KEY = "GANTI_DENGAN_API_KEY_GEMINI_TEMAN"
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
                    set -e
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
msg = f"[BotTeman] Jenkins build monitorTeman.py dimulai di {HOSTNAME} @ {ts}."

# Cek koneksi Gemini
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
                    set -e
                    LOG_FILE="$(pwd)/monitorTeman.log"
                    PID_FILE="$(pwd)/monitorTeman.pid"
                    echo "[RUN] Menjalankan $SCRIPT_FILE..."

                    if [ ! -f "$SCRIPT_FILE" ]; then
                        echo "[RUN] FAIL: $SCRIPT_FILE tidak ditemukan!"
                        exit 1
                    fi

                    # Hentikan instance lama
                    if [ -f "$PID_FILE" ]; then
                        OLD=$(cat "$PID_FILE" || true)
                        if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
                            echo "[RUN] Stop monitor lama ($OLD)..."
                            kill "$OLD" || true
                            sleep 1
                        fi
                    fi

                    export BUILD_ID=dontKillMe
                    export JENKINS_NODE_COOKIE=dontKillMe

                    # Hentikan proses lama lain
                    pkill -f "$SCRIPT_FILE" 2>/dev/null || true
                    sleep 1

                    echo "[RUN] Python: $(.venv/bin/python -V)"
                    RUNNER=".venv/bin/python -u \"$SCRIPT_FILE\""
                    nohup setsid bash -c "$RUNNER" > "$LOG_FILE" 2>&1 < /dev/null &
                    echo $! > "$PID_FILE"

                    sleep 2
                    if ps -p $(cat "$PID_FILE") >/dev/null 2>&1; then
                        echo "[RUN] OK: $SCRIPT_FILE berjalan (PID=$(cat "$PID_FILE"))"
                    else:
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
            archiveArtifacts artifacts: 'monitorTeman.log,monitorTeman.pid', allowEmptyArchive: true
        }
        success { echo "[POST] Build sukses." }
        failure { echo "[POST] Build gagal." }
    }
}