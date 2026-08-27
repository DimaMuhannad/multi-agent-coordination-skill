#!/usr/bin/env python3
"""Cross-platform context budget checker.
Checks coordination/roles/*.md sizes against the limit in budget.json.
Emits a non-blocking warning if the limit is exceeded.
"""
import json
import os
import sys

def main():
    # Only run on startup or clear to avoid noise on resume/compact
    if not sys.stdin.isatty():
        try:
            stdin_data = json.loads(sys.stdin.read())
            if stdin_data.get("source") not in ("startup", "clear"):
                return
        except Exception:
            pass

    root = os.getcwd()
    config_path = os.path.join(root, ".claude", "hooks", "budget.json")
    limit = 2400
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                limit = cfg.get("roles_byte_limit", 2400)
        except Exception:
            pass

    roles_dir = os.path.join(root, "coordination", "roles")
    if not os.path.isdir(roles_dir):
        return

    oversized = []
    for fname in os.listdir(roles_dir):
        if fname.endswith(".md"):
            fpath = os.path.join(roles_dir, fname)
            size = os.path.getsize(fpath)
            if size > limit:
                oversized.append(f"{fname} ({size} bytes > {limit} limit)")

    if oversized:
        msg = (
            "[Context Budget Warning] Oversized role files detected:\n"
            + "\n".join(f"  - {x}" for x in oversized) +
            "\n\n*** ИНСТРУКЦИЯ ДЛЯ АГЕНТОВ (LLM) ***\n"
            "Этот лимит носит предупреждающий характер (soft limit) и имеет гистерезис.\n"
            "ЗАПРЕЩАЕТСЯ самостоятельно удалять или агрессивно сжимать важный контекст, чтобы уложиться в бюджет.\n"
            "Если требуется компрессия командных файлов, вы ОБЯЗАНЫ запросить разрешение и инструкции у пользователя (человека, управляющего проектом).\n"
        )
        print(json.dumps({"systemMessage": msg}))

if __name__ == "__main__":
    main()
