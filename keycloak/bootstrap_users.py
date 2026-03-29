#!/usr/bin/env python3
"""Idempotent Keycloak bootstrap for TenderWriter development users."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _env(name: str, default: str) -> str:
    return str(os.getenv(name, default)).strip()


KEYCLOAK_URL = _env("KEYCLOAK_BOOTSTRAP_URL", _env("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")).rstrip("/")
KEYCLOAK_REALM = _env("KEYCLOAK_REALM", "tenderwriter")
KC_ADMIN_USER = _env("KC_ADMIN_USER", "admin")
KC_ADMIN_PASSWORD = _env("KC_ADMIN_PASSWORD", "DefaultKCAdmin2026Pass")
BOOTSTRAP_RETRIES = int(_env("KC_BOOTSTRAP_RETRIES", "60"))
BOOTSTRAP_DELAY_SECONDS = float(_env("KC_BOOTSTRAP_DELAY_SECONDS", "2"))


@dataclass(frozen=True)
class UserSpec:
    username: str
    email: str
    password: str
    first_name: str
    last_name: str
    realm_roles: tuple[str, ...]


USERS: tuple[UserSpec, ...] = (
    UserSpec(
        username=_env("KC_TW_ADMIN_USERNAME", "admin@admin.com"),
        email=_env("KC_TW_ADMIN_EMAIL", "admin@admin.com"),
        password=_env("KC_TW_ADMIN_PASSWORD", "TestPass123!"),
        first_name=_env("KC_TW_ADMIN_FIRST_NAME", "System"),
        last_name=_env("KC_TW_ADMIN_LAST_NAME", "Admin"),
        realm_roles=("tw_admin",),
    ),
    UserSpec(
        username=_env("KC_TW_EDITOR_USERNAME", "registrazioni.hyperknow@gmail.com"),
        email=_env("KC_TW_EDITOR_EMAIL", "registrazioni.hyperknow@gmail.com"),
        password=_env("KC_TW_EDITOR_PASSWORD", "TestPass123!"),
        first_name=_env("KC_TW_EDITOR_FIRST_NAME", "Massimo"),
        last_name=_env("KC_TW_EDITOR_LAST_NAME", "Ferrara"),
        realm_roles=(),
    ),
)

MANAGED_REALM_ROLES = {"tw_admin", "tw_editor", "tw_viewer"}


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict | list | None = None,
    form_body: dict[str, str] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> tuple[int, object | None, dict[str, str]]:
    url = f"{KEYCLOAK_URL}{path}"
    headers: dict[str, str] = {"Accept": "application/json"}
    data: bytes | None = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            payload = response.read()
            parsed = json.loads(payload.decode("utf-8")) if payload else None
            response_headers = {k: v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        if exc.code not in expected_statuses:
            raise RuntimeError(f"{method} {url} -> {exc.code}: {payload}") from exc
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = payload or None
        return exc.code, parsed, {k: v for k, v in exc.headers.items()}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc

    if status not in expected_statuses:
        raise RuntimeError(f"{method} {url} -> unexpected status {status}")

    return status, parsed, response_headers


def _get_admin_token() -> str:
    _, payload, _ = _request(
        "POST",
        "/realms/master/protocol/openid-connect/token",
        form_body={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": KC_ADMIN_USER,
            "password": KC_ADMIN_PASSWORD,
        },
        expected_statuses=(200,),
    )
    access_token = str((payload or {}).get("access_token") or "")
    if not access_token:
        raise RuntimeError("Keycloak admin token missing in response.")
    return access_token


def _wait_until_ready() -> str:
    last_error = "unknown error"
    for attempt in range(1, BOOTSTRAP_RETRIES + 1):
        try:
            token = _get_admin_token()
            _request(
                "GET",
                f"/admin/realms/{KEYCLOAK_REALM}",
                token=token,
                expected_statuses=(200,),
            )
            print(
                f"[keycloak-bootstrap] Keycloak ready at {KEYCLOAK_URL} "
                f"(realm={KEYCLOAK_REALM}, attempt={attempt})."
            )
            return token
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(
                f"[keycloak-bootstrap] Waiting for Keycloak "
                f"(attempt {attempt}/{BOOTSTRAP_RETRIES}): {last_error}"
            )
            time.sleep(BOOTSTRAP_DELAY_SECONDS)
    raise RuntimeError(f"Keycloak did not become ready: {last_error}")


def _find_user(token: str, spec: UserSpec) -> dict | None:
    _, payload, _ = _request(
        "GET",
        f"/admin/realms/{KEYCLOAK_REALM}/users?username={urllib.parse.quote(spec.username)}&exact=true",
        token=token,
        expected_statuses=(200,),
    )
    users = payload if isinstance(payload, list) else []
    for user in users:
        if str(user.get("username", "")).casefold() == spec.username.casefold():
            return user

    _, payload, _ = _request(
        "GET",
        f"/admin/realms/{KEYCLOAK_REALM}/users?email={urllib.parse.quote(spec.email)}&exact=true",
        token=token,
        expected_statuses=(200,),
    )
    users = payload if isinstance(payload, list) else []
    for user in users:
        if str(user.get("email", "")).casefold() == spec.email.casefold():
            return user
    return None


def _create_or_update_user(token: str, spec: UserSpec) -> str:
    existing = _find_user(token, spec)
    payload = {
        "username": spec.username,
        "email": spec.email,
        "firstName": spec.first_name,
        "lastName": spec.last_name,
        "enabled": True,
        "emailVerified": True,
    }

    if existing is None:
        _request(
            "POST",
            f"/admin/realms/{KEYCLOAK_REALM}/users",
            token=token,
            json_body=payload,
            expected_statuses=(201,),
        )
        existing = _find_user(token, spec)
        if existing is None:
            raise RuntimeError(f"User {spec.username} was created but could not be reloaded.")
        print(f"[keycloak-bootstrap] Created user {spec.username}.")
    else:
        user_id = str(existing["id"])
        _request(
            "PUT",
            f"/admin/realms/{KEYCLOAK_REALM}/users/{user_id}",
            token=token,
            json_body=payload,
            expected_statuses=(204,),
        )
        print(f"[keycloak-bootstrap] Updated user {spec.username}.")

    user_id = str(existing["id"])
    _request(
        "PUT",
        f"/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/reset-password",
        token=token,
        json_body={"type": "password", "value": spec.password, "temporary": False},
        expected_statuses=(204,),
    )
    print(f"[keycloak-bootstrap] Ensured password for {spec.username}.")
    return user_id


def _get_role_repr(token: str, role_name: str) -> dict:
    _, payload, _ = _request(
        "GET",
        f"/admin/realms/{KEYCLOAK_REALM}/roles/{urllib.parse.quote(role_name)}",
        token=token,
        expected_statuses=(200,),
    )
    if not isinstance(payload, dict) or not payload.get("name"):
        raise RuntimeError(f"Role {role_name} could not be loaded.")
    return payload


def _sync_roles(token: str, user_id: str, desired_roles: tuple[str, ...], username: str) -> None:
    _, payload, _ = _request(
        "GET",
        f"/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm",
        token=token,
        expected_statuses=(200,),
    )
    current_roles = payload if isinstance(payload, list) else []
    current_role_names = {str(item.get("name")) for item in current_roles}
    desired_role_names = set(desired_roles)

    roles_to_remove = [
        item for item in current_roles
        if str(item.get("name")) in MANAGED_REALM_ROLES and str(item.get("name")) not in desired_role_names
    ]
    if roles_to_remove:
        _request(
            "DELETE",
            f"/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm",
            token=token,
            json_body=roles_to_remove,
            expected_statuses=(204,),
        )
        print(
            f"[keycloak-bootstrap] Removed managed roles from {username}: "
            f"{', '.join(sorted(str(item.get('name')) for item in roles_to_remove))}"
        )

    missing_roles = sorted(desired_role_names - current_role_names)
    if missing_roles:
        _request(
            "POST",
            f"/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm",
            token=token,
            json_body=[_get_role_repr(token, role_name) for role_name in missing_roles],
            expected_statuses=(204,),
        )
        print(f"[keycloak-bootstrap] Assigned roles to {username}: {', '.join(missing_roles)}")


def main() -> int:
    token = _wait_until_ready()
    for spec in USERS:
        user_id = _create_or_update_user(token, spec)
        _sync_roles(token, user_id, spec.realm_roles, spec.username)
    print("[keycloak-bootstrap] Bootstrap completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[keycloak-bootstrap] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
