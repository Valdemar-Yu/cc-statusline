# cc-statusline

A compact single-line [status line](https://code.claude.com/docs/en/statusline) for **Claude Code** that shows, at a glance:

- 🤖 **Model name** — with a `[1M]` tag when the 1M-token context window is active
- ⚡ **Reasoning effort** — the live `/effort` level (`low` / `medium` / `high` / `xhigh` / `max`)
- 🧠 **Context usage** — a color-coded progress bar (green → yellow → red) with `used% (tokens/size)`
- ⏳ 📅 **Subscription rate limits** — **remaining** % and reset countdown for the **5-hour** and **7-day** windows (Claude.ai Pro/Max)

```
🤖 Opus 4.8 [1M] ⚡high  🧠 █░░░░░░░ 8% (80k/1M)  ⏳ 5h 76% ↻2h14m  📅 7d 59% ↻3d5h
```

Everything degrades gracefully: no `[1M]` on 200k models, no `⚡` when the model doesn't support effort, and the rate-limit segments are omitted until Claude Code provides them (Pro/Max, after the first API response of the session).

## Requirements

- [Claude Code](https://code.claude.com) **v2.1.132+** (uses the official `context_window` / `rate_limits` statusline fields)
- `python3` (ships with macOS; preinstalled on most Linux)

No API keys, no network calls, no reading of credentials — it only consumes the JSON that Claude Code pipes to the status line on stdin.

## Install

```bash
git clone https://github.com/Valdemar-Yu/cc-statusline.git
cd cc-statusline
./install.sh
```

`install.sh` copies `statusline.py` to `~/.claude/statusline.py` and adds the `statusLine` block to `~/.claude/settings.json` (it will not clobber an existing one — it just prints the snippet to add).

### Manual install

1. Copy `statusline.py` anywhere, e.g. `~/.claude/statusline.py`.
2. Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py"
  }
}
```

3. Open a new Claude Code window (the current session won't refresh live).

## Notes

- **Only 5h + 7d windows exist.** Claude exposes a 5-hour rolling window and a 7-day (weekly) window — the same ones shown in the claude.ai web UI. There is no separate "1-day" window.
- **Rate limits are Pro/Max only** and appear after the first API response in a session, so a fresh window shows them a moment later.
- The `⚡effort` color is `38;5;164` (a deep magenta-purple, chosen to stay distinct on light themes). Edit the code in `main()` to taste.

## Customize

Open `statusline.py` — it's ~150 lines of dependency-free Python:

| Want to… | Where |
| --- | --- |
| Change the context bar width | `bar(pct, width=8)` |
| Change colors | the `\033[<code>m` ANSI codes in `c(...)` calls |
| Add cost / git / cwd | append a segment to `parts` in `main()` |
| Show *used* instead of *remaining* rate limit | the `remaining = 100 - ...` line |

## License

MIT
