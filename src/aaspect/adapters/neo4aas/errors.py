"""Which database errors the uploaded content causes."""

from neo4j.exceptions import Neo4jError

# Codes seen for content neo4aas passes on but the server refuses: a missing id, a key
# without a type, a list mixing text and numbers. Other statement errors would point at a
# broken query, which must fail the step instead of every document.
_CONTENT_REFUSED = {
    "Neo.ClientError.Procedure.ProcedureCallFailed",
    "Neo.ClientError.Statement.TypeError",
}
_TIMED_OUT = "Neo.ClientError.Transaction.TransactionTimedOut"
_OUT_OF_MEMORY = "Neo.TransientError.General.MemoryPoolOutOfMemoryError"
# Only the per-transaction limit is the document's fault; the shared pool can be used up
# by other analyses. The server names the limit in its message.
_TRANSACTION_LIMIT = "db.memory.transaction.max threshold"


def content_fault(error: Neo4jError) -> str | None:
    """Why the content the statement worked on is at fault, or None if the server or the
    query is: a step must fail on those instead of blaming the corpus."""
    code = error.code or ""
    if code in _CONTENT_REFUSED:
        return f"content cannot be stored: {code}"
    if code.startswith(_TIMED_OUT) or (
        code == _OUT_OF_MEMORY and _TRANSACTION_LIMIT in (error.message or "")
    ):
        return "too large to store in one transaction"
    return None
