import argparse
import sqlite3


CREATE_FINDINGS_SQL = """
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


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS scans")
    cur.execute("DROP TABLE IF EXISTS findings")
    cur.execute(CREATE_FINDINGS_SQL)
    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize findings.db schema")
    parser.add_argument("--db", default="findings.db", help="SQLite DB path (default: findings.db)")
    args = parser.parse_args()

    init_db(args.db)
    print(f"[+] DB 초기화: {args.db}")


if __name__ == "__main__":
    main()
