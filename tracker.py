#!/usr/bin/env python3
"""
Letterboxd Unfollower Tracker
Usage:
  python tracker.py watch <username>   — start the daily background watcher
  python tracker.py check <username>   — take a snapshot now and show unfollowers
  python tracker.py history <username> — show full unfollow history
  python tracker.py clear <username>   — delete all snapshots for a user
"""

import sys
import sqlite3
import time
import signal
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.blocking import BlockingScheduler

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "snapshots.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
REQUEST_DELAY = 1.2   # seconds between page requests
CHECK_HOUR    = 9     # hour of day to run the daily check (24h, local time)

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    NOT NULL,
                captured_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshot_followers (
                snapshot_id INTEGER NOT NULL,
                follower    TEXT    NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS unfollow_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT NOT NULL,
                unfollower   TEXT NOT NULL,
                detected_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sf_snapshot ON snapshot_followers(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_ue_username ON unfollow_events(username);
        """)


def save_snapshot(username, followers: set) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO snapshots (username, captured_at) VALUES (?, ?)", (username, now)
        )
        snap_id = cur.lastrowid
        db.executemany(
            "INSERT INTO snapshot_followers (snapshot_id, follower) VALUES (?, ?)",
            [(snap_id, f) for f in followers]
        )
    return snap_id


def load_snapshot_followers(snap_id: int) -> set:
    with get_db() as db:
        rows = db.execute(
            "SELECT follower FROM snapshot_followers WHERE snapshot_id = ?", (snap_id,)
        ).fetchall()
    return {r["follower"] for r in rows}


def get_last_two_snapshots(username):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, captured_at FROM snapshots WHERE username = ? ORDER BY id DESC LIMIT 2",
            (username,)
        ).fetchall()
    return rows  # index 0 = newest


def save_unfollow_events(username, unfollowers: list):
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as db:
        db.executemany(
            "INSERT INTO unfollow_events (username, unfollower, detected_at) VALUES (?, ?, ?)",
            [(username, u, now) for u in unfollowers]
        )


def get_unfollow_history(username):
    with get_db() as db:
        return db.execute(
            "SELECT unfollower, detected_at FROM unfollow_events WHERE username = ? ORDER BY detected_at DESC",
            (username,)
        ).fetchall()


def clear_user_data(username):
    with get_db() as db:
        snap_ids = [r[0] for r in db.execute(
            "SELECT id FROM snapshots WHERE username = ?", (username,)
        ).fetchall()]
        if snap_ids:
            db.execute(
                f"DELETE FROM snapshot_followers WHERE snapshot_id IN ({','.join('?'*len(snap_ids))})",
                snap_ids
            )
        db.execute("DELETE FROM snapshots WHERE username = ?", (username,))
        db.execute("DELETE FROM unfollow_events WHERE username = ?", (username,))

# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_follow_list(username: str, kind: str) -> set | None:
    """
    kind: 'followers' or 'following'
    Returns a set of usernames, or None if the profile is private/not found.
    """
    users = set()
    page = 1

    while True:
        url = f"https://letterboxd.com/{username}/{kind}/page/{page}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"  [!] Network error on page {page}: {e}")
            return None

        if r.status_code == 404:
            print(f"  [!] User '{username}' not found (404).")
            return None
        if r.status_code != 200:
            print(f"  [!] Unexpected status {r.status_code} for page {page}.")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Detect private/locked profile
        if soup.select_one(".profile-lock"):
            print(f"  [!] '{username}' has a private profile.")
            return None

        cards = soup.select("table.person-table a.name")
        if not cards:
            break  # no more results

        for a in cards:
            href = a.get("href", "").strip("/")
            if href:
                users.add(href)

        if not soup.select_one("a.next"):
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return users

# ── Core logic ────────────────────────────────────────────────────────────────

def take_snapshot_and_diff(username: str, quiet: bool = False) -> list:
    """
    Scrapes current followers, stores a snapshot, diffs against the previous
    one, persists any unfollow events, and returns the list of unfollowers.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not quiet:
        print(f"\n[{ts}] Checking followers for @{username} …")

    followers = scrape_follow_list(username, "followers")
    if followers is None:
        return []

    if not quiet:
        print(f"  Found {len(followers)} follower(s).")

    snap_id = save_snapshot(username, followers)
    snapshots = get_last_two_snapshots(username)

    if len(snapshots) < 2:
        if not quiet:
            print("  Baseline snapshot saved. Unfollowers will show on the next check.")
        return []

    latest_id = snapshots[0]["id"]
    prev_id   = snapshots[1]["id"]

    latest_set = load_snapshot_followers(latest_id)
    prev_set   = load_snapshot_followers(prev_id)

    unfollowers = sorted(prev_set - latest_set)

    if unfollowers:
        save_unfollow_events(username, unfollowers)
        if not quiet:
            print(f"\n  ⚠  {len(unfollowers)} unfollow(s) detected since last check:")
            for u in unfollowers:
                print(f"     - https://letterboxd.com/{u}/")
    else:
        if not quiet:
            print("  ✓  No unfollowers since last check.")

    return unfollowers

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(username):
    init_db()
    take_snapshot_and_diff(username)


def cmd_watch(username):
    init_db()
    print(f"Starting daily watcher for @{username}.")
    print(f"Snapshots will be taken every day at {CHECK_HOUR:02d}:00.")
    print("Press Ctrl+C to stop.\n")

    # Run once immediately so there's a baseline right away
    take_snapshot_and_diff(username)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        take_snapshot_and_diff,
        trigger="cron",
        hour=CHECK_HOUR,
        minute=0,
        args=[username],
        kwargs={"quiet": False}
    )

    def _shutdown(sig, frame):
        print("\nShutting down watcher…")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    scheduler.start()


def cmd_history(username):
    init_db()
    rows = get_unfollow_history(username)
    if not rows:
        print(f"No unfollow events recorded for @{username} yet.")
        return

    print(f"\nUnfollow history for @{username} ({len(rows)} event(s)):\n")
    print(f"  {'Detected at':<22}  {'User'}")
    print(f"  {'-'*22}  {'-'*30}")
    for r in rows:
        detected = r["detected_at"].replace("T", " ")
        print(f"  {detected:<22}  https://letterboxd.com/{r['unfollower']}/")


def cmd_clear(username):
    init_db()
    confirm = input(f"Delete ALL snapshots and history for @{username}? [y/N] ").strip().lower()
    if confirm == "y":
        clear_user_data(username)
        print(f"Cleared all data for @{username}.")
    else:
        print("Aborted.")

# ── Entry point ───────────────────────────────────────────────────────────────

USAGE = __doc__

def main():
    if len(sys.argv) < 3:
        print(USAGE)
        sys.exit(1)

    command  = sys.argv[1].lower()
    username = sys.argv[2].lower().strip("@")

    dispatch = {
        "watch":   cmd_watch,
        "check":   cmd_check,
        "history": cmd_history,
        "clear":   cmd_clear,
    }

    if command not in dispatch:
        print(f"Unknown command: {command}")
        print(USAGE)
        sys.exit(1)

    dispatch[command](username)


if __name__ == "__main__":
    main()
