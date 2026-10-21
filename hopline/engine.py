from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .generation import Generation, GenerationManager
from .models import Node
from .singbox import build_config

@dataclass(slots=True)
class RunningGeneration:
    generation: Generation
    directory: Path
    process: asyncio.subprocess.Process


class SingBoxEngine:
    def __init__(
        self,
        *,
        binary: str = "sing-box",
        base_port: int = 18771,
        workdir: str | Path | None = None,
        reserved_ports: Iterable[int] = (),
    ) -> None:
        self.binary = binary
        self.base_port = base_port
        self.reserved_ports = frozenset(reserved_ports)
        self.root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="hopline-engine-"))
        self.root.mkdir(parents=True, exist_ok=True)
        for stale in self.root.glob("generation-*"):
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
        self.manager = GenerationManager()
        self._next_generation = 0
        self._active_node_signature: tuple[tuple[object, ...], ...] | None = None
        self._running: dict[str, RunningGeneration] = {}
        self.accepted_node_ids: tuple[str, ...] = ()
        self.rejected_node_ids: tuple[str, ...] = ()

    async def _config_check_passes(self, nodes: list[Node]) -> bool:
        """Return whether sing-box accepts a config built from these nodes."""
        if shutil.which(self.binary) is None:
            raise FileNotFoundError(f"tunnel binary not found: {self.binary}")
        config = build_config(nodes, listen_port=self.base_port)
        with tempfile.TemporaryDirectory(prefix="hopline-check-") as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            check = await asyncio.create_subprocess_exec(
                self.binary,
                "check",
                "-c",
                str(config_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await check.wait()
            return check.returncode == 0

    async def _supported_nodes(self, nodes: list[Node]) -> list[Node]:
        """Keep the nodes sing-box accepts, isolating any single malformed entry."""
        if not nodes:
            return []
        if await self._config_check_passes(nodes):
            return nodes
        if len(nodes) == 1:
            return []
        midpoint = len(nodes) // 2
        left = await self._supported_nodes(nodes[:midpoint])
        right = await self._supported_nodes(nodes[midpoint:])
        return left + right

    async def apply_nodes(self, nodes: list[Node]) -> Generation:
        """Publish a generation only when node connection parameters changed.

        Nodes sing-box rejects are dropped so one malformed entry cannot fail the whole
        generation.
        """
        if not nodes:
            raise ValueError("at least one node is required")
        supported = await self._supported_nodes(list(nodes))
        if not supported:
            raise ValueError("no sing-box-compatible node is available")
        accepted = {node.id for node in supported}
        self.accepted_node_ids = tuple(node.id for node in supported)
        self.rejected_node_ids = tuple(node.id for node in nodes if node.id not in accepted)
        rejected = self.rejected_node_ids
        if rejected:
            preview = ", ".join(rejected[:5])
            tail = f" and {len(rejected) - 5} more" if len(rejected) > 5 else ""
            print(f"hopline: {len(rejected)} node(s) dropped (sing-box-incompatible): {preview}{tail}",
                  file=sys.stderr)
        signature = tuple(
            (
                node.id, node.protocol, node.server, node.port, node.uuid,
                node.tls, node.sni, node.transport_type, node.path, node.host, node.method,
                node.plugin, node.plugin_opts, node.security, node.global_padding,
                node.authenticated_length, node.alter_id, node.packet_encoding, node.flow,
                node.encryption, node.reality_pbk, node.reality_sid, node.reality_spx,
                node.fingerprint, node.alpn, node.allow_insecure, node.service_name,
                node.header_type,
            )
            for node in sorted(supported, key=lambda item: item.id)
        )
        if signature == self._active_node_signature and self.manager.active is not None:
            return self.manager.active
        config = build_config(supported, listen_port=self.base_port)
        previous = self.manager.active
        try:
            generation = await self.start_generation(config)
        except BaseException:
            # A failed start must leave the previous generation serving untouched.
            if previous is not None:
                self._active_node_signature = self._signature_for(previous)
            raise
        generation.credentials = {node.id: node.credential for node in supported}
        self._active_node_signature = signature
        if previous is not None and previous is not generation:
            await self.stop_generation(previous)
        return generation

    def _signature_for(self, generation: Generation) -> tuple[tuple[object, ...], ...] | None:
        """Keep the previous signature so a failed publish retries on the next sync."""
        return self._active_node_signature

    async def start_generation(self, config: dict[str, Any]) -> Generation:
        if shutil.which(self.binary) is None:
            raise FileNotFoundError(f"tunnel binary not found: {self.binary}")
        label = f"generation-{self._next_generation}"
        self._next_generation += 1
        port = self.base_port + self._next_generation - 1
        while port in self.reserved_ports:
            self._next_generation += 1
            port = self.base_port + self._next_generation - 1
        directory = self.root / label
        directory.mkdir(parents=True, exist_ok=False)
        config_copy = json.loads(json.dumps(config))
        config_copy["inbounds"][0]["listen_port"] = port
        config_path = directory / "config.json"
        config_path.write_text(json.dumps(config_copy, indent=2), encoding="utf-8")
        check = await asyncio.create_subprocess_exec(
            self.binary,
            "check",
            "-c",
            str(config_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await check.communicate()
        if check.returncode != 0:
            raise RuntimeError(f"sing-box config rejected: {stderr.decode(errors='replace').strip()}")
        process = await asyncio.create_subprocess_exec(
            self.binary,
            "run",
            "-D",
            str(directory),
            "-c",
            str(config_path),
            "--disable-color",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        generation = Generation(label=label, port=port)
        self._running[label] = RunningGeneration(generation, directory, process)
        try:
            await self._wait_port(port, process)
        except BaseException:
            await self._terminate(process)
            stderr_output = await process.stderr.read() if process.stderr is not None else b""
            self._running.pop(label, None)
            detail = stderr_output.decode(errors="replace").strip()
            raise RuntimeError(
                f"sing-box exited before listener opened: {process.returncode}"
                + (f": {detail}" if detail else "")
            )
        self.manager.publish(generation)
        return generation

    async def stop_generation(self, generation: Generation) -> None:
        running = self._running.get(generation.label)
        if running is None:
            return
        # The gateway releases a lease only after its relay finishes, so this wait is
        # what guarantees no active stream is cut by a generation swap or shutdown.
        generation.accepting = False
        await self.manager.wait_drained(generation)
        await self._terminate(running.process)
        self._running.pop(generation.label, None)
        shutil.rmtree(running.directory, ignore_errors=True)
    async def close(self) -> None:
        for running in tuple(self._running.values()):
            running.generation.accepting = False
        await asyncio.gather(
            *(self.stop_generation(running.generation) for running in tuple(self._running.values()))
        )
        if self.root.name.startswith("hopline-engine-"):
            shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    async def _wait_port(port: int, process: asyncio.subprocess.Process) -> None:
        for _ in range(100):
            if process.returncode is not None:
                raise RuntimeError(f"sing-box exited before listener opened: {process.returncode}")
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", port), 0.1
                )
                writer.close()
                await writer.wait_closed()
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.05)
        raise TimeoutError(f"sing-box listener did not open: {port}")

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
