import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from quant_ranger._impl.helpers import CommandError, get_exec_output_silently
from quant_ranger._impl.logger import Logger


@dataclass(frozen=True, slots=True)
class SandboxAuth:
    """Authentication material that must be forwarded into sandboxed Pixi runs."""

    credential_read_paths: tuple[Path, ...] = ()
    """List of paths to credential files that the sandboxed Pixi process should be able
    to read."""
    credential_env: Mapping[str, str] | None = None
    """Environment variables to set for the sandboxed Pixi process to point it at the
    credential files."""
    redact: tuple[str, ...] = ()
    """Secret values that must be hidden in command logs."""


@dataclass(frozen=True, slots=True)
class KeychainCredential:
    channel_host: str
    """Host key as stored by rattler, including wildcard entries such as
    *.prefix.dev."""

    credential: Mapping[str, JsonValue]
    """Parsed JSON credential, e.g. {'BearerToken':'xxxxxxxxx'}, but also other forms
    possible."""


def prepare_sandbox_auth(
    channel_hosts: Sequence[str],
    logger: Logger,
    *,
    tempdir: Path,
    pixi_info: Mapping[str, JsonValue],
) -> SandboxAuth:
    """Find credentials for the given channel hosts in the macOS Keychain or the rattler
    credentials file."""
    if not channel_hosts:
        return SandboxAuth()

    if sys.platform == "darwin":
        keychain_credentials = _read_macos_keychain_credentials(channel_hosts, logger)
    else:
        logger.debug("No macOS Keychain available for Pixi auth.")
        keychain_credentials = ()

    if keychain_credentials:
        _warn_missing_auth(
            channel_hosts,
            [credential.channel_host for credential in keychain_credentials],
            logger,
        )
        auth_file = (tempdir / "credentials.json").resolve()
        _write_auth_file(keychain_credentials, auth_file)
        return SandboxAuth(
            credential_read_paths=(auth_file,),
            credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
            redact=_credential_secrets(keychain_credentials),
        )

    auth_file = _rattler_credentials_file(pixi_info)
    authenticated_hosts = _credentials_file_auth_hosts(auth_file, channel_hosts, logger)
    if authenticated_hosts:
        _warn_missing_auth(channel_hosts, authenticated_hosts, logger)
        logger.debug(f"Using rattler credentials file for Pixi auth: {auth_file}.")
        return SandboxAuth(
            credential_read_paths=(auth_file,),
            credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
        )

    host_list = ", ".join(channel_hosts)
    logger.warning(
        "Could not find Pixi auth credentials for "
        f"{host_list} in macOS Keychain or {auth_file}."
    )
    return SandboxAuth()


def _read_macos_keychain_credentials(
    channel_hosts: Sequence[str],
    logger: Logger,
) -> tuple[KeychainCredential, ...]:
    credentials: dict[str, Mapping[str, JsonValue]] = {}
    missing_hosts: list[str] = []
    for channel_host in channel_hosts:
        if any(
            _credential_host_matches_channel_host(credential_host, channel_host)
            for credential_host in credentials
        ):
            continue

        found = False
        for credential_host in _credential_host_candidates(channel_host):
            try:
                output = get_exec_output_silently(
                    [
                        "security",
                        "find-generic-password",
                        "-s",
                        "rattler",
                        "-a",
                        credential_host,
                        "-w",
                    ],
                    ignore_return_code=True,
                )
            except CommandError:
                logger.debug("No macOS Keychain available for Pixi auth.")
                return ()

            credential = (
                _extract_rattler_credential(output.stdout)
                if output.exit_code == 0
                else None
            )
            if credential is not None:
                logger.debug(
                    "Using Pixi auth credentials from macOS Keychain for "
                    f"{credential_host}."
                )
                credentials[credential_host] = credential
                found = True
                break

        if not found:
            missing_hosts.append(channel_host)

    if missing_hosts:
        logger.debug(
            "No Pixi auth credentials found in macOS Keychain for "
            f"{', '.join(missing_hosts)}."
        )

    return tuple(
        KeychainCredential(channel_host=credential_host, credential=credential)
        for credential_host, credential in credentials.items()
    )


def _extract_rattler_credential(secret: str) -> Mapping[str, JsonValue] | None:
    secret = secret.strip()
    if not secret:
        return None

    try:
        parsed = json.loads(secret)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        return parsed
    return None


def _write_auth_file(
    keychain_credentials: Sequence[KeychainCredential],
    auth_file: Path,
) -> None:
    contents = {
        keychain_credential.channel_host: keychain_credential.credential
        for keychain_credential in keychain_credentials
    }
    auth_file.write_text(json.dumps(contents, sort_keys=True) + "\n")


def _credential_secrets(
    keychain_credentials: Sequence[KeychainCredential],
) -> tuple[str, ...]:
    secrets: list[str] = []
    for keychain_credential in keychain_credentials:
        secrets.extend(_string_values(keychain_credential.credential))
    return tuple(dict.fromkeys(secrets))


def _string_values(value: JsonValue | Mapping[str, JsonValue]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, Mapping):
        return ()
    return tuple(
        string_value
        for nested_value in value.values()
        for string_value in _string_values(nested_value)
    )


def _rattler_credentials_file(pixi_info: Mapping[str, JsonValue]) -> Path:
    auth_file = os.environ.get("RATTLER_AUTH_FILE")
    if auth_file:
        return Path(auth_file).expanduser().resolve()

    auth_dir = pixi_info.get("auth_dir")
    if isinstance(auth_dir, str):
        return Path(auth_dir).expanduser().resolve()
    return (Path.home() / ".rattler" / "credentials.json").resolve()


def _credentials_file_auth_hosts(
    auth_file: Path,
    channel_hosts: Sequence[str],
    logger: Logger,
) -> tuple[str, ...]:
    if not auth_file.exists():
        logger.debug(f"No rattler credentials file found at {auth_file}.")
        return ()

    try:
        contents = json.loads(auth_file.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid rattler credentials file at {auth_file}.") from error

    if not isinstance(contents, dict):
        raise ValueError(f"Invalid rattler credentials file at {auth_file}.")

    return tuple(
        channel_host
        for channel_host in channel_hosts
        if any(
            isinstance(credential_host, str)
            and _credential_host_matches_channel_host(credential_host, channel_host)
            and isinstance(credentials, dict)
            for credential_host, credentials in contents.items()
        )
    )


def _warn_missing_auth(
    channel_hosts: Sequence[str],
    authenticated_hosts: Sequence[str],
    logger: Logger,
) -> None:
    missing_hosts = tuple(
        host
        for host in channel_hosts
        if not any(
            _credential_host_matches_channel_host(authenticated_host, host)
            for authenticated_host in authenticated_hosts
        )
    )
    if missing_hosts:
        logger.warning(
            "Could not find Pixi auth credentials for "
            f"{', '.join(missing_hosts)}; continuing without them."
        )


def _credential_host_candidates(channel_host: str) -> tuple[str, ...]:
    domain = channel_host.lower()
    candidates = [domain]
    while domain:
        candidates.append(f"*.{domain}")
        parts = domain.split(".", maxsplit=1)
        if len(parts) == 1:
            break
        domain = parts[1]
    return tuple(candidates)


def _credential_host_matches_channel_host(
    credential_host: str,
    channel_host: str,
) -> bool:
    return credential_host.lower() in _credential_host_candidates(channel_host)
