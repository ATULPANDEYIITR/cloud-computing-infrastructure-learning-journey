#!/usr/bin/env python3
"""
Docker Images and Dockerfiles
Image layers, Dockerfile instructions, image building, and optimization.

Uses the Python standard library and optionally the Docker CLI.
Compatible with Python 3.10+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class InstructionType(Enum):
    FROM = "FROM"
    RUN = "RUN"
    COPY = "COPY"
    ADD = "ADD"
    WORKDIR = "WORKDIR"
    ENV = "ENV"
    ARG = "ARG"
    EXPOSE = "EXPOSE"
    USER = "USER"
    CMD = "CMD"
    ENTRYPOINT = "ENTRYPOINT"
    LABEL = "LABEL"
    HEALTHCHECK = "HEALTHCHECK"
    VOLUME = "VOLUME"
    SHELL = "SHELL"
    OTHER = "OTHER"


class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class Instruction:
    number: int
    command: str
    arguments: str

    @property
    def instruction_type(self) -> InstructionType:
        try:
            return InstructionType(self.command.upper())
        except ValueError:
            return InstructionType.OTHER


@dataclass
class Layer:
    index: int
    instruction: Instruction
    cache_key: str
    estimated_size_mb: float
    cacheable: bool = True


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    line: Optional[int] = None


@dataclass
class BuildResult:
    image_name: str
    layers: list[Layer]
    total_size_mb: float
    cache_hits: int
    cache_misses: int
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "image": self.image_name,
            "layers": [
                {
                    "index": layer.index,
                    "instruction": layer.instruction.command,
                    "arguments": layer.instruction.arguments,
                    "cache_key": layer.cache_key,
                    "estimated_size_mb": round(
                        layer.estimated_size_mb, 2
                    ),
                    "cacheable": layer.cacheable,
                }
                for layer in self.layers
            ],
            "total_size_mb": round(self.total_size_mb, 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "findings": [
                {
                    "severity": finding.severity.value,
                    "code": finding.code,
                    "message": finding.message,
                    "line": finding.line,
                }
                for finding in self.findings
            ],
        }


class DockerfileError(Exception):
    """Raised when a Dockerfile cannot be parsed or validated."""


class DockerfileParser:
    """Parse logical Dockerfile instructions, including continuations."""

    INSTRUCTION_PATTERN = re.compile(
        r"^([A-Za-z]+)\s*(.*)$",
        re.DOTALL,
    )

    def parse(self, content: str) -> list[Instruction]:
        if not isinstance(content, str):
            raise DockerfileError("Dockerfile content must be text.")

        instructions = []
        logical_lines = []
        buffer = ""

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if line.endswith("\\"):
                buffer += line[:-1] + " "
                continue

            buffer += line
            logical_lines.append(buffer.strip())
            buffer = ""

        if buffer.strip():
            raise DockerfileError(
                "Dockerfile ends with an incomplete continuation."
            )

        for number, line in enumerate(logical_lines, start=1):
            match = self.INSTRUCTION_PATTERN.match(line)

            if not match:
                raise DockerfileError(
                    f"Invalid instruction at logical line {number}."
                )

            command = match.group(1).upper()
            arguments = match.group(2).strip()

            try:
                InstructionType(command)
            except ValueError:
                raise DockerfileError(
                    f"Unsupported Dockerfile instruction: {command}"
                )

            if not arguments:
                raise DockerfileError(
                    f"Missing arguments for {command}."
                )

            instructions.append(
                Instruction(number, command, arguments)
            )

        if not instructions:
            raise DockerfileError("Dockerfile contains no instructions.")

        if instructions[0].command != "FROM":
            raise DockerfileError(
                "The first instruction must be FROM."
            )

        return instructions


class DockerfileAnalyzer:
    """Analyze Dockerfile correctness, security, and optimization."""

    SENSITIVE_ENV = re.compile(
        r"(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)",
        re.IGNORECASE,
    )

    def analyze(
        self,
        instructions: list[Instruction],
    ) -> list[Finding]:
        findings = []

        if not instructions:
            return [
                Finding(
                    Severity.ERROR,
                    "EMPTY_DOCKERFILE",
                    "No Dockerfile instructions found.",
                )
            ]

        first_from = instructions[0]

        if first_from.command == "FROM":
            if re.search(
                r":latest(?:\s|$)",
                first_from.arguments,
                re.IGNORECASE,
            ):
                findings.append(
                    Finding(
                        Severity.WARNING,
                        "UNPINNED_BASE_IMAGE",
                        "Avoid the mutable latest image tag.",
                        first_from.number,
                    )
                )

            if "scratch" in first_from.arguments.lower():
                findings.append(
                    Finding(
                        Severity.INFO,
                        "SCRATCH_BASE",
                        "The image uses an empty scratch base.",
                        first_from.number,
                    )
                )

        run_commands = [
            item for item in instructions
            if item.command == "RUN"
        ]

        for item in instructions:
            args = item.arguments

            if item.command == "ADD":
                findings.append(
                    Finding(
                        Severity.WARNING,
                        "ADD_USAGE",
                        "Prefer COPY unless ADD extraction or URL behavior is required.",
                        item.number,
                    )
                )

            if item.command == "RUN":
                lower = args.lower()

                if "apt-get update" in lower:
                    if "apt-get install" not in lower:
                        findings.append(
                            Finding(
                                Severity.WARNING,
                                "PACKAGE_CACHE",
                                "Combine package index updates and installation in one RUN instruction.",
                                item.number,
                            )
                        )

                    if not re.search(
                        r"rm\s+-rf\s+/var/lib/apt/lists",
                        lower,
                    ):
                        findings.append(
                            Finding(
                                Severity.WARNING,
                                "PACKAGE_CLEANUP",
                                "Remove package-manager metadata after installation.",
                                item.number,
                            )
                        )

                if re.search(
                    r"\b(curl|wget)\b.*\|\s*(sh|bash)",
                    args,
                    re.IGNORECASE,
                ):
                    findings.append(
                        Finding(
                            Severity.WARNING,
                            "REMOTE_SCRIPT_EXECUTION",
                            "Download and verify remote scripts before execution.",
                            item.number,
                        )
                    )

                if "pip install" in lower and "--no-cache-dir" not in lower:
                    findings.append(
                        Finding(
                            Severity.INFO,
                            "PIP_CACHE",
                            "Consider pip install --no-cache-dir.",
                            item.number,
                        )
                    )

            if item.command == "ENV":
                name = args.split("=", 1)[0].split()[0]

                if self.SENSITIVE_ENV.search(name):
                    findings.append(
                        Finding(
                            Severity.ERROR,
                            "POSSIBLE_SECRET",
                            f"Do not store credentials in ENV: {name}.",
                            item.number,
                        )
                    )

                if name.upper() == "PATH" and "=" in args:
                    findings.append(
                        Finding(
                            Severity.INFO,
                            "PATH_CONFIGURATION",
                            "Verify that PATH preserves required system directories.",
                            item.number,
                        )
                    )

            if item.command == "USER":
                if args.lower() in ("root", "0"):
                    findings.append(
                        Finding(
                            Severity.WARNING,
                            "ROOT_RUNTIME",
                            "Run the application as a non-root user.",
                            item.number,
                        )
                    )

            if item.command == "FROM":
                if re.search(
                    r"\s+as\s+",
                    args,
                    re.IGNORECASE,
                ):
                    findings.append(
                        Finding(
                            Severity.INFO,
                            "MULTI_STAGE",
                            "A named build stage is present.",
                            item.number,
                        )
                    )

        if not any(
            item.command in ("CMD", "ENTRYPOINT")
            for item in instructions
        ):
            findings.append(
                Finding(
                    Severity.WARNING,
                    "NO_START_COMMAND",
                    "Define CMD or ENTRYPOINT for an application image.",
                )
            )

        if not any(
            item.command == "USER"
            for item in instructions
        ):
            findings.append(
                Finding(
                    Severity.WARNING,
                    "NO_EXPLICIT_USER",
                    "Specify a non-root runtime USER where possible.",
                )
            )

        if len(run_commands) > 8:
            findings.append(
                Finding(
                    Severity.INFO,
                    "MANY_RUN_INSTRUCTIONS",
                    "Review RUN instructions for unnecessary layer creation.",
                )
            )

        return findings


class ImageBuilder:
    """
    Educational image-layer estimator.

    The model does not reproduce Docker's internal build engine.
    It approximates layer creation, cache keys, and size contributions.
    """

    SIZE_ESTIMATES = {
        "FROM": 120.0,
        "RUN": 12.0,
        "COPY": 8.0,
        "ADD": 8.0,
        "WORKDIR": 0.0,
        "ENV": 0.0,
        "ARG": 0.0,
        "EXPOSE": 0.0,
        "USER": 0.0,
        "CMD": 0.0,
        "ENTRYPOINT": 0.0,
        "LABEL": 0.0,
        "HEALTHCHECK": 0.0,
        "VOLUME": 0.0,
        "SHELL": 0.0,
    }

    def __init__(self):
        self.cache: dict[str, float] = {}

    @staticmethod
    def make_cache_key(
        instruction: Instruction,
        parent_key: str,
    ) -> str:
        material = (
            f"{parent_key}|"
            f"{instruction.command}|"
            f"{instruction.arguments}"
        )

        return hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()

    def build(
        self,
        instructions: list[Instruction],
        image_name: str,
    ) -> BuildResult:
        if not image_name.strip():
            raise ValueError("Image name cannot be empty.")

        layers = []
        cache_hits = 0
        cache_misses = 0
        parent_key = "empty-base"

        for index, instruction in enumerate(
            instructions,
            start=1,
        ):
            key = self.make_cache_key(
                instruction,
                parent_key,
            )

            cacheable = True

            if instruction.command == "RUN":
                if "--no-cache" in instruction.arguments:
                    cacheable = False

            if cacheable and key in self.cache:
                size = self.cache[key]
                cache_hits += 1
            else:
                size = self.SIZE_ESTIMATES.get(
                    instruction.command,
                    0.0,
                )

                if cacheable:
                    self.cache[key] = size

                cache_misses += 1

            layers.append(
                Layer(
                    index=index,
                    instruction=instruction,
                    cache_key=key,
                    estimated_size_mb=size,
                    cacheable=cacheable,
                )
            )

            parent_key = key

        findings = DockerfileAnalyzer().analyze(
            instructions
        )

        return BuildResult(
            image_name=image_name,
            layers=layers,
            total_size_mb=sum(
                layer.estimated_size_mb
                for layer in layers
            ),
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            findings=findings,
        )


class DockerCLI:
    """Safe wrapper around selected Docker CLI operations."""

    def __init__(self, timeout: int = 600):
        self.timeout = timeout

    @staticmethod
    def available() -> bool:
        return shutil.which("docker") is not None

    def run(self, arguments: list[str]) -> str:
        if not self.available():
            raise RuntimeError(
                "Docker CLI is not installed or not available in PATH."
            )

        result = subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
            shell=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Docker command failed:\n"
                + result.stderr.strip()
            )

        return result.stdout.strip()

    def build(
        self,
        directory: Path,
        tag: str,
        dockerfile: str = "Dockerfile",
    ) -> str:
        if not directory.is_dir():
            raise ValueError("Build directory does not exist.")

        if not tag.strip():
            raise ValueError("Image tag cannot be empty.")

        return self.run(
            [
                "build",
                "--file",
                dockerfile,
                "--tag",
                tag,
                str(directory.resolve()),
            ]
        )

    def inspect(self, image: str) -> dict:
        output = self.run(
            ["image", "inspect", image]
        )

        data = json.loads(output)

        if not data:
            raise RuntimeError("Docker returned empty inspection data.")

        return data[0]

    def history(self, image: str) -> str:
        return self.run(
            ["image", "history", image]
        )


SAMPLE_DOCKERFILE = r"""
# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY . .

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /app /app

RUN useradd --create-home appuser

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "main.py"]
"""


def demonstrate() -> None:
    print("=" * 65)
    print("DOCKER IMAGE AND DOCKERFILE ANALYZER")
    print("=" * 65)

    parser = DockerfileParser()

    instructions = parser.parse(
        SAMPLE_DOCKERFILE
    )

    print("\n1. Parsed Dockerfile instructions")

    for instruction in instructions:
        print(
            f"{instruction.number:02d}. "
            f"{instruction.command:<12} "
            f"{instruction.arguments}"
        )

    print("\n2. Dockerfile analysis")

    findings = DockerfileAnalyzer().analyze(
        instructions
    )

    for finding in findings:
        print(
            f"[{finding.severity.value}] "
            f"{finding.code}: {finding.message}"
        )

    print("\n3. Simulated image build")

    builder = ImageBuilder()

    first_build = builder.build(
        instructions,
        "inventory-api:v1",
    )

    print(
        f"Estimated image size: "
        f"{first_build.total_size_mb:.2f} MB"
    )

    print(
        f"Cache hits: {first_build.cache_hits}, "
        f"cache misses: {first_build.cache_misses}"
    )

    second_build = builder.build(
        instructions,
        "inventory-api:v2",
    )

    print(
        f"Second build cache hits: "
        f"{second_build.cache_hits}"
    )

    print("\n4. Layer details")

    for layer in first_build.layers:
        print(
            f"Layer {layer.index}: "
            f"{layer.instruction.command:<12} "
            f"{layer.estimated_size_mb:>7.2f} MB"
        )

    print("\n5. Machine-readable report")

    print(
        json.dumps(
            first_build.to_dict(),
            indent=2,
        )
    )

    print("\n6. Optimization comparison")

    original = """
FROM python:3.12
COPY . /app
WORKDIR /app
RUN apt-get update
RUN apt-get install -y gcc
RUN pip install flask
CMD ["python", "app.py"]
"""

    optimized = """
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 10001
EXPOSE 8000
CMD ["python", "app.py"]
"""

    for name, content in [
        ("Original", original),
        ("Optimized", optimized),
    ]:
        parsed = parser.parse(content)
        report = builder.build(
            parsed,
            name.lower(),
        )

        print(
            f"{name}: "
            f"{len(parsed)} instructions, "
            f"{report.total_size_mb:.2f} estimated MB, "
            f"{len(report.findings)} findings"
        )


def inspect_real_image(image: str) -> None:
    docker = DockerCLI()

    print("\nReal Docker image inspection")

    metadata = docker.inspect(image)

    print(
        json.dumps(
            {
                "id": metadata.get("Id"),
                "repo_tags": metadata.get("RepoTags"),
                "size_bytes": metadata.get("Size"),
                "architecture": metadata.get("Architecture"),
                "os": metadata.get("Os"),
            },
            indent=2,
        )
    )

    print("\nDocker image history")

    print(docker.history(image))


def main() -> None:
    command_parser = argparse.ArgumentParser(
        description="Dockerfile analysis and image-layer simulation."
    )

    command_parser.add_argument(
        "--dockerfile",
        type=Path,
        help="Path to an existing Dockerfile.",
    )

    command_parser.add_argument(
        "--image",
        help="Inspect an existing local Docker image.",
    )

    command_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the image using the Docker CLI.",
    )

    command_parser.add_argument(
        "--tag",
        default="docker-learning:latest",
        help="Image tag for a real Docker build.",
    )

    command_parser.add_argument(
        "--context",
        type=Path,
        default=Path("."),
        help="Docker build context directory.",
    )

    args = command_parser.parse_args()

    try:
        if args.dockerfile:
            content = args.dockerfile.read_text(
                encoding="utf-8"
            )

            instructions = DockerfileParser().parse(
                content
            )

            result = ImageBuilder().build(
                instructions,
                args.tag,
            )

            print(
                json.dumps(
                    result.to_dict(),
                    indent=2,
                )
            )

        else:
            demonstrate()

        if args.build:
            output = DockerCLI().build(
                args.context,
                args.tag,
                (
                    str(args.dockerfile.resolve())
                    if args.dockerfile
                    else "Dockerfile"
                ),
            )

            print("\nActual Docker build output:")
            print(output)

        if args.image:
            inspect_real_image(args.image)

    except (
        DockerfileError,
        ValueError,
        RuntimeError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    demonstrate()
