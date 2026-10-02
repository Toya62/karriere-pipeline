pipeline {
    agent any

    parameters {
        string(
            name: 'GITHUB_REPOSITORY',
            defaultValue: '',
            description: 'GitHub owner/repository to push pipeline artifacts to'
        )
        choice(
            name: 'ACTION',
            choices: ['compile', 'scrape_ba', 'scrape_indeed', 'scrape_linkedin', 'scrape_all'],
            description: 'Select whether to compile LaTeX applications or run a job scraper'
        )
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Run Job Scraper') {
            when {
                expression { return params.ACTION != 'compile' }
            }
            steps {
                sh '''
                    echo "Executing scraper action: $ACTION..."
                    docker run --rm -e ACTION="$ACTION" -v "$PWD":/workspace -w /workspace \
                        python:3.11-slim sh -c '
                            pip install -r requirements.txt --quiet
                            if [ "$ACTION" = "scrape_ba" ]; then
                                python3 main.py scrape --portal ba
                            elif [ "$ACTION" = "scrape_indeed" ]; then
                                python3 main.py scrape --portal indeed
                            elif [ "$ACTION" = "scrape_linkedin" ]; then
                                python3 main.py scrape --portal linkedin
                            elif [ "$ACTION" = "scrape_all" ]; then
                                python3 main.py scrape
                            fi
                        '
                '''
            }
        }

        stage('Compile LaTeX Applications') {
            when {
                expression { return params.ACTION == 'compile' }
            }
            steps {
                sh '''
                    UNCOMPILED=""
                    for f in $(find applications/ -name "*_cv.tex" -o -name "*_cover.tex"); do
                        pdf="${f%.tex}.pdf"
                        if [ ! -f "$pdf" ]; then
                            UNCOMPILED="$UNCOMPILED $f"
                        fi
                    done

                    if [ -z "$UNCOMPILED" ]; then
                        echo "All PDFs are up to date. Skipping LaTeX compilation container."
                    else
                        echo "Compiling uncompiled TeX files: $UNCOMPILED"
                        docker run --rm -v "$PWD":/workspace -w /workspace texlive/texlive:latest sh -c "
                            for texfile in $UNCOMPILED; do
                                dir=\$(dirname \"\$texfile\")
                                echo \"Compiling \$texfile\"
                                pdflatex -interaction=nonstopmode -output-directory=\"\$dir\" \"\$texfile\" || true
                            done
                        "
                    fi
                '''
            }
        }

        stage('CRM Sync & Push to GitHub') {
            steps {
                withCredentials([gitUsernamePassword(credentialsId: 'github-credentials', gitToolName: 'Default')]) {
                    sh '''
                        echo "Syncing CRM tracker and pushing changes..."
                        if ! printf '%s' "$GITHUB_REPOSITORY" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'; then
                            echo "GITHUB_REPOSITORY must be set to owner/repository."
                            exit 1
                        fi
                        docker run --rm -v "$PWD":/workspace -w /workspace \
                            python:3.11-slim sh -c '
                                pip install -r requirements.txt --quiet
                                python3 main.py compile --keep-tex --no-push
                            '

                        git config user.name "Jenkins CI"
                        git config user.email "jenkins@karriere-pipeline.local"

                        git add applications/ data/crm_applications.csv
                        if ! git diff-index --quiet HEAD; then
                            git commit -m "ci(jenkins): sync pipeline data [skip ci]"
                            git pull --rebase origin main
                            git push "https://github.com/$GITHUB_REPOSITORY.git" HEAD:main
                        else
                            echo "No changes to commit."
                        fi
                    '''
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            echo 'Jenkins Pipeline completed successfully!'
        }
        failure {
            echo 'Jenkins Pipeline failed.'
        }
    }
}
