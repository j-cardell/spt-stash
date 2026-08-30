# AI Slop Notes — SPT Stash (ui-rework)

> **Status: RESOLVED** — all findings below were fixed in the slop-cleanup pass
> (see plan `2026-08-30_221500-ai-slop-cleanup.md`). This file is retained as a
> record of what was cleaned up. The only outstanding item is a final screenshot
> review to visually confirm the theme-token refactor (colors should be
> pixel-identical, since tokens evaluate to the same hex values).

Audit pass over the codebase for tell-tale AI-generated / copy-paste cruft.
Not a refactor — just an inventory of what looks like slop, ready to clean up.
All findings verified against the current tree. Line numbers are as of the
`b160017` commit.

---

## 1. Bypassed design-token system (biggest one) — ✅ FIXED

`theme.py` defines the full V4 palette as named constants
(`BG`, `SURFACE`, `ACCENT`, `SUCCESS`, …), but the UI files mostly ignore it.

- `theme.py`: 12→20 hex literals (the *definitions* — fine)
- `styles.py`: 2
- `main_window.py`: 6
- `widgets.py`: 27
- `dialogs.py`: 59
- `presets.py`: 37
- `installer.py`: 16
- `performance.py`: 14
- `browse.py`: 27
- `installed.py`: 48

**≈ 230 hardcoded hex codes** scattered through inline `setStyleSheet()` and
f-string HTML, when `theme.ACCENT`, `theme.TEXT_MUTED` etc. already exist.

Why it's slop: the palette is duplicated in ~10 places, so any color tweak
(say, dimming the accent) becomes a grep across six files instead of a one-line
change. This is the signature AI habit of "just inline the value", and it's
exactly what makes the V4 polish so tedious to iterate on.

**Cleanup:** import tokens into `widgets.dialogs/browse/installed/…` and stop
hardcoding. The `rgba()` dims and status colors are the worst offenders.

---

## 2. Literal duplicate line(s)

- `browse.py:482-483` — `self.load_installed_mods()` runs **twice** in a row
  (in the "enable disabled deps" branch of `start_mod_download`). One is dead.

- `staging/metadata.py:35,45,46` — three separate `return None` paths where two
  are reachable from the same call; the final `return None` at line 46 is the
  only one that matters. Lines 44-45 duplicate it.

---

## 3. `except Exception: pass` — silent exception swallows

22 instances project-wide of broad `except` with an empty/`pass` body. Several
are genuinely best-effort (a cache lookup that must not crash), but many hide
real failures — especially in the UI paths, where a broken render or a failed
download just dies silently:

- `config.py:25` — config load failure silently returns bare `defaults`.
- `paths.py:58` — swallows the whole config-file read on startup; a corrupt
  config vanishes with no trace.
- `staging/workers.py:106,154,170,238` — staging / symlink errors are passed.
- `ui/widgets.py:386,558`, `browse.py:591,603,635`,
  `presets.py:160`, `dialogs.py:215`, `main_window.py:232`,
  `matching.py:86`, `system/hardware.py:24,87`, `system/process.py:22,24,39`.

**Cleanup:** at minimum change the UI-path ones to log / toast. At most,
narrow `except` to the specific failure you expect instead of catching
`Exception` at large.

---

## 4. Copy-pasted "unlink symlink-or-dir" ladder

The same ~6-line block appears **20 times** across the codebase:

```python
if path.is_symlink() or path.exists():
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)
```

- `staging/links.py:15-16,30-31`
- `browse.py:417-418,433-434,474-475`
- `installed.py:650-651,656-657,1075-1076,1098-1099,1105-1106`

Also note the inner condition is redundant — `is_symlink()` is already checked
in the outer `if`, so the `or not path.is_dir()` branch logic is muddled
(symlinks aren't dirs, so a symlink always hits `unlink()`; the `rmtree` branch
is effectively dead for symlinks).

**Cleanup:** one helper `remove_path(p)` in `staging/links.py`, call it from the
other 19 spots.

---

## 5. "Comment restates code" noise

Several comments just say what the next line obviously does:

- `main_window.py:74` `# sidebar` → `sidebar = QFrame()`
- `main_window.py:81` `# brand row` → `brand_row = QHBoxLayout()`
- `presets.py:49` `# top row` → `top_row = QHBoxLayout()`
- `performance.py:40` `# top header` → `top_header = QHBoxLayout()`
- `installed.py:157` `# table widget` → `self.table_mods = QTableWidget()`

Harmless, but it's filler an AI adds to pad out "structure". Trim them.

---

## 6. Dead / never-called code

- `widgets.py` — `def _large_icon(...)` is defined but **never called** anywhere
  in the project. Leftover from an earlier design that was replaced. Either wire
  it up or delete it.

---

## 7. Verbose / redundant section banners (minor)

Heavy use of `# ── … ────…` and `'''…'''` banner comments and module docstrings
that repeat the filename + "what this file does" verbatim. Fine as convention,
but several are stale (e.g. docstrings describing behavior the refactor already
changed). Audit the module docstrings in `ui/tabs/*.py` for accuracy.

---

## Cleanup summary (from the slop-cleanup pass)

| Finding | Status |
| --- | --- |
| 1. Bypassed theme tokens (~230 hex literals) | ✅ FIXED — zero hex outside `theme.py`; added `ACCENT_HOVER`, `TRACK_*`, `TOAST_*`, `BTN_HOVER_BORDER`, `DISABLED_TEXT`, `SURFACE_2`, `SURFACE_3`; removed shadow palettes in `widgets.py` & `browse.py` |
| 2. Duplicate lines (`load_installed_mods`, `return None`) | ✅ FIXED |
| 3. `except: pass` swallows | ✅ PARTIALLY — install failures (Greed copy, fika meta save) now log; best-effort cache reads kept silent intentionally |
| 4. Copy-pasted symlink ladder (20x) | ✅ FIXED — `remove_path()` helper, 8 call sites + links.py |
| 5. "Comment restates code" noise | ✅ FIXED — removed 5 noise comments |
| 6. Dead `_large_icon` | ✅ FIXED — deleted (was unreferenced) |
| 7. Banner / docstring staleness | ✅ AUDITED — all docstrings accurate, no changes needed |

**Remaining:** visual screenshot review of the theme-token refactor (colors should
render pixel-identical since tokens evaluate to the same hex values).

---

## Suggested priority

1. **`browse.py:482-483`** — delete the duplicate `load_installed_mods()` (free win, zero risk).
2. **`metadata.py:44-46`** — collapse duplicate `return None`.
3. **Theme-token bypass** — the highest-value cleanup; makes future color work ~6x cheaper.
4. **`except: pass` in UI paths** — surface failures instead of swallowing.
5. **Symlink-ladder helper** — kill 20 copies.
6. **`_large_icon`** — delete or wire.
7. Comment noise / banner staleness.

None of these are blockers; the suite stays at 12/12 + ruff-clean either way.
