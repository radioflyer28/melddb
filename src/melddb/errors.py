"""Stable errors; driver exceptions are retained as __cause__."""


class MeldDBError(Exception):
    code = "melddb"


class ValidationError(MeldDBError):
    code = "validation"

    def __init__(self, message, violations=()):
        super().__init__(message)
        self.violations = list(violations)


class ConstraintError(MeldDBError):
    code = "constraint"


class AlreadyExistsError(ConstraintError):
    code = "already_exists"


class ConflictError(MeldDBError):
    code = "conflict"


class NotFoundError(MeldDBError):
    code = "not_found"


class OwnershipError(MeldDBError):
    code = "ownership"


class TransactionError(MeldDBError):
    code = "transaction"


class TransactionOutcomeError(TransactionError):
    """A transaction boundary left the connection or durable outcome uncertain."""

    code = "transaction_outcome"

    def __init__(self, message, *, phase, outcome, initiating_error=None,
                 backend_error=None):
        super().__init__(message)
        self.phase = phase
        self.outcome = outcome
        self.initiating_error = initiating_error
        self.backend_error = backend_error


class CommitError(TransactionOutcomeError):
    code = "commit"


class RollbackError(TransactionOutcomeError):
    code = "rollback"


class BusyError(MeldDBError):
    code = "busy"


class ConnectionError(MeldDBError):
    code = "connection"


class UnsupportedError(MeldDBError):
    code = "unsupported"


class MigrationError(MeldDBError):
    code = "migration"


class TraversalLimitError(MeldDBError):
    code = "traversal_limit"
