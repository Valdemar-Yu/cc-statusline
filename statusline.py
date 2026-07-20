#!/usr/bin/env python3
"""Claude Code custom statusline (single line).

Layout / 布局:
  🤖 <model> [1M] ⚡<effort>   🧠 <context-bar> <used%> (<used>/<size>)   ⏳ 5h <remaining%> ↻<reset>   📅 7d <remaining%> ↻<reset>   🕐 <date time>

- model name; appends "[1M]" when the model runs the 1M-token context window
  模型名; 1M 上下文窗口时追加 "[1M]"
- ⚡<effort>: live /effort reasoning level (low/medium/high/xhigh/max); hidden when unsupported
  实时 /effort 思考强度; 模型不支持时隐藏
- context bar from official `context_window.used_percentage`, falls back to parsing the transcript
  上下文优先用官方字段, 缺失时回退解析 transcript
- rate limits (`rate_limits.five_hour` / `seven_day`) show REMAINING % + reset countdown;
  Claude.ai Pro/Max only, appears after the first API response; each window degrades gracefully if absent
  额度显示"剩余"% + 重置倒计时; 仅 Pro/Max, 首次 API 响应后出现, 缺失则优雅省略
- 🕐 clock: responsive to terminal width via the COLUMNS env var (Claude Code v2.1.153+).
  Degrades full "YY-MM-DD HH:MM" -> "MM-DD HH:MM" -> "HH:MM" -> hidden as space shrinks.
  时钟按 COLUMNS 宽度分级降级: 完整 -> 去年份 -> 只时间 -> 隐藏

Any error degrades silently — the statusline never crashes. / 任何异常都静默降级。

Reads a JSON session object on stdin, prints one line on stdout.
Docs: https://code.claude.com/docs/en/statusline
"""
import sys, json, os, time, re, unicodedata, shutil
import urllib.request

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def read_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}

def c(txt, code):
    return f"\033[{code}m{txt}\033[0m"

def disp_width(s):
    """Rendered terminal width: ANSI codes count 0, emoji/CJK-wide count 2, rest 1."""
    s = _ANSI_RE.sub("", s)
    w = 0
    for ch in s:
        o = ord(ch)
        if unicodedata.combining(ch) or 0xFE00 <= o <= 0xFE0F:  # combining / variation selector
            continue
        if (unicodedata.east_asian_width(ch) in ("W", "F")
                or 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
                or 0x2300 <= o <= 0x23FF or 0x2B00 <= o <= 0x2BFF):
            w += 2
        else:
            w += 1
    return w

def term_width():
    """Current terminal width: prefer COLUMNS (Claude Code v2.1.153+), fall back to probe/80."""
    try:
        return int(os.environ["COLUMNS"])
    except (KeyError, ValueError):
        return shutil.get_terminal_size((80, 24)).columns

def human(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)

def fmt_model(data, ctx):
    """Model name; annotate 1M context window with '[1M]'."""
    name = (data.get("model") or {}).get("display_name", "Claude")
    mid = (data.get("model") or {}).get("id", "")
    size = ctx[1] if ctx else 0
    is_1m = size >= 1_000_000 or "1m" in mid.lower() or "1m" in name.lower()
    # strip a self-supplied "(1M context)"-style suffix before re-adding a compact tag
    name = re.sub(r"\s*[\(\[][^)\]]*1m[^)\]]*[\)\]]", "", name, flags=re.I).strip()
    return f"{name} [1M]" if is_1m else name

def bar(pct, width=8):
    pct = max(0.0, min(100.0, float(pct or 0)))
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)

def pct_color(remaining):
    """Color a REMAINING percentage: less left -> redder."""
    if remaining > 50: return "32"   # green
    if remaining > 20: return "33"   # yellow
    return "31"                       # red

def used_color(used):
    """Color a USED percentage: more used -> redder."""
    if used < 60: return "32"
    if used < 85: return "33"
    return "31"

def fmt_countdown(resets_at):
    """resets_at is unix seconds -> '2h14m' / '3d5h' / '45m'."""
    try:
        delta = int(resets_at) - int(time.time())
    except Exception:
        return ""
    if delta <= 0:
        return "now"
    d, rem = divmod(delta, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d: return f"{d}d{h}h"
    if h: return f"{h}h{m}m"
    return f"{m}m"

# ---- context: prefer official fields, fall back to the transcript ----
def context_from_official(data):
    cw = data.get("context_window") or {}
    used_pct = cw.get("used_percentage")
    size = cw.get("context_window_size")
    total_in = cw.get("total_input_tokens")
    if used_pct is None or size is None:
        return None
    used_tok = total_in if isinstance(total_in, int) else int(round(size * used_pct / 100))
    return float(used_pct), int(size), int(used_tok or 0)

def context_from_transcript(data):
    path = data.get("transcript_path", "")
    if not path or not os.path.exists(path):
        return None
    used = 0
    try:
        with open(path) as f:
            for line in f:
                try:
                    u = (json.loads(line).get("message") or {}).get("usage")
                except Exception:
                    continue
                if not u:
                    continue
                used = (u.get("input_tokens", 0)
                        + u.get("cache_read_input_tokens", 0)
                        + u.get("cache_creation_input_tokens", 0))
    except Exception:
        return None
    mid = (data.get("model") or {}).get("id", "")
    size = 1_000_000 if "1m" in mid.lower() else 200_000
    return (used / size * 100 if size else 0), size, used

# ---- Kimi Coding Plan quota (fallback when official rate_limits absent) ----
_KIMI_CACHE = os.path.expanduser("~/.claude/.kimi_usage_cache.json")
_KIMI_CACHE_TTL = 120  # seconds between network calls

def _parse_iso(s):
    """'2026-07-19T08:26:44.702772Z' -> unix seconds."""
    try:
        from datetime import datetime, timezone
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None

def kimi_quota():
    """Query api.kimi.com/coding/v1/usages; cached on disk for _KIMI_CACHE_TTL.

    Returns {"five_hour": {...}, "seven_day": {...}} in the same shape the
    rate_limits renderer expects, or None on any failure (silent degrade).
    """
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    if "kimi" not in base or not key:
        return None
    # fresh cache?
    try:
        if time.time() - os.path.getmtime(_KIMI_CACHE) < _KIMI_CACHE_TTL:
            with open(_KIMI_CACHE) as f:
                return json.load(f)
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "https://api.kimi.com/coding/v1/usages",
            headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read())
        out = {}
        for w in d.get("limits") or []:
            win = w.get("window") or {}
            det = w.get("detail") or {}
            if win.get("duration") == 300 and det.get("remaining") is not None:
                out["five_hour"] = {
                    "used_percentage": 100 - float(det["remaining"]),
                    "resets_at": _parse_iso(det.get("resetTime", "")),
                }
        u = d.get("usage") or {}
        if u.get("remaining") is not None:
            out["seven_day"] = {
                "used_percentage": 100 - float(u["remaining"]),
                "resets_at": _parse_iso(u.get("resetTime", "")),
            }
        result = out or None
        if result:
            try:
                with open(_KIMI_CACHE, "w") as f:
                    json.dump(result, f)
            except Exception:
                pass
        return result
    except Exception:
        # network down etc.: serve stale cache if we have one
        try:
            with open(_KIMI_CACHE) as f:
                return json.load(f)
        except Exception:
            return None

def main():
    data = read_input()

    # ---- model + effort ----
    ctx = context_from_official(data) or context_from_transcript(data)
    model_seg = c(f"🤖 {fmt_model(data, ctx)}", "1;36")
    effort = (data.get("effort") or {}).get("level")
    if effort:
        model_seg += " " + c(f"⚡{effort}", "1;38;5;164")  # deep magenta-purple
    parts = [model_seg]

    # ---- context bar ----
    if ctx:
        used_pct, size, used_tok = ctx
        size_label = "1M" if size >= 1_000_000 else f"{size//1000}k"
        parts.append(
            c("🧠 " + bar(used_pct), used_color(used_pct))
            + f" {used_pct:.0f}% "
            + c(f"({human(used_tok)}/{size_label})", "90")
        )

    # ---- rate limits (may be absent) ----
    rl = data.get("rate_limits") or {}
    if not (rl.get("five_hour") or rl.get("seven_day")):
        rl = kimi_quota() or {}
    for key, label, emoji in (("five_hour", "5h", "⏳"), ("seven_day", "7d", "📅")):
        w = rl.get(key)
        if not w or w.get("used_percentage") is None:
            continue
        remaining = 100 - float(w["used_percentage"])
        txt = f"{emoji} {label} " + c(f"{remaining:.0f}%", pct_color(remaining))
        cd = fmt_countdown(w.get("resets_at")) if w.get("resets_at") else ""
        if cd:
            txt += c(f" ↻{cd}", "90")
        parts.append(txt)

    # ---- clock (rightmost), responsive to terminal width ----
    # kept live between events by "refreshInterval" in settings; COLUMNS injected by Claude Code
    SEP = "  "
    base_w = disp_width(SEP.join(parts))
    lt = time.localtime()
    variants = [
        time.strftime("%y-%m-%d %H:%M", lt),  # 26-07-16 10:49
        time.strftime("%m-%d %H:%M", lt),     # 07-16 10:49
        time.strftime("%H:%M", lt),           # 10:49
    ]
    avail = term_width() - base_w - disp_width(SEP) - 1  # -1 margin to avoid edge wrap
    for v in variants:
        seg_txt = f"🕐 {v}"
        if disp_width(seg_txt) <= avail:
            parts.append(c(seg_txt, "90"))
            break
    # if even "HH:MM" won't fit, the clock is omitted entirely

    sys.stdout.write(SEP.join(parts))

if __name__ == "__main__":
    main()
