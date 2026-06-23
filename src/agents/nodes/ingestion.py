import structlog
from src.agents.state import PRReviewState
from src.azure_client.pr_client import get_pr_diff, get_file_content

log = structlog.get_logger()


async def run(state: PRReviewState) -> dict:
    """
    Fetches the list of changed files and their content from the PR.
    Only fetches Python (.py) and SQL (.sql) files — skips everything else.
    """
    log.info("ingestion_start", pr_id=state.pr_id)

    try:
        changes = await get_pr_diff(state.repository_id, state.pr_id)

        changed_files = []
        file_contents = {}

        for change in changes:
            item = change.get("item", {})
            path = item.get("path", "")
            change_type = change.get("changeType", "")

            # Only care about Python and SQL files
            if not (path.endswith(".py") or path.endswith(".sql")):
                continue

            # Skip deleted files
            if "delete" in change_type.lower():
                continue

            changed_files.append({
                "path": path,
                "change_type": change_type,
                "file_type": "python" if path.endswith(".py") else "sql",
            })

            # Fetch actual content from the source branch
            content = await get_file_content(
                state.repository_id,
                path,
                state.source_branch.replace("refs/heads/", ""),
            )
            if content:
                file_contents[path] = content

        log.info("ingestion_done", files_found=len(changed_files))
        return {
            "changed_files": changed_files,
            "file_contents": file_contents,
            "status": "INGESTED",
        }

    except Exception as e:
        log.error("ingestion_failed", error=str(e))
        return {"status": "FAILED", "error": f"Ingestion failed: {e}"}