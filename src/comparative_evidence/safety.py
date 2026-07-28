from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlsplit


SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
OBSERVATION_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{1,126}[A-Za-z0-9]$")
ALLOWED_LOCATOR_SCHEMES = {"evidence-vault", "s3"}
ALLOWED_DATA_CLASSES = {
    "approved-synthetic-exemplar",
    "approved-synthetic-qualification",
    "redacted-confidential-manifest",
    "redacted-regulated-manifest",
    "synthetic",
}
REDACTION_STATUS = "reviewed-redacted-manifest"

PROTECTED_KEY_PARTS = {
    "accesskey",
    "accesstoken",
    "address",
    "apikey",
    "authorization",
    "bearer",
    "clientsecret",
    "cookie",
    "dateofbirth",
    "dob",
    "email",
    "mrn",
    "name",
    "password",
    "passwd",
    "patientid",
    "phone",
    "privatekey",
    "secret",
    "session",
    "ssn",
    "subjectid",
    "token",
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
)


class EvidenceSafetyError(ValueError):
    """Evidence receives a governed projection path before repository admission."""


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", value).casefold())


def normalize_identity(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceSafetyError(f"{field} requires a bounded textual identity")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not IDENTITY_PATTERN.fullmatch(normalized):
        raise EvidenceSafetyError(
            f"{field} requires 3-128 identity characters from the released identity alphabet"
        )
    return normalized.casefold()


def validate_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise EvidenceSafetyError(f"{field} requires sha256 plus 64 lowercase hexadecimal characters")
    return value


def validate_commit(value: Any) -> str:
    if not isinstance(value, str) or not COMMIT_PATTERN.fullmatch(value):
        raise EvidenceSafetyError("implementation_commit requires an immutable 40- or 64-character Git identity")
    return value


def validate_observation_id(value: Any) -> str:
    if not isinstance(value, str) or not OBSERVATION_ID_PATTERN.fullmatch(value):
        raise EvidenceSafetyError(
            "observation_id requires an uppercase, hyphen-separated repository-safe identity"
        )
    return value


def validate_locator(value: Any) -> str:
    if not isinstance(value, str):
        raise EvidenceSafetyError("governed_locator requires a protected evidence URI")
    parsed = urlsplit(value)
    if parsed.scheme not in ALLOWED_LOCATOR_SCHEMES:
        raise EvidenceSafetyError(
            "governed_locator requires the evidence-vault or s3 protected-storage scheme"
        )
    decoded = unquote(value)
    contains_control = any(ord(character) < 32 or ord(character) == 127 for character in decoded)
    if (
        not parsed.netloc
        or not parsed.path
        or parsed.path == "/"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "%" in value
        or contains_control
    ):
        raise EvidenceSafetyError(
            "governed_locator requires an authority and object path free of encoded, credential, query, or control material"
        )
    return value


def validate_classification(value: dict[str, Any]) -> None:
    if value.get("data_class") not in ALLOWED_DATA_CLASSES:
        raise EvidenceSafetyError("data_class requires a released redacted or synthetic classification")
    if value.get("redaction_status") != REDACTION_STATUS:
        raise EvidenceSafetyError(
            "redaction_status requires the reviewed-redacted-manifest disposition"
        )


def validate_repository_safe_content(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            normalized = normalized_key(key_text)
            control_plane_field = (
                normalized == "productionauthorizationeffect"
                and item == "none"
            ) or (
                normalized == "displayname"
                and path.endswith(".governance_closure.metadata.owner")
                and isinstance(item, str)
                and item.casefold().endswith(" role")
            )
            if not control_plane_field and any(
                part in normalized for part in PROTECTED_KEY_PARTS
            ):
                raise EvidenceSafetyError(
                    f"{path}.{key_text} represents protected content; retain its class and governed locator"
                )
            validate_repository_safe_content(item, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_repository_safe_content(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            raise EvidenceSafetyError(
                f"{path} resembles credential material; retain it in the approved secrets service"
            )
        parsed = urlsplit(value)
        if parsed.scheme and (parsed.username or parsed.password):
            raise EvidenceSafetyError(
                f"{path} contains URI credential material; retain a protected locator"
            )
