# Letterboxd Unfollower Tracker

A CLI tool that takes daily snapshots of your Letterboxd followers and alerts you when someone unfollows you.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### Start the daily watcher (keeps running, checks every day at 09:00)
```bash
python tracker.py watch <username>
```
Takes a baseline snapshot immediately, then checks again every morning at 09:00.  
Press **Ctrl+C** to stop.

### Take a one-off snapshot and check for unfollowers right now
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

## How it works

1. Scrapes `letterboxd.com/<username>/followers/` (all pages)
2. Stores the follower list in a local SQLite database (`snapshots.db`)
3. On each subsequent check, diffs the new list against the previous snapshot
4. Any username that was present before but is now gone is recorded as an unfollow event

## Notes

- **First run** only captures the baseline — unfollowers appear from the second check onward
- **Private profiles** are detected and skipped gracefully
- **Rate limiting** — the scraper waits ~1.2s between pages to avoid getting blocked
- `snapshots.db` is created automatically in the same folder as `tracker.py`
- To run the watcher persistently in the background, use `screen`, `tmux`, or a systemd service
