from app.domains.developer.service.monitoring_service import MonitoringService
from app.infrastructure.monitoring.call_log_repository import get_call_log_repository


def get_monitoring_service() -> MonitoringService:
    return MonitoringService(get_call_log_repository())
