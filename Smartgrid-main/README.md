# Smartgrid Project
College Major Project on Cybersecurity to smartgrid

# Changelog
### V1.0
Completed and Hardcoded basic working of the file
Has several bugs but works as intended

---
### V1.1 (dashboardoperator.py)
### [Unreleased] - <28/11/2025>
#### Changed
- Reworked network layer to use requests.Session, configurable timeouts, retries, and exponential backoff for PUT requests.
- Payload format updated to include timezone-aware ISO timestamp (`timestamp_iso`) and optional epoch field (`timestamp_epoch`).
- Added type hints and defensive input validation to `_create_payload`.
- UI styling upgraded: platform-aware fonts, more consistent ttk style configuration, and a `Value.TLabel` style for numeric displays.
- Attack console styling made configurable via `attack_bg` / `attack_fg`.
- Removed (visually) the blackout panel from main layout to simplify UI.
- Added small color helpers and utilities for theme tweaks.

### Fixed
- (None yet) — note: new version introduced several issues that must be fixed (see "Known issues").

### Known issues / TODO
- `network_worker` incorrectly uses `getattr(self, "COMMAND_ENDPOINT")` / `STATUS_ENDPOINT` — will raise on HTTP calls. Replace with module constants or assign to `self.*` in `__init__`.
- `create_widgets` removed `self.blackout_listbox` but blackout-related methods still reference it — causes `AttributeError`. Either restore the widget or guard calls.
- Color helper functions declared without `self` cause `TypeError` if called via `self.*`. Mark as `@staticmethod` or add `self`.
- Queue item unpacking is messy — simplify logic to correctly extract `(priority, payload)` pattern.

- ---
### V1.2 (dashboardoperator.py)
### [Unreleased] - <28/11/2025>
### Added
- Introduced a **thread-safe logging system**:
  - `append_attack_log()` for safe logging from worker threads.
  - `_insert_attack_text()` for GUI-thread insertion with tags.
  - Support for log levels: INFO, DEFENSE, WARNING, ERROR, CRITICAL.
  - Optional file logging through `attack_log_file`.
- Added **automatic console trimming** with `attack_console_max_lines`.
- Improved **attack console appearance**:
  - Added `wrap="word"`, padding, borderless style.
  - Color-tagged log lines for clearer event visibility.
- Enhanced **status light indicator** rendering:
  - New parameters: `size`, `border`, `outline_width`, `glow`, `blink`, `blink_interval`.
  - Now supports blinking animation and glow effect.
  - Better cleanup of previous drawings and preventing overlapping blink timers.

### Changed
- `log_attack_action()` now uses the new thread-safe logging mechanism.
- `_append_attack_log()` kept for compatibility but now delegates to `append_attack_log()`.
- Minor UI refinements to attack console layout.

### Fixed
- Improved stability when updating the attack console by ensuring all text insertions occur on the UI thread.
- Prevented duplicate blink timers for the indicator by cancelling existing jobs before creating a new one.
- Ensured that tag styles for logging levels are created lazily and only once.
- Fixed line growth issues in attack console by implementing automatic log-trim logic.
- General cleanup of redundant code and improved consistency of log-level handling.

### Known Issues
- Style mapping still calls `self._lighten(...)` while the helper is named `_lighten_color` — requires renaming or adjusting call site.
- Color helper functions (`_hex_to_rgb`, `_rgb_to_hex`) are defined without `self` or `@staticmethod`, causing TypeErrors if called via `self`.
- `network_worker` still uses:
  - `getattr(self, "COMMAND_ENDPOINT")`
  - `getattr(self, "STATUS_ENDPOINT")`  
  These should reference module constants or be assigned to `self` in `__init__`.
- Blackout listbox is referenced by logic but **never created** in the UI, causing potential `AttributeError`.
---
### V1.3 (dashboardoperator.py)
### [Unreleased] - <01/12/2025>

### Added
- Thread-safety and blackout management improvements:
  - `active_blackouts_lock` to protect `active_blackouts`.
  - `blackout_cleanup_interval_ms` and `_cleanup_after_id` for controlled cleanup scheduling.
  - UI: restored **Active Blackouts** list panel (`blackout_listbox`). 
- Response queue controls:
  - `response_poll_interval_ms`, `response_max_items_per_tick`, `response_short_backlog_ms`.
  - Adaptive `process_response_queue()` scheduling and bounded-per-tick processing to avoid GUI stalls. 
- `send_command()` now supports `priority`, input validation and logs queueing outcomes. 
- Safer, timezone-aware blackout expiry handling and normalization (coerce numeric epoch → UTC datetime). 
- `self.COMMAND_ENDPOINT` / `self.STATUS_ENDPOINT` instance attributes and a `_lighten` compatibility alias for styling helpers. 

### Changed
- `process_response_queue()` rewritten to process a limited number of items per tick and adapt delay when backlog exists. 
- `update_dashboard()` rewritten for robustness: input validation, incremental Treeview updates (insert/update/delete), deduplication via snapshot hash, and safer indicator redraw logic. 
- `_add_active_blackout()` replaced with a defensive implementation that validates inputs, uses locks, and enforces `max_active_blackouts`. 
- Color helpers (`_hex_to_rgb` / `_rgb_to_hex`) declared `@staticmethod` and `_lighten_color` left as instance method; `_setup_styles` uses compatibility alias. 

### Fixed
- Fixed bug where `getattr(self, "COMMAND_ENDPOINT")`/`STATUS_ENDPOINT` would previously resolve to `None` by assigning those constants to `self.*` in `__init__`. 
- Prevented blocking GUI on large response backlogs by bounding per-tick processing and using adaptive scheduling. 
- Fixed color helper invocation `self._lighten(...)` by creating compatibility alias for `_lighten_color` and making helpers static. 
- Restored blackout UI and fixed race conditions by protecting `active_blackouts` with a lock. 

### Known Issues / TODO
- The queue-item unpacking code in `network_worker` still contains redundant/awkward checks when extracting `(priority, payload)` — simplify to `if isinstance(item, tuple) and len(item) >= 2: payload = item[1]` for clarity. 
- `active_blackouts_lock` is assigned more than once in `__init__` (duplicate assignment) — harmless but should be cleaned. 
- Consider throttling `log_attack_action()` calls from the network worker to avoid spamming console on repeated transient errors (add consecutive-failure counter / backoff to logs). 
- If you plan to persist `attack_log_file` ensure file rotation/truncation is implemented to avoid unbounded log growth. 
---
### V1.3.1 (dashboardoperator.py)
### [Unreleased] - <02/12/2025>
Minor Status update



