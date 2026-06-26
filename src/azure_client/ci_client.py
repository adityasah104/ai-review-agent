import httpx
from typing import Optional, Dict
from src.config.settings import settings
from src.azure_client.auth import get_auth_headers
import os
import requests


def get_devops_token():
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        # Azure DevOps's resource scope — note the trailing /.default
        "scope": "499b84ac-1321-427f-aa17-267ca6975798/.default",
    }
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _base_url() -> str:
    return (
        f"https://dev.azure.com/{settings.AZURE_DEVOPS_ORG}/"
        f"{settings.AZURE_DEVOPS_PROJECT}/_apis"
    )


async def get_latest_build_for_branch(source_branch: str) -> Optional[Dict]:
    """
    Returns the latest pipeline build for the given branch.
    source_branch should be in the format 'refs/heads/feature/my-branch'.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        headers = await get_auth_headers()
        resp = await client.get(
            f"{_base_url()}/build/builds",
            headers=headers,
            params={
                "branchName": source_branch,
                "$top": 1,
                "queryOrder": "queueTimeDescending",
                "api-version": "7.1",
            },
        )
        resp.raise_for_status()
        builds = resp.json().get("value", [])
        if not builds:
            return None
        return builds[0]


async def get_build_logs(build_id: int) -> str:
    """
    Returns concatenated log text for a build. Used to parse lint errors.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        headers = await get_auth_headers()
        # Get list of log entries
        logs_resp = await client.get(
            f"{_base_url()}/build/builds/{build_id}/logs",
            headers=headers,
            params={"api-version": "7.1"},
        )
        logs_resp.raise_for_status()
        log_entries = logs_resp.json().get("value", [])

        all_logs = []
        for entry in log_entries:
            log_id = entry["id"]
            log_text_resp = await client.get(
                f"{_base_url()}/build/builds/{build_id}/logs/{log_id}",
                headers=headers,
                params={"api-version": "7.1"},
            )
            if log_text_resp.status_code == 200:
                all_logs.append(log_text_resp.text)

        return "\n".join(all_logs)