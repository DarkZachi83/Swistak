# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Jawne błędy infrastruktury AI; nie zawierają tekstów prywatnych faktur."""


class AICoreError(RuntimeError):
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)


class ModelUnavailable(AICoreError):
    code = "provider_unavailable"


class InvalidResponse(AICoreError):
    code = "invalid_response"


class TaskCancelled(AICoreError):
    code = "cancelled"


class TaskTimeout(AICoreError):
    code = "timeout"


class ToolGatewayPending(AICoreError):
    code = "permission_denied"
