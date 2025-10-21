pipeline {
    agent any

    environment {
        DOCKER_HUB_CREDENTIALS = credentials('docker-hub')  // Jenkins credential ID
        DOCKER_IMAGE = "shreyeah29/week7-myapp:latest"
    }

    stages {
        stage('Checkout Code') {
            steps {
                echo '📦 Cloning repository...'
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                echo '🐳 Building Docker image...'
                sh 'docker build -t $DOCKER_IMAGE -f app/Dockerfile ./app'
            }
        }

        stage('Run Container Test') {
            steps {
                echo '🚀 Running test container...'
                sh '''
                docker stop temp-week7 || true
                docker rm temp-week7 || true
                docker run -d -p 5012:5001 --name temp-week7 $DOCKER_IMAGE
                sleep 5
                docker ps
                docker stop temp-week7
                docker rm temp-week7
                '''
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo '📤 Pushing image to Docker Hub...'
                sh '''
                echo $DOCKER_HUB_CREDENTIALS_PSW | docker login -u $DOCKER_HUB_CREDENTIALS_USR --password-stdin
                docker push $DOCKER_IMAGE
                '''
            }
        }
    }

    post {
        success {
            echo '✅ Pipeline executed successfully — Image pushed to Docker Hub!'
        }
        failure {
            echo '❌ Pipeline failed. Please check the logs.'
        }
    }
}
