pipeline {
  agent any
  environment {
    PYTHON = "/usr/bin/python3"
  }
  triggers {
    githubPush()  // tambahkan ini
    cron('H 0 * * *')
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
        // use HTTPS public repo (no credentials)
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
          # Ensure script is executable
          chmod +x monitor.py || true
          sudo -n python3 monitor.py || python3 monitor.py
        '''
      }
    }
  }
  post {
    success {
      archiveArtifacts artifacts: '**/report*.html, **/*.log', allowEmptyArchive: true
      echo "Run finished successfully."
    }
    failure {
      echo "Pipeline failed. Check console output."
    }
  }
}
