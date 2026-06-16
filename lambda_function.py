import os
import json
import hmac
import hashlib
import requests
import boto3


GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
AGENT_ID = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS_ID = os.environ["BEDROCK_AGENT_ALIAS_ID"]
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")

bedrock_agent = boto3.client("bedrock-agent-runtime", region_name=REGION)


def verify_github_signature(event):
    signature = event.get("headers", {}).get("x-hub-signature-256")
    if not signature:
        return False

    body = event.get("body", "")
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def get_pr_diff(owner, repo, pr_number):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def invoke_bedrock_agent(diff_text):
    prompt = f"""
다음 GitHub Pull Request 변경사항을 코드 리뷰해주세요.

리뷰 항목:
1. 버그 및 논리 오류
2. 보안 취약점
3. 코드 스타일 문제
4. 성능 문제
5. 테스트 코드 제안
6. 리팩토링 제안

변경사항:
{diff_text[:12000]}
"""

    response = bedrock_agent.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId="codebuddy-session",
        inputText=prompt
    )

    result = ""

    for event in response["completion"]:
        if "chunk" in event:
            result += event["chunk"]["bytes"].decode("utf-8")

    return result


def post_pr_comment(owner, repo, pr_number, review_text):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    body = {
        "body": f"""## CodeBuddy AI Review

{review_text}
"""
    }

    response = requests.post(url, headers=headers, json=body, timeout=20)
    response.raise_for_status()


def lambda_handler(event, context):
    try:
        if not verify_github_signature(event):
            return {
                "statusCode": 401,
                "body": "Invalid GitHub signature"
            }

        payload = json.loads(event["body"])

        action = payload.get("action")
        if action not in ["opened", "synchronize", "reopened"]:
            return {
                "statusCode": 200,
                "body": "Ignored event"
            }

        repo = payload["repository"]["name"]
        owner = payload["repository"]["owner"]["login"]
        pr_number = payload["pull_request"]["number"]

        diff_text = get_pr_diff(owner, repo, pr_number)
        review_text = invoke_bedrock_agent(diff_text)
        post_pr_comment(owner, repo, pr_number, review_text)

        return {
            "statusCode": 200,
            "body": "CodeBuddy review completed"
        }

    except Exception as e:
        print("ERROR:", str(e))
        return {
            "statusCode": 500,
            "body": str(e)
        }