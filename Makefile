# --- acceptance_backfill (EVAL_ACCEPTANCE_STANDARD.md P4) ---
# 证据来源: tests/
# 命令逐字取自该来源，未增删任何参数。
.PHONY: eval

eval:
	python3 -m pytest tests -q
