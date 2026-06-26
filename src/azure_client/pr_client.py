import httpx
from typing import List, Dict, Optional
from src.config.settings import settings
from src.azure_client.auth import get_auth_headers
def _base_url() -> str:
    return (
        f"https://dev.azure.com/{settings.AZURE_DEVOPS_ORG}/"
        f"{settings.AZURE_DEVOPS_PROJECT}/_apis"
    )

async def get_pr_diff(repository_id: str, pr_id: int) -> List[Dict]:
    """
    Fetches the list of changed files (iterations/changes) for a PR.
    Returns a list of dicts with file path and change type.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        headers = await get_auth_headers()
        # Get latest iteration ID
        iter_resp = await client.get(
            f"{_base_url()}/git/repositories/{repository_id}/pullRequests/{pr_id}/iterations",
            headers=headers,
            params={"api-version": "7.1"},
        )
        iter_resp.raise_for_status()
        iterations = iter_resp.json().get("value", [])
        if not iterations:
            return []

        latest_iter_id = iterations[-1]["id"]

        # Get changes in latest iteration
        changes_resp = await client.get(
            f"{_base_url()}/git/repositories/{repository_id}/pullRequests/{pr_id}"
            f"/iterations/{latest_iter_id}/changes",
            headers=headers,
            params={"api-version": "7.1"},
        )
        changes_resp.raise_for_status()
        return changes_resp.json().get("changeEntries", [])


async def get_file_content(repository_id: str, file_path: str, branch: str) -> Optional[str]:
    """Fetches raw file content from a branch."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = await get_auth_headers()
        resp = await client.get(
            f"{_base_url()}/git/repositories/{repository_id}/items",
            headers=headers,
            params={
                "path": file_path,
                "versionDescriptor.version": branch,
                "versionDescriptor.versionType": "branch",
                "$format": "text",
                "api-version": "7.1",
            },
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text


async def post_pr_comment(repository_id: str, pr_id: int, comment_text: str) -> Dict:
    """Posts a top-level comment (thread) to a PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = await get_auth_headers()
        resp = await client.post(
            f"{_base_url()}/git/repositories/{repository_id}/pullRequests/{pr_id}/threads",
            headers=headers,
            params={"api-version": "7.1"},
            json={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": comment_text,
                        "commentType": 1,
                    }
                ],
                "status": "active",
            },
        )
        resp.raise_for_status()
        return resp.json()