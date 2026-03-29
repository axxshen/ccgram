# Inter-Agent Messaging

## Overview

Add agent-to-agent messaging to ccgram, allowing AI coding agents running in different tmux windows to discover each other, exchange messages, broadcast notifications, and spawn new agents — with human oversight via Telegram.

**Problem:** Agents in ccgram tmux windows are isolated. Users manually relay information between agents via Telegram topics. For long-running multi-component work (microservices, monorepo modules, cross-repo integration), agents need direct collaboration.

**Solution:** File-based mailbox system + CLI (`ccgram msg`) + broker delivery via existing poll loop + Telegram visibility. Skill and MCP server as additional interfaces to the same CLI.

**Key design decisions (from brainstorm + 3-reviewer process):**

- Async-default messaging (`send` returns immediately; `--wait` opt-in)
- Broker-first delivery (send_keys injection on idle is primary; skill inbox-check is enhancement)
- Shell topic safety (never inject messages into shell windows)
- Silent Telegram notifications (inter-agent messages grouped, no push)
- Auto-attached context (cwd, branch, provider in every message)
- Deadlock prevention (one outstanding `--wait` per window)
- Per-type TTLs sized for human-in-the-loop Telegram workflows (60m–8h)
- Atomic writes for all mailbox/registry files (Maildir-inspired write-then-rename)

**Functional spec:** This plan was derived from the brainstorm spec reviewed by Perplexity, Codex, and Gemini. The spec content is preserved in the Context section below.

## Context

### Codebase patterns (from exploration)

- **CLI:** Click group in `cli.py` with subcommands in separate `*_cmd.py` files (doctor_cmd.py, status_cmd.py pattern)
- **State files:** `atomic_write_json()` in `utils.py` — write to tmp, fsync, rename. Used for state.json, session_map.json
- **Config:** Env vars read in `Config.__init__()`, flag-to-env mapping in `_FLAG_TO_ENV`, lazy import at command entry
- **Poll loop:** `status_poll_loop()` in `handlers/status_polling.py` — 1s interval, time-gated periodic tasks (topic check every 60s)
- **Hook events:** `HookEvent` dataclass → `dispatch_hook_event()` switch → handler functions, resolved via `_resolve_users_for_window_key()`
- **Tests:** CliRunner for CLI, pytest fixtures, tests mirror source layout in `tests/ccgram/`

### Files/components involved

| Area                  | Files                                                                         |
| --------------------- | ----------------------------------------------------------------------------- |
| New CLI group         | `src/ccgram/msg_cmd.py` (new), `src/ccgram/cli.py` (add msg group)            |
| Mailbox core          | `src/ccgram/mailbox.py` (new) — message CRUD, registry, sweep                 |
| Broker delivery       | `src/ccgram/handlers/msg_broker.py` (new) — idle delivery, rate limiting      |
| Telegram integration  | `src/ccgram/handlers/msg_telegram.py` (new) — topic notifications             |
| Spawn flow            | `src/ccgram/handlers/msg_spawn.py` (new) — approval, creation                 |
| Skill                 | `src/ccgram/msg_skill.py` (new) — skill file generation + install             |
| Config                | `src/ccgram/config.py` (extend)                                               |
| Poll loop integration | `src/ccgram/handlers/status_polling.py` (extend)                              |
| Hook integration      | `src/ccgram/handlers/hook_events.py` (extend — idle trigger)                  |
| Tests                 | `tests/ccgram/test_mailbox.py`, `test_msg_cmd.py`, `test_msg_broker.py`, etc. |

### Architecture

```
+---------------+  +---------------+
|  Claude Skill |  |  MCP Server   |   <- Agent-side interfaces (MCP deferred to v2)
+-------+-------+  +-------+-------+
        |                   |
        v                   v
+-------------------------------+
|        CLI (ccgram msg)       |      <- Core operations
+---------------+---------------+
                |
                v
+-------------------------------+
|   File Mailbox + Registry     |      <- Storage layer (~/.ccgram/mailbox/)
+---------------+---------------+
                |
                v
+-------------------------------+
|   ccgram Broker (poll loop)   |      <- Delivery + lifecycle
+-------------------------------+
```

### Message types

| Type        | Behavior                                             | Sender blocks?           | Default TTL |
| ----------- | ---------------------------------------------------- | ------------------------ | ----------- |
| `request`   | Expects reply. Sender returns immediately by default | No (default) or `--wait` | 60 min      |
| `reply`     | Response to a request. Links via `reply_to`          | No                       | 120 min     |
| `notify`    | Fire-and-forget                                      | No                       | 240 min     |
| `broadcast` | Notify to every matching recipient's inbox           | No                       | 480 min     |

### Message format

```json
{
  "id": "msg-<uuid>",
  "from": "@0",
  "to": "@5",
  "type": "request",
  "reply_to": null,
  "subject": "API contract query",
  "body": "What's your gRPC API contract for payment processing?",
  "context": {
    "cwd": "/home/user/payment-svc",
    "branch": "feat/refund",
    "provider": "claude"
  },
  "created_at": "2026-03-29T10:45:00Z",
  "delivered_at": null,
  "read_at": null,
  "status": "pending",
  "ttl_minutes": 60
}
```

### Registry entry

```json
{
  "@0": {
    "name": "payment-service",
    "provider": "claude",
    "cwd": "/home/user/payment-svc",
    "branch": "feat/refund-endpoint",
    "status": "busy",
    "task": "Implementing refund endpoint",
    "team": "backend",
    "updated_at": "2026-03-29T10:30:00Z"
  }
}
```

### Configuration

| Setting       | Env Var                    | Default              |
| ------------- | -------------------------- | -------------------- |
| Auto-spawn    | `CCGRAM_MSG_AUTO_SPAWN`    | `false`              |
| Max windows   | `CCGRAM_MSG_MAX_WINDOWS`   | `10`                 |
| Mailbox dir   | (follows config dir)       | `~/.ccgram/mailbox/` |
| Wait timeout  | `CCGRAM_MSG_WAIT_TIMEOUT`  | `60` (seconds)       |
| Spawn timeout | `CCGRAM_MSG_SPAWN_TIMEOUT` | `300` (seconds)      |
| Spawn rate    | `CCGRAM_MSG_SPAWN_RATE`    | `3` (per window/hr)  |
| Message rate  | `CCGRAM_MSG_RATE_LIMIT`    | `10` (per window/5m) |

## Development Approach

- **Testing approach**: TDD (tests first)
- Complete each task fully before moving to the next
- Make small, focused changes
- **CRITICAL: every task MUST include new/updated tests** for code changes in that task
- **CRITICAL: all tests must pass before starting next task** — no exceptions
- **CRITICAL: update this plan file when scope changes during implementation**
- Run `make fmt && make test && make lint` after each change
- Maintain backward compatibility (new `msg` subcommand, no changes to existing behavior)

## Testing Strategy

- **Unit tests**: required for every task (TDD — write first)
- **Integration tests**: for broker delivery (real tmux), Telegram dispatch (PTB \_do_post patch)
- **Test patterns**: CliRunner for CLI, tmp_path for mailbox dirs, monkeypatch for config

## Progress Tracking

- Mark completed items with `[x]` immediately when done
- Add newly discovered tasks with ➕ prefix
- Document issues/blockers with ⚠️ prefix
- Update plan if implementation deviates from original scope
- Keep plan in sync with actual work done

## Implementation Steps

### Task 1: Mailbox core — message storage layer

The foundation. File-based mailbox with atomic writes, message CRUD, TTL support.

- [ ] write tests for `Mailbox` class: create inbox dir, write message, read message, list messages, acknowledge
- [ ] write tests for atomic write safety: partial write recovery, concurrent read during write
- [ ] write tests for TTL expiration: message expires after ttl_minutes, expired messages filtered from inbox
- [ ] write tests for message status transitions: pending → read → replied; pending → expired
- [ ] implement `src/ccgram/mailbox.py`:
  - `Mailbox` class with `base_dir` (default `~/.ccgram/mailbox/`)
  - `send(from_id, to_id, body, type, subject, ttl_minutes, reply_to, file_path)` → writes msg JSON to `{to_id}/msg-{uuid}.json` via atomic write (tmp + rename)
  - `inbox(window_id)` → list pending messages for window, filtered by TTL
  - `read(msg_id, window_id)` → mark message as read, set `read_at`
  - `reply(msg_id, window_id, body)` → create reply message linked via `reply_to`, mark original as `replied`
  - `sweep(window_id=None)` → remove expired + old read messages
  - Per-type TTL defaults: request=60m, reply=120m, notify=240m, broadcast=480m
  - Auto-attach context (cwd from session_map, branch from `git rev-parse`, provider from registry)
- [ ] write tests for `--file` support: body loaded from file path, size validation
- [ ] implement file support: `--file` reads content, 100KB soft limit with warning
- [ ] run `make fmt && make test && make lint` — must pass

### Task 2: Agent registry

Auto-populated from ccgram state + optional self-declared task/team fields.

- [ ] write tests for `Registry` class: create, read entry, update entry, remove entry, staleness detection
- [ ] write tests for auto-population: entries created from session_map + window state
- [ ] write tests for self-declared fields: register task/team, update task, clear on window death
- [ ] implement registry in `src/ccgram/mailbox.py` (or `src/ccgram/msg_registry.py` if large):
  - `Registry` class wrapping `~/.ccgram/mailbox/registry.json`
  - `refresh(session_manager, tmux_manager)` → update auto-populated fields (window_id, name, provider, cwd, branch, status) from existing ccgram state
  - `register(window_id, task, team)` → set self-declared fields
  - `get(window_id)` → single entry
  - `list_peers(filter_provider, filter_team, filter_cwd_pattern)` → filtered list
  - `remove(window_id)` → cleanup on window death
  - Staleness: entries not refreshed within 10 min shown as `stale`
  - All writes via `atomic_write_json`
- [ ] run `make fmt && make test && make lint` — must pass

### Task 3: CLI subcommand group — `ccgram msg`

Click group with subcommands for all operations. Following existing pattern (cli.py + msg_cmd.py).

- [ ] write tests for CLI help and subcommand routing: `ccgram msg --help`, `ccgram msg list-peers --help`
- [ ] write tests for `list-peers` command: table output, `--json` output, empty state
- [ ] write tests for `find` command: filter by provider, team, cwd pattern
- [ ] write tests for `send` command: basic send, `--notify`, `--wait`, `--ttl`, `--file`
- [ ] write tests for `inbox` command: show pending, `--json`, empty inbox
- [ ] write tests for `read` command: mark message read, unknown msg-id error
- [ ] write tests for `reply` command: create reply, link to original, `--file`
- [ ] write tests for `broadcast` command: send to all, filtered by team/provider/cwd
- [ ] write tests for `register` command: set task/team, update task
- [ ] write tests for `sweep` command: clean expired, `--force` cleans all read
- [ ] implement `src/ccgram/msg_cmd.py`:
  - `msg_main` Click group
  - Subcommands: `list-peers`, `find`, `send`, `inbox`, `read`, `reply`, `broadcast`, `register`, `sweep`
  - Window self-identification: `CCGRAM_WINDOW_ID` env var (primary), tmux runtime detection (fallback)
  - `send` default is async (return immediately); `--wait` blocks with poll loop + timeout (`CCGRAM_MSG_WAIT_TIMEOUT`)
  - `--wait` deadlock prevention: fail if sender already has pending outbound `--wait`
  - Message rate limiting: max `CCGRAM_MSG_RATE_LIMIT` per window per 5 min
  - All output: table format (human) or `--json` (machine)
- [ ] register `msg` group in `src/ccgram/cli.py` (add to cli group, lazy import pattern)
- [ ] run `make fmt && make test && make lint` — must pass

### Task 4: Config extensions

Add new env vars to Config for all messaging settings.

- [ ] write tests for new config values: defaults, env var override, config-dir mailbox path
- [ ] extend `src/ccgram/config.py`:
  - `msg_auto_spawn: bool` from `CCGRAM_MSG_AUTO_SPAWN` (default: False)
  - `msg_max_windows: int` from `CCGRAM_MSG_MAX_WINDOWS` (default: 10)
  - `msg_wait_timeout: int` from `CCGRAM_MSG_WAIT_TIMEOUT` (default: 60)
  - `msg_spawn_timeout: int` from `CCGRAM_MSG_SPAWN_TIMEOUT` (default: 300)
  - `msg_spawn_rate: int` from `CCGRAM_MSG_SPAWN_RATE` (default: 3)
  - `msg_rate_limit: int` from `CCGRAM_MSG_RATE_LIMIT` (default: 10)
  - `mailbox_dir: Path` derived from config_dir / `mailbox`
- [ ] add CLI flag mappings to `_FLAG_TO_ENV` in `cli.py` (for flags that make sense on `run` command)
- [ ] run `make fmt && make test && make lint` — must pass

### Task 5: Broker delivery — idle detection + send_keys injection

The active delivery layer. Piggybacks on existing poll loop. Injects messages into idle agent windows.

- [ ] write tests for broker delivery logic: detect idle → select pending message → format → deliver
- [ ] write tests for shell topic safety: messages to shell windows are NOT delivered via send_keys
- [ ] write tests for provider-specific idle detection: Claude (Stop hook), Codex/Gemini (activity heuristic)
- [ ] write tests for `delivered_at` timestamp: set on successful injection
- [ ] write tests for message rate limiting enforcement in broker
- [ ] implement `src/ccgram/handlers/msg_broker.py`:
  - `async def broker_delivery_cycle(bot)` — called from poll loop, checks all inboxes for pending messages
  - For each pending message: check recipient idle status → if idle and not shell provider → format message text → `send_keys` → set `delivered_at`
  - Shell safety: skip send_keys for shell-provider windows (message stays in mailbox)
  - Rate limiting: track sends per window, enforce `CCGRAM_MSG_RATE_LIMIT`
  - Message formatting: include sender name, subject, body (truncated if very long for send_keys)
- [ ] integrate into `src/ccgram/handlers/status_polling.py`:
  - Add `broker_delivery_cycle()` call in main poll loop (every cycle or every N seconds)
  - Add periodic `mailbox.sweep()` call (every 5 minutes, time-gated like topic check)
- [ ] integrate idle detection from hook events: extend `_handle_stop()` in `hook_events.py` to trigger immediate broker delivery check for that window
- [ ] run `make fmt && make test && make lint` — must pass

### Task 6: Telegram integration — visibility and notifications

Inter-agent messages shown in Telegram topics, silent by default, grouped.

- [ ] write tests for message notification formatting: sender info, subject, body preview
- [ ] write tests for notification grouping: multiple messages merged into single Telegram message
- [ ] write tests for silent delivery: notifications don't trigger push (disable_notification=True)
- [ ] write tests for shell topic pending message display: show message in topic since send_keys is skipped
- [ ] implement `src/ccgram/handlers/msg_telegram.py`:
  - `async def notify_message_sent(bot, from_window, to_window, message)` — post in sender's topic
  - `async def notify_message_received(bot, from_window, to_window, message)` — post in recipient's topic
  - `async def notify_pending_shell(bot, window_id, message)` — show pending message in shell topic for human action
  - All notifications use `disable_notification=True` (silent)
  - Use existing `safe_send()` / `safe_reply()` helpers for entity formatting
  - Merge multiple inter-agent notifications via existing message queue (queue worker handles merging)
- [ ] wire notifications into broker delivery and CLI send paths
- [ ] run `make fmt && make test && make lint` — must pass

### Task 7: Broadcast messaging

Filtered broadcast: send a notify to all matching peers.

- [ ] write tests for broadcast to all peers
- [ ] write tests for filtered broadcast: by team, provider, cwd pattern
- [ ] write tests for broadcast TTL (480 min default)
- [ ] write tests for broadcast Telegram visibility: single summary message, not per-recipient
- [ ] implement broadcast in `Mailbox.broadcast()`:
  - Write one message file per matching recipient inbox
  - Filter by team, provider, cwd glob pattern (using `fnmatch`)
  - Type is `notify` with 480 min TTL
  - Telegram: single summary notification in sender's topic listing recipients
- [ ] wire into CLI `broadcast` subcommand (already stubbed in Task 3)
- [ ] run `make fmt && make test && make lint` — must pass

### Task 8: Agent spawning with Telegram approval

Agents request new agent instances. Requires Telegram approval by default.

- [ ] write tests for spawn request creation: validate provider, cwd, max-windows check
- [ ] write tests for spawn rate limiting: max N per window per hour
- [ ] write tests for approval flow: approve callback creates window, deny callback returns error
- [ ] write tests for auto-mode: `--auto` bypasses approval but not max-windows or rate limits
- [ ] write tests for spawn timeout: unapproved request expires after `CCGRAM_MSG_SPAWN_TIMEOUT`
- [ ] write tests for context bootstrap: `--context` file attached to spawn
- [ ] implement `src/ccgram/handlers/msg_spawn.py`:
  - `async def handle_spawn_request(bot, requester_window, provider, cwd, prompt, context_file, auto)`:
    - Validate provider exists, cwd exists, max-windows not exceeded
    - Rate limit check (per window per hour)
    - If `--auto` or `CCGRAM_MSG_AUTO_SPAWN`: create immediately
    - Else: post inline keyboard to requester's Telegram topic `[Approve] [Deny]`
    - On approve: create tmux window, launch agent, send initial prompt, install skill, register in registry, return window_id
    - On deny: return error to requester
    - On timeout: cancel request, return timeout error
  - Callback data: `CB_SPAWN_APPROVE = "sp:ok:<request_id>"`, `CB_SPAWN_DENY = "sp:no:<request_id>"`
- [ ] register spawn callbacks in bot.py callback handler
- [ ] wire into CLI `spawn` subcommand
- [ ] run `make fmt && make test && make lint` — must pass

### Task 9: Skill auto-installation

Install messaging skill prompt to Claude Code agents so they check inbox on idle.

- [ ] write tests for skill file generation: correct prompt content, correct path
- [ ] write tests for skill installation: writes to correct directory, idempotent
- [ ] write tests for skill content: includes register, inbox check, send, broadcast instructions
- [ ] implement `src/ccgram/msg_skill.py`:
  - `SKILL_CONTENT` — prompt text teaching the agent about messaging (register on start, check inbox on idle, send/find/broadcast/spawn)
  - `install_skill(cwd: Path)` — write skill file to `{cwd}/.claude/skills/ccgram-messaging.md` (per-project, scoped)
  - `ensure_skill_installed(window_id)` — check if skill exists for window's cwd, install if missing
  - Idempotent: skip if file already exists with same content
- [ ] integrate skill install into spawn flow (Task 8) and optionally into topic creation for Claude windows
- [ ] run `make fmt && make test && make lint` — must pass

### Task 10: Window self-identification

Ensure agents can identify their own window ID for CLI operations.

- [ ] write tests for self-identification: env var present → use it; absent → tmux fallback; outside tmux → error
- [ ] implement in `msg_cmd.py`:
  - `get_my_window_id()` → reads `CCGRAM_WINDOW_ID` env var (primary)
  - Fallback: `tmux display-message -p -t $TMUX_PANE '#{window_id}'`
  - Error if neither works (not in tmux)
- [ ] set `CCGRAM_WINDOW_ID` env var when ccgram creates tmux windows (extend `tmux_manager.create_window()`)
- [ ] run `make fmt && make test && make lint` — must pass

### Task 11: Verify acceptance criteria

- [ ] verify all message types work end-to-end: request, reply, notify, broadcast
- [ ] verify broker delivery works: message sent → idle detected → injected via send_keys → reply captured
- [ ] verify shell safety: messages to shell windows stay in mailbox, shown in Telegram topic
- [ ] verify deadlock prevention: `--wait` with existing pending outbound fails immediately
- [ ] verify TTL expiration: expired messages not shown in inbox, swept by periodic cleanup
- [ ] verify spawn approval flow: request → Telegram keyboard → approve → window created
- [ ] verify Telegram visibility: messages appear in both topics, silent, grouped
- [ ] verify rate limiting: exceeding message or spawn rate returns error
- [ ] verify registry auto-population: window state reflected without manual registration
- [ ] run full test suite: `make fmt && make test && make lint && make typecheck`

### Task 12: Update documentation

- [ ] update `CLAUDE.md` with `ccgram msg` command reference and design summary
- [ ] update `docs/plans/` — mark this plan complete
- [ ] add messaging section to architecture rule file (`.claude/rules/architecture.md`)

## Technical Details

### File layout

```
~/.ccgram/mailbox/
  registry.json              # Agent registry (auto + self-declared)
  @0/                        # Window @0 inbox
    tmp/                     # In-flight writes (atomic write staging)
    msg-<uuid>.json          # Individual messages
  @5/
    tmp/
    msg-<uuid>.json
```

### Delivery flow

```
Agent A (skill)                    ccgram broker              Agent B (skill)
─────────────────                  ─────────────              ─────────────────
ccgram msg send @5 "API?"
  → writes @5/inbox/msg.json
  → returns immediately (async)
                                   poll cycle sees msg in @5/inbox
                                   @5 is busy → skip
                                   ...
                                   @5 goes idle (Stop hook)
                                   ┌─ shell provider? ─┐
                                   │  YES: skip, show   │
                                   │  in Telegram topic  │
                                   │  NO: send_keys msg  │
                                   └────────────────────┘
                                   sets delivered_at                Agent B sees message
                                                                   processes it
                                                                   ccgram msg reply <id> "answer"
                                                                     → writes @0/inbox/reply.json
Agent A checks inbox (skill prompt or next CLI call)
  reads reply
```

### Safety rules

- **Atomic writes:** All message + registry writes via write-to-tmp + fsync + rename (existing `atomic_write_json` pattern)
- **Shell safety:** Never inject messages into shell-provider windows via send_keys
- **Deadlock prevention:** Max one outstanding `--wait` per window; fail if already blocking
- **Rate limiting:** Max 10 messages/5min per window; max 3 spawns/hour per window
- **TTL expiry:** Wakes blocking `--wait` sender with timeout error
- **Sweep:** Periodic cleanup every 5 min in poll loop; session cleanup on window death

## Post-Completion

**Manual verification:**

- Test with 2+ Claude Code instances in separate tmux windows sending messages
- Test cross-provider: Claude → Codex message delivery
- Test shell safety: verify message to shell window stays in mailbox
- Test Telegram notification grouping with 5+ rapid inter-agent messages
- Test spawn approval flow via real Telegram inline keyboard

**Future work (from reviewer feedback — not in this plan):**

- MCP server wrapping CLI for Desktop Claude / IDE integration
- Observer/watch pattern for monitoring other windows
- Claim/accept/decline flow for request ownership
- Human message relay from Telegram UI
- Advisory file locking for shared worktrees
- Parent/child lifecycle linking for spawned agents
- Transcript injection for spawn context
- Self-declared capability tags for discovery
