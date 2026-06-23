from config import get_settings


def platform_jwks_path(merchant_id: str) -> str:
    return f"/api/v1/admin/merchants/{merchant_id}/trust/jwks"


def platform_jwks_url(merchant_id: str) -> str:
    settings = get_settings()
    return f"{settings.api_base_url}{platform_jwks_path(merchant_id)}"


def normalize_jwks_url(jwks_url: str | None, merchant_id: str) -> str | None:
    if not jwks_url:
        return None
    trimmed = jwks_url.strip()
    path = platform_jwks_path(merchant_id)
    if trimmed == path or trimmed.endswith(path):
        return platform_jwks_url(merchant_id)
    return trimmed
