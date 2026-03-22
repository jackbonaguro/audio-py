# Player Refactor Plan

Goal: Fix readability issues while reducing line count (current ~829 lines: gui 540, player 289).

**Status: DONE** — All phases completed. Result: gui 360, player 277, controller 200, state 16, utils 37. Structure improved; total lines ~891 (new modules offset gui/player savings).

---

## Phase 1: Extract shared utilities (saves ~25 lines)

### 1.1 New `player/utils.py`
- `bytes_to_chunk_index(chunks: list[bytes], target_bytes: int) -> int` — single implementation for both gui and player use
- `ratio_to_chunk_index(chunks: list[bytes], ratio: float) -> int` — thin wrapper: `target_bytes = int(ratio * total)`
- `format_time(sec: float) -> str` — move `_fmt` here
- `BYTES_PER_SAMPLE`, `SLIDER_RANGE`, `UI_POLL_MS`, `SEEK_DELAY_MS` — shared constants

**Impact:** gui loses ~25 lines (duplicate loop x2, inline _fmt), adds ~20 for utils. **Net: -5 to -10**

### 1.2 Use utils in both gui and player
- Replace both "chunk index from ratio/bytes" loops with `ratio_to_chunk_index` / `bytes_to_chunk_index`
- Replace `_fmt` calls with `format_time`

---

## Phase 2: Replace SimpleNamespace with typed state (neutral lines, clearer)

### 2.1 New `player/state.py`
```python
@dataclass
class ProgressState:
    bytes_decoded: int = 0
    bytes_written: int = 0
    sample_rate: int = 0
    channels: int = 0
    done: bool = False
    abort: bool = False
    paused: bool = False
    seek_to_chunk: int | None = None
```
~15 lines. Workers and window take `ProgressState` instead of SimpleNamespace. No more `getattr(..., False)`.

---

## Phase 3: Consolidate player.py pause/seek logic (~-25 lines)

### 3.1 Extract `_apply_seek()` in play_from_buffer
Both seek paths (during playback and during pause) do: stop stream, close, terminate, reopen, set `bytes_written`/`i`/`last_chunk`, `just_resumed=True`. Extract:
```python
def _apply_seek(stream, p, chunks, seek_to): ...
```
Returns new `(stream, p, bytes_written, i, last_chunk)`.

### 3.2 Inline or extract pause-loop body
The `while pause_check()` block has the seek check duplicated. Move seek check to a helper or factor so one block handles "during pause, maybe seek". Single place for seek logic.

### 3.3 Remove dead code
Delete `transform_stereo` (unused).

**Impact:** ~-25 lines in player.py

---

## Phase 4: Extract PlaybackController from gui (~-80 lines in gui)

### 4.1 New `player/controller.py` (~120 lines)
`PlaybackController` owns:
- `ProgressState` instance
- Preload/Playback worker creation and signals
- `load(path, transform)`, `reload_with_transform(path, ratio, was_playing)`
- `play()`, `pause()`, `toggle_play_pause()`, `seek_to_ratio(ratio)`
- `abort()`, `is_loading()`, `is_playing()`

Signals: `load_complete`, `load_error`, `load_finished`, `playback_finished`, `playback_error`, `progress_updated(bytes_written, decode_sec, output_sec, ...)` or similar.

### 4.2 Slim down StreamProgressWindow
Window becomes:
- UI layout (~60 lines)
- Wire controller signals to UI updates
- Button handlers call controller methods
- `_update_bars` reads from controller/state
- `_on_load_complete` becomes thin: call `waveform.set_audio`, `play_pause_btn.setEnabled(True)`, maybe `controller.seek_to_ratio(ratio)` if restore needed

**Impact:** gui drops from ~540 to ~380. Controller adds ~120. **Net: -40**

---

## Phase 5: Split _load into focused methods (~-15 lines)

### 5.1 Replace single `_load(preserve_position)` with:
- `_load()` — normal load; calls `_start_load(path)` after validation
- `_reload_for_halftime()` — called from halftime toggle; computes ratio, calls `_start_load(path)` with `restore=(ratio, was_playing)`

### 5.2 `_start_load(path, restore=None)`
Single place for: abort playback, reset progress, create PreloadWorker, connect signals, start. Restore logic only in `_on_load_complete` when `restore` is set.

**Impact:** Less branching, clearer flow. **~-15 lines** by removing duplicated setup.

---

## Phase 6: Optional — explicit playback state enum (~+10 lines, clearer)

If time allows:
```python
class PlaybackState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
```
Derive from `progress.done`, `progress.paused`, worker `isRunning()`. Simplifies conditionals in `_update_bars`, button enabling.

---

## Summary: estimated line change

| Phase | gui.py | player.py | New files | Net |
|-------|--------|-----------|-----------|-----|
| 1 utils | -25 | 0 | +25 | -25 |
| 2 state | 0 | 0 | +15 | +15 |
| 3 player consolidate | 0 | -25 | 0 | -25 |
| 4 controller | -160 | 0 | +120 | -40 |
| 5 _load split | -15 | 0 | 0 | -15 |
| **Total** | **-200** | **-25** | **+160** | **~-65 lines** |

Target: **~765 lines** (from ~829), with clearer structure and less duplication.

---

## Implementation order

1. **Phase 1** (utils) — low risk, immediate deduplication
2. **Phase 3** (player consolidate) — self-contained, no gui changes
3. **Phase 2** (state) — do before Phase 4
4. **Phase 4** (controller) — main structural change; do after 1–3
5. **Phase 5** (_load split) — can do alongside or after Phase 4
6. **Phase 6** — optional polish
