import sqlite3

conn = sqlite3.connect("spendly.db")
conn.row_factory = sqlite3.Row

def print_table(title, rows):
    if not rows:
        print(f"\n{title}: (empty)")
        return
    cols = rows[0].keys()
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    sep = "+-" + "-+-".join("-" * widths[c] for c in cols) + "-+"
    header = "| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |"
    print(f"\n{title}")
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        print("| " + " | ".join(str(r[c]).ljust(widths[c]) for c in cols) + " |")
    print(sep)

print_table("USERS", conn.execute("SELECT id, name, email, created_at FROM users").fetchall())
print_table("EXPENSES", conn.execute("SELECT id, user_id, amount, category, date, description FROM expenses").fetchall())
conn.close()
