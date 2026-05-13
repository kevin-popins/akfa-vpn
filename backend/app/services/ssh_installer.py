from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
import asyncio
import shlex

import asyncssh

from app.core.security import decrypt_secret, mask_secret
from app.models import VpsNode, VpnUser
from app.services.reality import ensure_reality_credentials
from app.services.ssh_host_keys import ssh_connection_options
from app.services.xray_config import render_server_config


READ_ONLY_CHECK_COMMANDS = [
    "echo AKFA_CONNECTION_OK",
    "whoami",
    "id",
    "uname -a",
    "cat /etc/os-release",
    "command -v systemctl || true",
    "command -v curl || true",
    "command -v jq || true",
]

SSH_CONNECT_TIMEOUT_SECONDS = 10
SSH_COMMAND_TIMEOUT_SECONDS = 20
SSH_REMOTE_KILL_AFTER_SECONDS = 10
SSH_LOCAL_TIMEOUT_GRACE_SECONDS = 15
SSH_APT_UPDATE_TIMEOUT_SECONDS = 180
SSH_APT_INSTALL_TIMEOUT_SECONDS = 300
SSH_XRAY_INSTALL_TIMEOUT_SECONDS = 420
SSH_SERVICE_TIMEOUT_SECONDS = 60
APT_LOCK_EXIT_CODE = 73
APT_LOCK_MESSAGE = "На сервере уже выполняется apt/dpkg процесс. Дождитесь завершения или остановите его."


@dataclass
class CommandLog:
    at: datetime
    level: str
    command: str | None
    message: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    mutating: bool = False

    def as_dict(self) -> dict:
        return {
            "at": self.at.isoformat(),
            "level": self.level,
            "command": self.command,
            "message": self.message,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output": "\n".join(part for part in [self.stdout, self.stderr] if part) or None,
            "exit_code": self.exit_code,
            "mutating": self.mutating,
        }


@dataclass
class InstallResult:
    ok: bool
    logs: list[dict] = field(default_factory=list)
    reality_private_key: str | None = None
    reality_public_key: str | None = None
    short_id: str | None = None


class XrayInstaller:
    def __init__(self, node: VpsNode, users: list[VpnUser] | None = None, progress_callback: Callable[[dict], None] | None = None) -> None:
        self.node = node
        self.users = users or []
        self.logs: list[CommandLog] = []
        self.progress_callback = progress_callback

    async def check_connection(self) -> InstallResult:
        try:
            async with await self._connect() as conn:
                self._log("info", None, "Проверка SSH выполняет только read-only команды", mutating=False)
                for command in READ_ONLY_CHECK_COMMANDS:
                    await self._exec(conn, command, mutating=False)
        except Exception as exc:
            self._log("error", None, "Ошибка SSH-подключения", stderr=mask_secret(str(exc)), mutating=False)
            return self._result(False)
        return self._result(True)

    async def verify(self) -> InstallResult:
        commands = [
            "if [ -x /usr/local/bin/xray ]; then /usr/local/bin/xray version; elif command -v xray >/dev/null 2>&1; then xray version; else echo Xray не найден; fi",
            f"systemctl status {self.node.xray_service_name} --no-pager -l",
            f"ls -la {self.node.xray_config_path}",
            f"wc -c {self.node.xray_config_path}",
            f"jq empty {self.node.xray_config_path}",
            f"ss -tulpn | grep ':{self.node.vless_port}' || true",
        ]
        try:
            async with await self._connect() as conn:
                self._log("info", None, "Проверка состояния Xray выполняет только read-only команды", mutating=False)
                for command in commands:
                    await self._exec(conn, command, mutating=False, allow_failure=True)
        except Exception as exc:
            self._log("error", None, "Ошибка SSH-проверки Xray", stderr=mask_secret(str(exc)), mutating=False)
            return self._result(False)
        active = any(
            entry.command and "systemctl status" in entry.command and entry.exit_code == 0
            for entry in self.logs
        )
        return self._result(active)

    async def dry_run(self) -> InstallResult:
        ensure_reality_credentials(self.node)
        render_server_config(self.node, self.users)
        self._log("info", None, "Сформирован валидный план установки Xray-core", mutating=False)
        for command in self.install_plan_commands():
            self._log("info", command, "Сухой запуск: команда не выполнялась", mutating=True)
        return self._result(True)

    async def install(self) -> InstallResult:
        ensure_reality_credentials(self.node)
        try:
            rendered = render_server_config(self.node, self.users)
        except Exception as exc:
            self._log("error", None, "Нельзя применить конфиг: локальная проверка не пройдена", stderr=str(exc), mutating=False)
            return self._result(False)

        config_path = self.node.xray_config_path
        config_dir = str(PurePosixPath(config_path).parent)
        temp_config = f"/tmp/akfa-xray-config-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
        backup_glob = f"{config_path}.akfa.bak.*"
        validate_command = (
            f"if [ -x /usr/local/bin/xray ]; then /usr/local/bin/xray run -test -config {temp_config}; "
            f"elif command -v xray >/dev/null 2>&1; then xray run -test -config {temp_config}; "
            f"else jq empty {temp_config}; fi"
        )
        rollback_command = (
            f"backup=$(ls -1t {backup_glob} 2>/dev/null | head -n 1); "
            f"if [ -n \"$backup\" ]; then cp \"$backup\" {config_path} && chown root:root {config_path} || true; "
            f"chmod 644 {config_path}; systemctl restart {self.node.xray_service_name} || true; fi"
        )

        try:
            async with await self._connect() as conn:
                self._log("info", None, "Начата реальная установка Xray. Только этот путь изменяет VPS.", mutating=True)
                await self._exec(conn, self._apt_lock_check_command(), mutating=False)
                for command in self._package_install_commands():
                    await self._exec(conn, command, mutating=True)
                await self._exec(conn, f"mkdir -p {config_dir}", mutating=True)
                await self._exec(conn, f"cat > {temp_config}", mutating=True, input_data=rendered, log_command=f"cat > {temp_config} <AKFA_XRAY_CONFIG>")
                await self._exec(conn, f"chown root:root {temp_config} || true", mutating=True)
                await self._exec(conn, f"chmod 644 {temp_config}", mutating=True)
                await self._exec(conn, validate_command, mutating=False)
                await self._exec(conn, f"if [ -f {config_path} ]; then cp {config_path} {config_path}.akfa.bak.$(date +%Y%m%d%H%M%S); fi", mutating=True)
                await self._exec(conn, f"cp {temp_config} {config_path}", mutating=True)
                await self._exec(conn, f"chown root:root {config_path} || true", mutating=True)
                await self._exec(conn, f"chmod 644 {config_path}", mutating=True)
                await self._exec(conn, f"systemctl enable {self.node.xray_service_name}", mutating=True)
                await self._exec(conn, f"systemctl restart {self.node.xray_service_name}", mutating=True)
                status = await self._exec(conn, f"systemctl is-active {self.node.xray_service_name}", mutating=False, allow_failure=True)
                await self._exec(conn, f"systemctl status {self.node.xray_service_name} --no-pager -l", mutating=False, allow_failure=True)
                if status.exit_status != 0 or status.stdout.strip() != "active":
                    self._log("error", None, "Сервис Xray не стартовал, выполняется rollback", stderr=mask_secret(status.stderr), mutating=True)
                    await self._exec(conn, rollback_command, mutating=True, allow_failure=True)
                    return self._result(False)
        except Exception as exc:
            self._log("error", None, "Ошибка SSH/установки", stderr=mask_secret(str(exc)), mutating=False)
            return self._result(False)
        return self._result(True)

    async def apply_config(self) -> InstallResult:
        ensure_reality_credentials(self.node)
        try:
            rendered = render_server_config(self.node, self.users)
        except Exception as exc:
            self._log("error", None, "Нельзя применить конфиг: локальная проверка не пройдена", stderr=str(exc), mutating=False)
            return self._result(False)

        config_path = self.node.xray_config_path
        temp_config = f"/tmp/akfa-xray-config-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
        backup_glob = f"{config_path}.akfa.bak.*"
        validate_command = (
            f"if [ -x /usr/local/bin/xray ]; then /usr/local/bin/xray run -test -config {temp_config}; "
            f"elif command -v xray >/dev/null 2>&1; then xray run -test -config {temp_config}; "
            f"else jq empty {temp_config}; fi"
        )
        rollback_command = (
            f"backup=$(ls -1t {backup_glob} 2>/dev/null | head -n 1); "
            f"if [ -n \"$backup\" ]; then cp \"$backup\" {config_path} && chown root:root {config_path} || true; "
            f"chmod 644 {config_path}; systemctl restart {self.node.xray_service_name} || true; fi"
        )

        try:
            async with await self._connect() as conn:
                self._log("info", None, "Применение конфига Xray без переустановки бинарника", mutating=True)
                await self._exec(conn, f"cat > {temp_config}", mutating=True, input_data=rendered, log_command=f"cat > {temp_config} <AKFA_XRAY_CONFIG>")
                await self._exec(conn, f"chown root:root {temp_config} || true", mutating=True)
                await self._exec(conn, f"chmod 644 {temp_config}", mutating=True)
                await self._exec(conn, validate_command, mutating=False)
                await self._exec(conn, f"if [ -f {config_path} ]; then cp {config_path} {config_path}.akfa.bak.$(date +%Y%m%d%H%M%S); fi", mutating=True)
                await self._exec(conn, f"cp {temp_config} {config_path}", mutating=True)
                await self._exec(conn, f"chown root:root {config_path} || true", mutating=True)
                await self._exec(conn, f"chmod 644 {config_path}", mutating=True)
                await self._exec(conn, f"systemctl restart {self.node.xray_service_name}", mutating=True)
                status = await self._exec(conn, f"systemctl is-active {self.node.xray_service_name}", mutating=False, allow_failure=True)
                await self._exec(conn, f"ss -tulpn | grep ':{self.node.vless_port}' || true", mutating=False, allow_failure=True)
                if status.exit_status != 0 or status.stdout.strip() != "active":
                    self._log("error", None, "Сервис Xray не стартовал после применения конфига, выполняется rollback", stderr=mask_secret(status.stderr), mutating=True)
                    await self._exec(conn, rollback_command, mutating=True, allow_failure=True)
                    return self._result(False)
        except Exception as exc:
            self._log("error", None, "Ошибка применения конфига Xray", stderr=mask_secret(str(exc)), mutating=False)
            return self._result(False)
        return self._result(True)

    def install_plan_commands(self) -> list[str]:
        config_path = self.node.xray_config_path
        temp_config = "/tmp/akfa-xray-config-<timestamp>.json"
        return [self._apt_lock_check_command()] + self._package_install_commands() + [
            f"mkdir -p {PurePosixPath(config_path).parent}",
            f"cat > {temp_config} <AKFA_XRAY_CONFIG>",
            f"chown root:root {temp_config} || true",
            f"chmod 644 {temp_config}",
            f"/usr/local/bin/xray run -test -config {temp_config} || jq empty {temp_config}",
            f"if [ -f {config_path} ]; then cp {config_path} {config_path}.akfa.bak.<timestamp>; fi",
            f"cp {temp_config} {config_path}",
            f"chown root:root {config_path} || true",
            f"chmod 644 {config_path}",
            f"systemctl enable {self.node.xray_service_name}",
            f"systemctl restart {self.node.xray_service_name}",
            f"systemctl is-active {self.node.xray_service_name}",
            f"systemctl status {self.node.xray_service_name} --no-pager -l",
        ]

    def apply_config_plan_commands(self) -> list[str]:
        config_path = self.node.xray_config_path
        temp_config = "/tmp/akfa-xray-config-<timestamp>.json"
        return [
            f"cat > {temp_config} <AKFA_XRAY_CONFIG>",
            f"chown root:root {temp_config} || true",
            f"chmod 644 {temp_config}",
            f"/usr/local/bin/xray run -test -config {temp_config} || jq empty {temp_config}",
            f"if [ -f {config_path} ]; then cp {config_path} {config_path}.akfa.bak.<timestamp>; fi",
            f"cp {temp_config} {config_path}",
            f"chown root:root {config_path} || true",
            f"chmod 644 {config_path}",
            f"systemctl restart {self.node.xray_service_name}",
            f"systemctl is-active {self.node.xray_service_name}",
            f"ss -tulpn | grep ':{self.node.vless_port}' || true",
        ]

    def _package_install_commands(self) -> list[str]:
        return [
            "DEBIAN_FRONTEND=noninteractive apt-get update -o Acquire::ForceIPv4=true",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates jq",
            "bash -c \"$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)\" @ install",
        ]

    def _apt_lock_check_command(self) -> str:
        lock_paths = "/var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock"
        return (
            "if pgrep -x apt >/dev/null 2>&1 || pgrep -x apt-get >/dev/null 2>&1 || "
            "pgrep -x dpkg >/dev/null 2>&1 || pgrep -x unattended-upgrade >/dev/null 2>&1; then "
            "ps -eo pid,comm,args | grep -E '[a]pt|[d]pkg|[u]nattended' >&2; "
            f"echo '{APT_LOCK_MESSAGE}' >&2; exit {APT_LOCK_EXIT_CODE}; fi; "
            "if command -v fuser >/dev/null 2>&1 && fuser "
            f"{lock_paths} >/dev/null 2>&1; then "
            f"fuser -v {lock_paths} >&2 || true; "
            f"echo '{APT_LOCK_MESSAGE}' >&2; exit {APT_LOCK_EXIT_CODE}; fi; "
            "echo AKFA_APT_DPKG_OK"
        )

    async def _connect(self) -> asyncssh.SSHClientConnection:
        verifier, options = ssh_connection_options(self.node)
        conn = await asyncio.wait_for(
            asyncssh.connect(
                self.node.ip_address,
                **options,
            ),
            timeout=SSH_CONNECT_TIMEOUT_SECONDS,
        )
        if verifier.accepted_new:
            self._log("info", None, f"SSH fingerprint сохранен: {verifier.fingerprint}", mutating=False)
        elif verifier.matched_existing:
            self._log("info", None, f"SSH fingerprint проверен: {verifier.fingerprint}", mutating=False)
        return conn

    async def _exec(
        self,
        conn: asyncssh.SSHClientConnection,
        command: str,
        *,
        mutating: bool,
        allow_failure: bool = False,
        input_data: str | None = None,
        log_command: str | None = None,
    ):
        displayed = log_command or command
        timeout_seconds = self._timeout_for_command(command)
        remote_command = self._wrap_command_with_timeout(command, timeout_seconds)
        self._log("info", displayed, "Выполняется команда", mutating=mutating)
        try:
            result = await asyncio.wait_for(
                conn.run(remote_command, input=input_data, check=False),
                timeout=timeout_seconds + SSH_LOCAL_TIMEOUT_GRACE_SECONDS,
            )
        except TimeoutError as exc:
            self._log("error", displayed, "Таймаут выполнения SSH-команды, SSH-канал закрывается", stderr=f"{timeout_seconds}s", mutating=mutating)
            conn.close()
            try:
                await asyncio.wait_for(conn.wait_closed(), timeout=5)
            except Exception:
                conn.abort()
            raise RuntimeError(f"{displayed} превысил таймаут {timeout_seconds} секунд") from exc
        if result.exit_status in {124, 137}:
            self._log(
                "error",
                displayed,
                "Таймаут выполнения SSH-команды",
                stdout=result.stdout,
                stderr=f"{displayed} превысил таймаут {timeout_seconds} секунд\n{result.stderr or ''}".strip(),
                exit_code=result.exit_status,
                mutating=mutating,
            )
            raise RuntimeError(f"{displayed} превысил таймаут {timeout_seconds} секунд")
        if result.exit_status == APT_LOCK_EXIT_CODE:
            self._log(
                "error",
                displayed,
                APT_LOCK_MESSAGE,
                stdout=result.stdout,
                stderr=result.stderr or APT_LOCK_MESSAGE,
                exit_code=result.exit_status,
                mutating=mutating,
            )
            raise RuntimeError(APT_LOCK_MESSAGE)
        self._log(
            "info" if result.exit_status == 0 else "error",
            displayed,
            f"Код выхода: {result.exit_status}",
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_status,
            mutating=mutating,
        )
        if result.exit_status != 0 and not allow_failure:
            raise RuntimeError(f"Команда завершилась с ошибкой: {displayed}")
        return result

    def _timeout_for_command(self, command: str) -> int:
        stripped = command.strip()
        if "apt-get update" in stripped:
            return SSH_APT_UPDATE_TIMEOUT_SECONDS
        if "apt-get install" in stripped:
            return SSH_APT_INSTALL_TIMEOUT_SECONDS
        if "install-release.sh" in stripped:
            return SSH_XRAY_INSTALL_TIMEOUT_SECONDS
        if "systemctl restart" in stripped or "systemctl enable" in stripped or "systemctl status" in stripped:
            return SSH_SERVICE_TIMEOUT_SECONDS
        if "xray run -test" in stripped:
            return SSH_SERVICE_TIMEOUT_SECONDS
        return SSH_COMMAND_TIMEOUT_SECONDS

    def _wrap_command_with_timeout(self, command: str, timeout_seconds: int) -> str:
        quoted = shlex.quote(command)
        return f"timeout --kill-after={SSH_REMOTE_KILL_AFTER_SECONDS}s {timeout_seconds}s bash -lc {quoted}"

    def _log(
        self,
        level: str,
        command: str | None,
        message: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        mutating: bool = False,
    ) -> None:
        entry = CommandLog(
            at=datetime.now(timezone.utc),
            level=level,
            command=self._mask(command) if command else None,
            message=self._mask(message),
            stdout=self._mask(stdout)[-4000:] if stdout else None,
            stderr=self._mask(stderr)[-4000:] if stderr else None,
            exit_code=exit_code,
            mutating=mutating,
        )
        self.logs.append(entry)
        if self.progress_callback:
            self.progress_callback(entry.as_dict())

    def _result(self, ok: bool) -> InstallResult:
        self._log("info" if ok else "error", None, "Действие завершено успешно" if ok else "Действие завершилось ошибкой", mutating=False)
        return InstallResult(
            ok=ok,
            logs=[entry.as_dict() for entry in self.logs],
            reality_private_key=self.node.reality_private_key,
            reality_public_key=self.node.reality_public_key,
            short_id=self.node.short_id,
        )

    def _mask(self, value: str) -> str:
        redacted = mask_secret(value)
        for secret in [
            self.node.reality_private_key,
            self.node.short_id,
            decrypt_secret(self.node.encrypted_ssh_password),
            decrypt_secret(self.node.encrypted_private_key),
        ]:
            if secret:
                redacted = redacted.replace(secret, "<secret>")
        return redacted
