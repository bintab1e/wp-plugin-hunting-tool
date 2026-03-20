#!/usr/bin/env python3
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

PLUGINS_DIR = "plugins"
RULES_PATH = "rules.json"
DB_PATH = "findings.db"

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def log_ok(msg):
    print(f"{GREEN}[+]{RESET} {msg}")


def log_err(msg):
    print(f"{RED}[-]{RESET} {msg}")


def run_scan():
    if not os.path.exists(RULES_PATH):
        log_err("rules.json 파일이 없습니다")
        return
    if not os.path.isdir(PLUGINS_DIR):
        log_err("plugins 폴더가 없습니다")
        return

    with open(RULES_PATH, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    rules = []
    for r in data.get("rules", []):
        if r.get("enabled", True):
            rules.append(r)

    php_files = []
    for root, _, names in os.walk(PLUGINS_DIR):
        for name in names:
            if name.lower().endswith(".php"):
                php_files.append(os.path.join(root, name))
    php_files.sort()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 단일 테이블만 유지
    cur.execute("DROP TABLE IF EXISTS scans")
    cur.execute("DROP TABLE IF EXISTS findings")
    cur.execute(
        """
        CREATE TABLE findings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          rule_id TEXT NOT NULL,
          category TEXT NOT NULL,
          plugin TEXT NOT NULL,
          file_path TEXT NOT NULL,
          input_line INTEGER NOT NULL,
          output_line INTEGER NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    total = 0
    log_ok("scan 시작")
    log_ok("rules: " + str(len(rules)))
    log_ok("php files: " + str(len(php_files)))

    for rule in rules:
        rule_id = rule.get("id", "")
        category = rule.get("category", "Unknown")
        input_pattern = rule.get("input_pattern", "")
        output_pattern = rule.get("output_pattern", "")

        log_ok("rule 진행: " + rule_id)

        try:
            input_re = re.compile(input_pattern, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            log_err("input_pattern 컴파일 실패: " + rule_id + " / " + str(e))
            continue

        for file_path in php_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception as e:
                log_err("파일 읽기 실패: " + file_path + " / " + str(e))
                continue

            input_matches = list(input_re.finditer(text))
            if not input_matches:
                continue

            rel = os.path.relpath(file_path, PLUGINS_DIR)
            plugin = rel.split(os.sep)[0] if os.sep in rel else "(root)"

            for im in input_matches:
                dynamic_output = output_pattern
                groups = im.groups()
                for i in range(1, 10):
                    token = "\\" + str(i)
                    if token in dynamic_output:
                        if i <= len(groups) and groups[i - 1] is not None:
                            dynamic_output = dynamic_output.replace(token, re.escape(groups[i - 1]))
                        else:
                            dynamic_output = dynamic_output.replace(token, "")

                try:
                    output_re = re.compile(dynamic_output, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                except re.error as e:
                    log_err("output_pattern 컴파일 실패: " + rule_id + " / " + str(e))
                    continue

                # input 근처에서만 output 검색
                start = max(0, im.start() - 2500)
                end = min(len(text), im.end() + 5000)
                window_text = text[start:end]
                output_matches = list(output_re.finditer(window_text))

                if not output_matches:
                    continue

                input_line = text.count("\n", 0, im.start()) + 1

                for om in output_matches:
                    abs_start = start + om.start()
                    output_line = text.count("\n", 0, abs_start) + 1

                    cur.execute(
                        """
                        INSERT INTO findings(rule_id, category, plugin, file_path, input_line, output_line, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rule_id,
                            category,
                            plugin,
                            file_path,
                            input_line,
                            output_line,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    total += 1

                    print(
                        f"{GREEN}[+]{RESET} {CYAN}{rule_id}{RESET} | {category} | {plugin} | "
                        f"{file_path} | input:L{input_line} | output:L{output_line}"
                    )

        conn.commit()

    log_ok("scan 완료")
    log_ok("총 탐지: " + str(total))
    log_ok("db: " + DB_PATH)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    run_scan()
