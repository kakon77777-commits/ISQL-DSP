import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.bridge import decode_decimal_bytes, to_registered_core_program_envelope
from isql_dsr.canonical import state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.program import decode_program, encode_program, program_from_stream
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream


class ProgramBridgeCLIV06Tests(unittest.TestCase):
    def run_cli(self, args):
        from isql_dsr.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(args)
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    @staticmethod
    def write_json(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_program_core_envelope_is_exec_r4_dsrp_and_lossless(self):
        base = SemanticState(identity="obj:program-bridge")
        event = TransitionEvent(
            event_id="e1",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(4)).to_dict()},
            base_revision=0,
            previous_hash=state_hash(base),
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        registry = extend_registry_for_events(registry, (event,))
        registry, program_ref = registry.intern_text(SymbolNamespace.PROGRAM_ID, "prog")
        registry, instruction_ref = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "i1")
        genesis = compile_registered_state(base, registry)
        stream = build_event_stream(base, (event,), registry)
        program = program_from_stream(stream, registry, program_ref, (instruction_ref,))
        env = to_registered_core_program_envelope(program, genesis)
        self.assertEqual((env.domain, env.resolution, env.control), ("EXEC", "R4", "DSRP"))
        self.assertTrue(env.payload_digits.isascii() and env.payload_digits.isdigit())
        self.assertEqual(decode_decimal_bytes(env.payload_digits), encode_program(program))
        self.assertTrue(env.wire.startswith("ISQL1:EXEC:R4:DSRP"))

    def test_cli_builds_runs_and_bridges_program_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            base = SemanticState(identity="obj:program-cli")
            event = TransitionEvent(
                event_id="e1",
                operation="upsert_axis",
                payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(7)).to_dict()},
                base_revision=0,
                previous_hash=state_hash(base),
            )
            base_json = td / "base.json"
            events_json = td / "events.json"
            registry_path = td / "symbols.isqlr"
            genesis_path = td / "genesis.isqln"
            stream_path = td / "history.isqle"
            program_path = td / "program.isqlp"
            final_path = td / "final.isqln"
            self.write_json(base_json, base.to_dict())
            self.write_json(events_json, [event.to_dict()])

            self.run_cli([
                "registry-build", "--state", str(base_json), "--events", str(events_json),
                "--program-id", "prog", "--instruction-id", "i1",
                "--out", str(registry_path),
            ])
            self.run_cli(["registered-pack", "--state", str(base_json), "--registry", str(registry_path), "--out", str(genesis_path)])
            self.run_cli(["stream-pack", "--genesis", str(base_json), "--events", str(events_json), "--registry", str(registry_path), "--out", str(stream_path)])
            packed = self.run_cli([
                "program-pack", "--registry", str(registry_path), "--genesis-native", str(genesis_path),
                "--stream", str(stream_path), "--program-id", "prog", "--instruction-id", "i1", "--out", str(program_path),
            ])
            self.assertEqual(packed["schema"], "isql.dsr-program-artifact/v0.6")
            self.assertEqual(packed["instructions"], 1)

            ran = self.run_cli([
                "program-run", "--registry", str(registry_path), "--genesis-native", str(genesis_path),
                "--program", str(program_path), "--out", str(final_path),
            ])
            self.assertEqual(ran["status"], 1)
            inspected = self.run_cli(["registered-inspect", "--native", str(final_path), "--registry", str(registry_path)])
            self.assertEqual(inspected["axes"][0]["key"], "risk")

            bridged = self.run_cli([
                "program-bridge", "--registry", str(registry_path), "--genesis-native", str(genesis_path), "--program", str(program_path)
            ])
            self.assertEqual((bridged["domain"], bridged["resolution"], bridged["control"]), ("EXEC", "R4", "DSRP"))
            self.assertTrue(bridged["payload_digits"].isdigit())


if __name__ == "__main__":
    unittest.main()
