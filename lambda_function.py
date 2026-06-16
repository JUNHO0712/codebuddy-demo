import os
import json
import hmac
import hashlib
import base64
import urllib.request
import urllib.error
import traceback
import boto3


GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
AGENT_ID = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS_ID = os.environ["BEDROCK_AGENT_ALIAS_ID"]
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")

bedrock_agent = boto3.client("bedrock-agent-runtime", region_name=REGION)


def get_header(headers, key):
    for k, v in headers.items():
        if k.lower() == key.lower():
            return v
    return None


def get_body(event):
    body = event.get("body", "")

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    return body


def verify_github_signature(event):
    headers = event.get("headers", {}) or {}
    signature = get_header(headers, "x-hub-signature-256")

    if not signature:
        return False

    body = get_body(event)

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def http_request(url, method="GET", headers=None, data=None):
    headers = headers or {}

    if data is not None:
        data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"HTTPError {e.code}: {error_body}")


def get_pr_diff(owner, repo, pr_number):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codebuddy-review"
    }

    return http_request(url, method="GET", headers=headers)


def invoke_bedrock_agent(owner, repo, pr_number, diff_text):
    prompt = f"""
너는 GitHub Pull Request를 검토하는 코드 리뷰 도우미야.

다음 Pull Request 변경사항을 한국어로 리뷰해줘.

Repository: {owner}/{repo}
Pull Request: #{pr_number}

아래 형식으로 답변해줘.

1. 버그 및 논리 오류
2. 보안 취약점
3. 코드 스타일 문제
4. 성능 문제
5. 테스트 코드 제안
6. 리팩토링 제안
7. 종합 의견

변경사항:
{diff_text[:12000]}
"""

    response = bedrock_agent.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=f"codebuddy-{owner}-{repo}-{pr_number}",
        inputText=prompt
    )

    result = ""

    for event in response["completion"]:
        if "chunk" in event:
            result += event["chunk"]["bytes"].decode("utf-8")

    return result.strip()


def post_pr_comment(owner, repo, pr_number, review_text):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codebuddy-review"
    }

    body = {
        "body": f"""## CodeBuddy AI Review

{review_text}
"""
    }

    return http_request(url, method="POST", headers=headers, data=body)


def post_slack_message(owner, repo, pr_number, review_text):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set. Skip Slack notification.")
        return

    pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"

    body = {
        "text": f"""CodeBuddy 리뷰 완료

Repository: {owner}/{repo}
Pull Request: #{pr_number}
URL: {pr_url}

리뷰 요약:
{review_text[:1000]}
"""
    }

    return http_request(SLACK_WEBHOOK_URL, method="POST", headers={}, data=body)


def lambda_handler(event, context):
    try:
        print("EVENT:", json.dumps(event))

        headers = event.get("headers", {}) or {}
        github_event = get_header(headers, "x-github-event")

        if github_event == "ping":
            return {
                "statusCode": 200,
                "body": "GitHub webhook ping received"
            }

        if not verify_github_signature(event):
            return {
                "statusCode": 401,
                "body": "Invalid GitHub signature"
            }

        payload = json.loads(get_body(event))

        action = payload.get("action")
        if action not in ["opened", "synchronize", "reopened"]:
            return {
                "statusCode": 200,
                "body": f"Ignored action: {action}"
            }

        owner = payload["repository"]["owner"]["login"]
        repo = payload["repository"]["name"]
        pr_number = payload["pull_request"]["number"]

        diff_text = get_pr_diff(owner, repo, pr_number)
        review_text = invoke_bedrock_agent(owner, repo, pr_number, diff_text)

        post_pr_comment(owner, repo, pr_number, review_text)
        post_slack_message(owner, repo, pr_number, review_text)

        return {
            "statusCode": 200,
            "body": "CodeBuddy review completed"
        }

    except Exception as e:
        print("ERROR:", str(e))
        print(traceback.format_exc())

        return {
            "statusCode": 500,
            "body": str(e)
        }
