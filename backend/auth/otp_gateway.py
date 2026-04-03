"""
Ask VJ — OTP Gateway

Pluggable OTP delivery: mock (console logging) or Twilio SMS.
"""

import logging
from typing import Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)


@runtime_checkable
class OTPGateway(Protocol):
    """Interface for sending OTP codes to a phone number."""

    async def send_otp(self, phone: str, code: str) -> bool: ...


class MockOTPGateway:
    """
    Development gateway that logs OTP codes to the console.
    Always returns True.
    """

    async def send_otp(self, phone: str, code: str) -> bool:
        logger.info("MOCK OTP -> phone=%s code=%s", phone, code)
        return True


class TwilioOTPGateway:
    """
    Production gateway that sends OTP codes via Twilio SMS API.
    """

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._url = (
            f"https://api.twilio.com/2010-04-01"
            f"/Accounts/{account_sid}/Messages.json"
        )

    async def send_otp(self, phone: str, code: str) -> bool:
        body = f"Your Ask VJ verification code is: {code}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._url,
                    auth=(self._account_sid, self._auth_token),
                    data={
                        "To": phone,
                        "From": self._from_number,
                        "Body": body,
                    },
                    timeout=10.0,
                )
            if resp.status_code in (200, 201):
                logger.info("Twilio OTP sent to %s (sid=%s)", phone, resp.json().get("sid"))
                return True
            logger.error("Twilio error %d: %s", resp.status_code, resp.text)
            return False
        except httpx.HTTPError as exc:
            logger.exception("Twilio request failed for %s: %s", phone, exc)
            return False


def create_otp_gateway(config) -> OTPGateway:
    """
    Factory: return the appropriate OTP gateway based on config.auth.otp_gateway.
    """
    gateway_type = config.auth.otp_gateway.lower()
    if gateway_type == "twilio":
        return TwilioOTPGateway(
            account_sid=config.auth.twilio_account_sid,
            auth_token=config.auth.twilio_auth_token,
            from_number=config.auth.twilio_phone_number,
        )
    # Default to mock
    if gateway_type != "mock":
        logger.warning("Unknown OTP gateway '%s', falling back to mock", gateway_type)
    return MockOTPGateway()
