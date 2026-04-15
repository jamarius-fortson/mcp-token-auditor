"""Alert Monitor Agent - Real-time threshold enforcement and anomaly detection."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from src.models.audit import Alert, AlertRule, AuditEvent
from src.storage.database import AuditDatabase

logger = logging.getLogger(__name__)

# Default alert rules
DEFAULT_RULES: Dict[str, Dict[str, Any]] = {
    "CTX_WARN": {"threshold": 40, "enabled": True, "severity": "WARNING"},
    "CTX_CRITICAL": {"threshold": 60, "enabled": True, "severity": "CRITICAL"},
    "TOOL_BLOAT": {"threshold": 300, "enabled": True, "severity": "WARNING"},
    "SCHEMA_BLOAT": {"threshold": 400, "enabled": True, "severity": "WARNING"},
    "CALL_SPIKE": {"threshold": 60, "enabled": True, "severity": "INFO"},
    "SERVER_DRIFT": {"threshold": 25, "enabled": True, "severity": "WARNING"},
}

DEBOUNCE_WINDOW_SEC = 30


class AlertMonitorAgent:
    """Real-time threshold enforcement and anomaly detection system."""

    def __init__(self, db: AuditDatabase, alerts_config: Dict[str, Any]):
        """Initialize alert monitor.
        
        Args:
            db: AuditDatabase instance
            alerts_config: Alert configuration
        """
        self.db = db
        self.alerts_config = alerts_config
        self.rules: Dict[str, AlertRule] = self._load_rules()
        self.webhook_url = alerts_config.get("webhook_url", "")
        self.alert_buffer: List[Alert] = []
        
        logger.info(f"AlertMonitorAgent initialized with {len(self.rules)} rules")

    def _load_rules(self) -> Dict[str, AlertRule]:
        """Load alert rules from config."""
        rules = {}
        rule_configs = self.alerts_config.get("rules", DEFAULT_RULES)
        
        for rule_id, config in rule_configs.items():
            rules[rule_id] = AlertRule(
                rule_id=rule_id,
                trigger=rule_id,
                threshold=config.get("threshold", 0),
                severity=config.get("severity", "WARNING"),
                enabled=config.get("enabled", True),
            )
        
        return rules

    async def evaluate_audit_event(self, audit_event: AuditEvent) -> List[Alert]:
        """Evaluate all alert rules against audit event.
        
        Args:
            audit_event: Audit event from Token Audit Agent
            
        Returns:
            List of triggered alerts (filtered by debounce)
        """
        alerts: List[Alert] = []
        
        # Skip if not a tool metadata event
        if audit_event.message_type.value == "other":
            return alerts
        
        server_id = audit_event.server_id
        tool_name = audit_event.tool_name or ""
        
        # Evaluate each enabled rule
        for rule_id, rule in self.rules.items():
            if not rule.enabled:
                continue
            
            alert: Optional[Alert] = None
            
            # CTX_WARN: > 40% context window
            if rule_id == "CTX_WARN" and audit_event.context_window_pct >= rule.threshold:
                alert = self._create_alert(
                    rule=rule,
                    audit_event=audit_event,
                    current_value=audit_event.context_window_pct,
                    message=f"Token metadata consuming {audit_event.context_window_pct}% of context window",
                )
            
            # CTX_CRITICAL: > 60% context window (never suppressed)
            elif rule_id == "CTX_CRITICAL" and audit_event.context_window_pct >= rule.threshold:
                alert = self._create_alert(
                    rule=rule,
                    audit_event=audit_event,
                    current_value=audit_event.context_window_pct,
                    message=f"CRITICAL: Token metadata consuming {audit_event.context_window_pct}% of context window",
                )
                # CTX_CRITICAL is never debounced
                alert.suppressed = False
            
            # TOOL_BLOAT: single tool description > 300 tokens
            elif rule_id == "TOOL_BLOAT" and audit_event.token_breakdown:
                desc_tokens = audit_event.token_breakdown.description_tokens
                if desc_tokens > rule.threshold:
                    alert = self._create_alert(
                        rule=rule,
                        audit_event=audit_event,
                        current_value=float(desc_tokens),
                        message=f"Tool '{tool_name}' description exceeds {rule.threshold} tokens ({desc_tokens} tokens)",
                    )
            
            # SCHEMA_BLOAT: single tool schema > 400 tokens
            elif rule_id == "SCHEMA_BLOAT" and audit_event.token_breakdown:
                schema_tokens = audit_event.token_breakdown.schema_tokens
                if schema_tokens > rule.threshold:
                    alert = self._create_alert(
                        rule=rule,
                        audit_event=audit_event,
                        current_value=float(schema_tokens),
                        message=f"Tool '{tool_name}' schema exceeds {rule.threshold} tokens ({schema_tokens} tokens)",
                    )
            
            # CALL_SPIKE: Tool called > X times per minute
            elif rule_id == "CALL_SPIKE":
                call_count = self.db.get_call_count(server_id, minutes=1)
                if call_count > rule.threshold:
                    alert = self._create_alert(
                        rule=rule,
                        audit_event=audit_event,
                        current_value=float(call_count),
                        message=f"Server '{server_id}' call spike: {call_count} calls/min (threshold: {rule.threshold})",
                    )
            
            # SERVER_DRIFT: Deviates > X% from rolling baseline
            elif rule_id == "SERVER_DRIFT" and audit_event.token_breakdown:
                avg_tokens = self.db.get_server_token_average(server_id)
                current_tokens = audit_event.token_breakdown.total_tool_tokens
                
                if avg_tokens > 0:
                    drift_pct = abs(current_tokens - avg_tokens) / avg_tokens * 100
                    if drift_pct > rule.threshold:
                        alert = self._create_alert(
                            rule=rule,
                            audit_event=audit_event,
                            current_value=drift_pct,
                            message=f"Tool '{tool_name}' size drift: {drift_pct:.1f}% from average {avg_tokens:.1f} tokens",
                        )
            
            # Apply debouncing (except CRITICAL)
            if alert:
                if rule_id != "CTX_CRITICAL":
                    if not self._should_fire(rule_id, server_id):
                        alert.suppressed = True
                        logger.debug(f"Alert {rule_id} suppressed by debounce for {server_id}")
                    else:
                        self.db.update_alert_state(rule_id, server_id)
                
                alerts.append(alert)
        
        # Persist fired alerts
        for alert in alerts:
            if not alert.suppressed:
                if self.db.write_alert(alert.to_dict()):
                    logger.info(f"Alert fired: {alert.rule_id} ({alert.severity})")
                    self.alert_buffer.append(alert)
        
        return alerts

    def _create_alert(
        self,
        rule: AlertRule,
        audit_event: AuditEvent,
        current_value: float,
        message: str,
    ) -> Alert:
        """Create an alert instance."""
        return Alert(
            rule_id=rule.rule_id,
            severity=rule.severity,
            triggered_by_audit_id=audit_event.audit_id,
            server_id=audit_event.server_id,
            tool_name=audit_event.tool_name,
            message=message,
            current_value=current_value,
            threshold_value=rule.threshold,
            timestamp=datetime.utcnow(),
        )

    def _should_fire(self, rule_id: str, server_id: str) -> bool:
        """Check if alert should fire (not debounced).
        
        Args:
            rule_id: Alert rule ID
            server_id: Server ID
            
        Returns:
            True if should fire, False if debounced
        """
        last_fired = self.db.get_alert_last_fired(rule_id, server_id)
        if not last_fired:
            return True
        
        time_since_fire = (datetime.utcnow() - last_fired).total_seconds()
        return time_since_fire >= DEBOUNCE_WINDOW_SEC

    async def flush_alert_buffer(self) -> List[Alert]:
        """Flush buffered alerts (for when webhook reconnects).
        
        Returns:
            List of alerts that were flushed
        """
        flushed = self.alert_buffer.copy()
        self.alert_buffer.clear()
        logger.info(f"Flushed {len(flushed)} buffered alerts")
        return flushed
