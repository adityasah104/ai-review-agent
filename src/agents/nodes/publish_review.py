import structlog
from src.agents.state import PRReviewState
from src.azure_client.pr_client import post_pr_comment

log = structlog.get_logger()

SEVERITY_EMOJI = {
    "critical": "🔴",
    "major": "🟡",
    "minor": "🔵",
    "info": "⚪",
}

CATEGORY_LABEL = {
    "code_quality": "Code Quality",
    "security": "Security",
    "performance": "Performance",
}


def _build_comment(state: PRReviewState) -> str:
    lines = []
    lines.append("## 🤖 AI PR Review — Amazon Bedrock Nova Pro")
    lines.append("")

    # CI Fix summary if applicable
    if state.ci_fix_attempts > 0:
        if state.status == "CI_FIX_GAVE_UP":
            lines.append(
                f"⚠️ **CI Auto-fix:** Attempted {state.ci_fix_attempts} fix(es) but CI still failing. "
                "Please review CI errors manually."
            )
        else:
            lines.append(
                f"🔧 **CI Auto-fix:** Applied {state.ci_fix_attempts} fix(es) to resolve CI lint errors."
            )
        lines.append("")

    # Findings by category
    findings = state.findings
    if findings:
        # Group by category
        by_category: dict = {}
        for f in findings:
            cat = f.get("category", "other")
            by_category.setdefault(cat, []).append(f)

        total = len(findings)
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        major = sum(1 for f in findings if f.get("severity") == "major")
        minor = sum(1 for f in findings if f.get("severity") == "minor")

        lines.append(f"### 📊 Summary: {total} finding(s) — 🔴 {critical} critical · 🟡 {major} major · 🔵 {minor} minor")
        lines.append("")

        for cat, cat_findings in by_category.items():
            label = CATEGORY_LABEL.get(cat, cat.title())
            lines.append(f"### {label}")
            for f in cat_findings:
                emoji = SEVERITY_EMOJI.get(f.get("severity", "minor"), "⚪")
                conf_val = float(f.get("confidence", 0.0))
                conf_pct = f"{int(conf_val * 100)}%"
                
                # Check if it was skipped due to confidence
                skipped_note = ""
                from src.config.settings import settings
                if conf_val < settings.MIN_FIX_CONFIDENCE and f.get("severity") in ("minor", "major", "critical"):
                    skipped_note = " *(Skipped auto-fix: Low Confidence)*"

                lines.append(
                    f"- {emoji} **{f.get('file_path', '')}** "
                    f"({f.get('line_hint', '')}) [Confidence: {conf_pct}]{skipped_note}: {f.get('description', '')}"
                )
                if f.get("suggestion"):
                    lines.append(f"  > 💡 *{f['suggestion']}*")
            lines.append("")
    else:
        lines.append("### ✅ No issues found by AI review agents.")
        lines.append("")

    # Aider fix summary
    if state.aider_fix_summary:
        lines.append("### 🔧 Auto-Fix Applied by Aider")
        lines.append(state.aider_fix_summary)
        lines.append("")

    # Security note removed since AI now auto-fixes critical issues

    lines.append("---")
    lines.append("*AI Review Agent · Amazon Bedrock Nova Pro · This PR has not been auto-merged.*")

    return "\n".join(lines)


async def run(state: PRReviewState) -> dict:
    """Posts the final review summary as a PR comment in Azure DevOps."""
    log.info("publish_review_start", pr_id=state.pr_id, findings=len(state.findings))

    comment = _build_comment(state)

    try:
        await post_pr_comment(state.repository_id, state.pr_id, comment)
        log.info("publish_review_done")
        return {"review_summary": comment, "status": "DONE"}
    except Exception as e:
        log.error("publish_review_error", error=str(e))
        return {"status": "FAILED", "error": f"Failed to post PR comment: {e}"}