"""Ad-hoc smoke check: send chat messages and print intent/method/answer."""
import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def post(path, payload, token=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    token = post("/api/auth/login", {"username": "admin", "password": "admin@123"})["access_token"]
    messages = sys.argv[1:] or [
        "whats in demand",
        "what product is in demand",
        "what are ind emand?",
        "what products is in stock",
        "show me all products",
        "what needs to be restocked",
        "how much stock for P0001",
    ]
    for msg in messages:
        r = post("/api/chat", {"message": msg}, token)
        answer = (r.get("message") or "").replace("\n", " ")
        print(f"{msg!r:42} | {str(r.get('intent')):24} | {r.get('parse_method'):14} | {answer[:90]}")


if __name__ == "__main__":
    main()
