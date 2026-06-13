# 🎬 Letterboxd Unfollower Tracker

A lightweight CLI tool that silently watches your Letterboxd followers and tells you exactly who unfollowed you — and when.

> No API key needed. No account login required. Just your username.

---

## Features

- **Daily automatic snapshots** via APScheduler — set it and forget it
- **Precise diff detection** — compares each snapshot against the last to catch unfollows
- **Persistent history** — every unfollow event is stored with a timestamp in a local SQLite database
- **Private profile detection** — gracefully skips locked accounts
- **Zero config** — one file, one database, runs anywhere Python does

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/letterboxd-unfollower-tracker.git
cd letterboxd-unfollower-tracker
pip install -r requirements.txt
```

---

## Usage

### Start the daily watcher
Captures a baseline immediately, then checks every morning at 09:00.
```bash
python tracker.py watch <username>
```

### Take a manual snapshot right now
```bash
python tracker.py check <username>
```

### View full unfollow history
```bash
python tracker.py history <username>
```

### Clear all stored data for a user
```bash
python tracker.py clear <username>
```

---

## Example Output

```
[2026-06-13 09:00:01] Checking followers for @moss …
  Found 312 follower(s).

  ⚠  2 unfollow(s) detected since last check:
     - https://letterboxd.com/someuser/
     - https://letterboxd.com/anotheruser/
```

```
$ python tracker.py history moss

Unfollow history for @moss (3 event(s)):

  Detected at             User
  ----------------------  ------------------------------
  2026-06-13 09:00:01     https://letterboxd.com/someuser/
  2026-06-13 09:00:01     https://letterboxd.com/anotheruser/
  2026-06-12 09:00:02     https://letterboxd.com/olduser/
```

---

## How It Works

1. Scrapes `letterboxd.com/<username>/followers/` across all pages
2. Saves the full follower list as a snapshot in `snapshots.db`
3. On each subsequent check, diffs the new list against the previous snapshot
4. Any username present before but missing now is recorded as an unfollow event

---

## Running Persistently

To keep the watcher running in the background, use `tmux`:

```bash
tmux new -s letterboxd
python tracker.py watch yourusername
# Ctrl+B then D to detach
```

Or create a systemd service for it to survive reboots.

---

## Notes

- The **first run** only establishes a baseline — unfollowers appear from the second check onward
- Snapshots are stored in `snapshots.db`, created automatically alongside `tracker.py`
- The scraper waits ~1.2s between page requests to avoid rate limiting
- Letterboxd has no official public API — this tool scrapes HTML and may break if their markup changes

---

## Requirements

- Python 3.10+
- `requests`
- `beautifulsoup4`
- `apscheduler`

---

## License

MIT
