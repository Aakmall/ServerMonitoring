pipeline {
  agent any
  environment {
    PYTHON = "/usr/bin/python3"
  }
  triggers {
    githubPush()     // otomatis dari GitHub webhook
    cron('H 0 * * *') // otomatis harian
  }
  stages {
    stage('Prepare') {
      steps {
        echo "Workspace: ${env.WORKSPACE}"
        sh 'pwd; ls -la'
      }
    }
    stage('Checkout') {
      steps {
        checkout([$class: 'GitSCM', branches: [[name: '*/main']],
                  userRemoteConfigs: [[url: 'https://github.com/Aakmall/ServerMonitoring.git']]])
      }
    }
    stage('Setup venv') {
      steps {
        sh '''
          python3 -m venv .venv || true
          . .venv/bin/activate
          pip install --upgrade pip
          pip install -r requirements.txt || true
        '''
      }
    }
    stage('Run Monitor') {
      steps {
        sh '''
          . .venv/bin/activate || true
          chmod +x monitor.py || true
          sudo -n python3 monitor.py || python3 monitor.py
        '''
      }
    }
  }
  post {
    success {
      archiveArtifacts artifacts: '**/wa_alert_log.txt, **/*.log', allowEmptyArchive: true
      echo "Run finished successfully."
    }
    failure {
      echo "Pipeline failed. Check console output."
    }
  }
}
