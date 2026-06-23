import structlog
from src.agents.state import PRReviewState
from src.rag.retriever import retrieve_guidelines

log = structlog.get_logger()


async def run(state: PRReviewState) -> dict:
    """
    Queries ChromaDB to fetch relevant Python and dbt guidelines
    based on what file types changed in the PR.
    """
    log.info("context_retrieval_start")

    file_types = list(set(f["file_type"] for f in state.changed_files))
    queries = []

    if "python" in file_types:
        queries.append("Python code quality best practices PEP8 style guide")
        queries.append("Python security vulnerabilities common mistakes")

    if "sql" in file_types:
        queries.append("dbt SQL style guide best practices naming conventions")
        queries.append("SQL performance optimization query structure")

    if not queries:
        return {"rag_context": []}

    all_context = []
    for query in queries:
        results = retrieve_guidelines(query, n_results=3)
        all_context.extend(results)

    # Deduplicate
    seen = set()
    unique_context = []
    for item in all_context:
        if item not in seen:
            seen.add(item)
            unique_context.append(item)

    log.info("context_retrieval_done", chunks=len(unique_context))
    return {"rag_context": unique_context[:8]}  # Cap at 8 chunks