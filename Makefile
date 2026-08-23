# qwen lane gates — thin wrappers over lane-gate.sh (read its header). TASK names a brief (briefs/<TASK>.md + .gate).
#   make gate TASK=P0-A1              slice gate: what every brief's "Done means" runs (CI lint mirrors + the brief's named tests)
#   make integrate-gate-fast TASK=…   the same thing; the target name run-qwen.sh looks for
#   make integrate-gate               the LANE gate: CI mirrors (ruff check+format, pnpm lint+build) + every brief's tests
TASK ?= all

.PHONY: gate integrate-gate-fast integrate-gate
gate:
	@./lane-gate.sh $(TASK) fast
integrate-gate-fast:
	@./lane-gate.sh $(TASK) fast
integrate-gate:
	@./lane-gate.sh all full
