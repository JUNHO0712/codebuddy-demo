# CodeBuddy

CodeBuddy는 GitHub Pull Request가 생성되면 AWS Lambda와 Amazon Bedrock Agent를 이용해 자동으로 코드 리뷰를 수행하고, 리뷰 결과를 GitHub PR 댓글과 Slack 알림으로 전송하는 서버리스 코드 리뷰 시스템입니다.

## Architecture

GitHub Pull Request  
-> GitHub Webhook  
-> AWS Lambda Function URL  
-> Amazon Bedrock Agent  
-> GitHub PR Comment  
-> Slack Notification  

## Features

- GitHub Pull Request 자동 감지
- GitHub API를 이용한 PR diff 조회
- Amazon Bedrock Agent 기반 코드 리뷰 생성
- 버그, 보안 취약점, 코드 스타일, 성능 문제 분석
- 테스트 코드 및 리팩토링 제안
- GitHub PR 댓글 자동 등록
- Slack 리뷰 완료 알림 전송
- CloudFormation/SAM 템플릿 기반 배포 지원

## Repository Structure

```text
codebuddy-demo/
├── lambda_function.py
├── template.yaml
├── requirements.txt
└── README.md
