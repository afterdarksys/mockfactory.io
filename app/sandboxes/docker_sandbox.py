import docker
import time
import asyncio
from typing import Dict, Any, Optional
from app.core.config import settings
from app.models.execution import Language
import json


class DockerSandbox:
    """
    Secure Docker-based code execution sandbox.
    - No root access
    - No system access
    - Resource limits enforced
    - Container escape detection
    """

    LANGUAGE_IMAGES = {
        Language.PYTHON: "python:3.11-alpine",
        Language.PHP: "php:8.2-cli-alpine",
        Language.PERL: "perl:5.38-slim",
        Language.JAVASCRIPT: "node:20-alpine",
        Language.NODE: "node:20-alpine",
        Language.GO: "golang:1.21-alpine",
        Language.SHELL: "alpine:latest",
        Language.HTML: "nginx:alpine",
    }

    SECURITY_SYSCALLS_BLACKLIST = [
        "clone",
        "unshare",
        "mount",
        "umount",
        "pivot_root",
        "chroot",
        "reboot",
        "sethostname",
        "setdomainname",
    ]

    def __init__(self):
        self.client = docker.from_env()

    async def execute(
        self,
        language: Language,
        code: str,
        timeout: int = None
    ) -> Dict[str, Any]:
        """Execute code in a secure Docker container"""

        if timeout is None:
            timeout = settings.MAX_EXECUTION_TIME

        image = self.LANGUAGE_IMAGES.get(language)
        if not image:
            return {
                "status": "failed",
                "error": f"Unsupported language: {language}",
                "security_violations": []
            }

        # Pull image if not exists
        try:
            self.client.images.get(image)
        except docker.errors.ImageNotFound:
            self.client.images.pull(image)

        container = None
        start_time = time.time()

        try:
            # Create secure container configuration
            container = self.client.containers.run(
                image=image,
                command=self._get_command(language, code),
                detach=True,
                remove=False,
                network_mode="none",  # No network access
                mem_limit=f"{settings.MAX_MEMORY_MB}m",
                memswap_limit=f"{settings.MAX_MEMORY_MB}m",
                cpu_quota=settings.MAX_CPU_QUOTA,
                cpu_period=100000,
                pids_limit=50,
                security_opt=[
                    "no-new-privileges:true",
                    f"seccomp={self._get_seccomp_profile()}"
                ],
                cap_drop=["ALL"],  # Drop all capabilities
                read_only=True,  # Read-only root filesystem
                tmpfs={"/tmp": "size=10M,mode=1777"},  # Small temp space
                user="nobody",  # Run as non-root user
            )

            # Wait for execution with timeout
            result = container.wait(timeout=timeout)
            execution_time_ms = (time.time() - start_time) * 1000

            # Get output
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')
            exit_code = result.get("StatusCode", -1)

            # Check for security violations
            violations = self._detect_violations(container, logs)

            # Get resource usage
            stats = container.stats(stream=False)
            memory_used_mb = stats["memory_stats"].get("usage", 0) / (1024 * 1024)

            return {
                "status": "completed" if exit_code == 0 and not violations else "failed",
                "output": logs[:10000],  # Limit output size
                "exit_code": exit_code,
                "execution_time_ms": execution_time_ms,
                "memory_used_mb": memory_used_mb,
                "security_violations": violations,
                "container_id": container.short_id
            }

        except docker.errors.ContainerError as e:
            return {
                "status": "failed",
                "error": str(e),
                "output": e.stderr.decode('utf-8') if e.stderr else "",
                "execution_time_ms": (time.time() - start_time) * 1000,
                "security_violations": []
            }

        except Exception as e:
            return {
                "status": "failed",
                "error": f"Execution error: {str(e)}",
                "execution_time_ms": (time.time() - start_time) * 1000,
                "security_violations": []
            }

        finally:
            # Cleanup
            if container:
                try:
                    container.remove(force=True)
                except:
                    pass

    def _get_command(self, language: Language, code: str) -> list:
        """Get the command to execute based on language"""

        if language == Language.PYTHON:
            return ["python", "-c", code]
        elif language == Language.PHP:
            return ["php", "-r", code]
        elif language == Language.PERL:
            return ["perl", "-e", code]
        elif language in [Language.JAVASCRIPT, Language.NODE]:
            return ["node", "-e", code]
        elif language == Language.GO:
            # Go requires a file
            return ["sh", "-c", f'echo "{code}" > /tmp/main.go && go run /tmp/main.go']
        elif language == Language.SHELL:
            return ["sh", "-c", code]
        elif language == Language.HTML:
            # For HTML, just echo it
            return ["sh", "-c", f'echo "{code}"']

    def _get_seccomp_profile(self) -> str:
        """Generate seccomp profile to block dangerous syscalls"""
        profile = {
            "defaultAction": "SCMP_ACT_ALLOW",
            "syscalls": [
                {
                    "names": self.SECURITY_SYSCALLS_BLACKLIST,
                    "action": "SCMP_ACT_ERRNO"
                }
            ]
        }

        # Write to temp file
        profile_path = "/tmp/seccomp_profile.json"
        with open(profile_path, "w") as f:
            json.dump(profile, f)

        return profile_path

    def _detect_violations(self, container, logs: str) -> list:
        """Detect container escape attempts and security violations"""
        violations = []

        # Check logs for suspicious patterns
        suspicious_patterns = [
            "permission denied",
            "operation not permitted",
            "capability not permitted",
            "/proc/",
            "/sys/",
            "mount",
            "unshare",
            "chroot",
        ]

        logs_lower = logs.lower()
        for pattern in suspicious_patterns:
            if pattern in logs_lower:
                violations.append(f"Suspicious activity detected: {pattern}")

        # Check container metadata for escape attempts
        try:
            inspect = self.client.api.inspect_container(container.id)

            # Check if process tried to escalate privileges
            if inspect.get("HostConfig", {}).get("Privileged", False):
                violations.append("Privilege escalation attempt detected")

        except Exception as e:
            violations.append(f"Inspection error: {str(e)}")

        return violations
