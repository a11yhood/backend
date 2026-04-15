"""Security event logging for monitoring and incident response.

Logs security-relevant events in structured format for analysis.
All security-critical operations should be logged.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Configure structured logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

security_logger = logging.getLogger("security")


def log_security_event(
    event_type: str,
    user_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
    severity: str = "INFO",
):
    """Log security-relevant events in structured format.

    Args:
        event_type: Type of security event (e.g., LOGIN_FAILED, ROLE_CHANGE, UNAUTHORIZED_ACCESS)
        user_id: User ID associated with the event
        ip_address: Client IP address
        details: Additional event-specific details
        severity: Log level (INFO, WARNING, ERROR, CRITICAL)

    Examples:
        log_security_event("LOGIN_FAILED", user_id="user123", ip_address="1.2.3.4")
        log_security_event("ROLE_CHANGE", user_id="admin", details={"target": "user456", "new_role": "moderator"})
        log_security_event("UNAUTHORIZED_ACCESS", ip_address="1.2.3.4", details={"path": "/admin"}, severity="WARNING")
    """

    event_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "ip_address": ip_address,
        "details": details or {},
        "severity": severity,
    }

    log_message = json.dumps(event_data)

    if severity == "CRITICAL":
        security_logger.critical(log_message)
    elif severity == "ERROR":
        security_logger.error(log_message)
    elif severity == "WARNING":
        security_logger.warning(log_message)
    else:
        security_logger.info(log_message)


def log_auth_failure(user_id: str | None, reason: str, ip_address: str | None = None):
    """Log failed authentication attempt."""
    log_security_event(
        event_type="AUTH_FAILED",
        user_id=user_id,
        ip_address=ip_address,
        details={"reason": reason},
        severity="WARNING",
    )


def log_unauthorized_access(path: str, user_id: str | None, ip_address: str):
    """Log unauthorized access attempt."""
    log_security_event(
        event_type="UNAUTHORIZED_ACCESS",
        user_id=user_id,
        ip_address=ip_address,
        details={"path": path},
        severity="WARNING",
    )


def log_role_change(admin_id: str, target_user_id: str, old_role: str, new_role: str):
    """Log user role change."""
    log_security_event(
        event_type="ROLE_CHANGE",
        user_id=admin_id,
        details={"target_user_id": target_user_id, "old_role": old_role, "new_role": new_role},
        severity="WARNING",  # Admin actions should be monitored
    )


def log_account_lockout(user_id: str, reason: str):
    """Log account lockout event."""
    log_security_event(
        event_type="ACCOUNT_LOCKED", user_id=user_id, details={"reason": reason}, severity="WARNING"
    )
