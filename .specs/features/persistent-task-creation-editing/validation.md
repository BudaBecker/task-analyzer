# Persistent Task Creation and Editing Validation

**Date:** 2026-09-14
**Spec:** [Approved delivery 1A specification](spec.md)
**Design:** [Approved design and audit revision](design.md)
**Diff range:** `127d777..5fe1955` on `feat/persistent-task-creation-editing`
**Verifier:** independent sub-agent (author != verifier); no source or test file was modified by this validation.
**Revision:** re-verified 2026-09-14 after fix commit `5fe1955`, which the Verifier did not author. The original pass covered `127d777..b50a9fe`.

## Validation: persistent-task-creation-editing - FAIL

**Verdict: FAIL — the feature is not complete.**

Everything locally verifiable now passes: all five gates are green, 588 tests pass, and every injected fault is killed — no surviving mutants remain. The verdict stays FAIL for one reason only, and it is external:

1. **PCE-47 (private Tailscale access) is UNMET.** It cannot be satisfied locally and no authorized-environment evidence exists.
2. **PCE-44's target-interpreter half is UNMET.** The *declared* baseline is now pinned and discriminated by tests (see Finding 2, resolved), but the interpreter actually installed on the Ubuntu target is still unverified.

This matches the Design's own instruction that "an overall PASS, Verified traceability and validate_state completion require the actual target-interpreter and private-access evidence." No local work can close either item, so FAIL is the correct verdict rather than a pessimistic one.

---

## Task Completion

All 31 tasks (T1-T31) are marked `[Complete]` in [tasks.md](tasks.md). No task is blocked or partial. T31 documents the pending external checkpoint rather than satisfying it.

---

## Gate Check

Run from the repository root with the session's development interpreter (Python 3.13.2).

| Gate | Command | Exit | Result |
| --- | --- | --- | --- |
| Formatting | `python -m ruff format --check src/task-analyzer-server tests/server` | 0 | 40 files already formatted |
| Lint | `python -m ruff check src/task-analyzer-server tests/server` | 0 | All checks passed |
| Types | `python -m mypy --strict src/task-analyzer-server/task_analyzer_server` | 0 | Success: no issues found in 11 source files |
| Tests | `python -m pytest tests/server` | 0 | **588 passed**, 0 failed, 0 skipped, 2 warnings, 57.05s |
| Dependencies | `python -m pip check` | 0 | No broken requirements found |

All five were re-run by the Verifier at `5fe1955`, not taken from the fix author's report.

- **Test count before this feature:** 0 (the Design records empty source/test directories).
- **Test count after:** 588. **Delta:** +588 (583 at `b50a9fe`, plus 5 added by the fix).
- **Skipped tests:** none. **Failures:** none.
- The two warnings are third-party `DeprecationWarning`s from Starlette's test client, not application defects.

The `python -m build` / installed-wheel gate is exercised inside the suite itself by `tests/server/integration/test_installed_distribution.py`, which builds the wheel from a copy of the packaged sources, installs it into a fresh environment, and runs the initializer, factory and restart checks against the installed distribution only.

---

## Spec-Anchored Acceptance Criteria

Every criterion below is traced to a `file:line` and the assertion expression at that location, then judged against the outcome the specification fixes. Paths are relative to the repository root.

### P1: Create a valid pending task

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-01 valid title-only creation | Pending task, no observations/deadline required | `tests/server/unit/test_domain_validation.py:74` — `issues_for(title="Read notes") == ()`; `tests/server/integration/test_services_create.py:181` — title-only creation yields a pending task | PASS |
| PCE-02 empty/whitespace title rejected | Rejection | `tests/server/unit/test_domain_validation.py:84` — `issues_for(title="") == (REQUIRED_TITLE,)`; `:89` `title="     "`; `:110` parametrized over `\t`, `\n`, `\r\n`, NBSP, EM SPACE | PASS |
| PCE-03 exactly 200 chars after trimming accepted | Accept | `tests/server/unit/test_domain_validation.py:119` — `issues_for(title="a" * 200) == ()`; `:155` `f"   {'a' * 200}   "` accepted after trimming | PASS |
| PCE-04 over 200 after trimming rejected | Reject | `tests/server/unit/test_domain_validation.py:124` — `issues_for(title="a" * 201) == (TOO_LONG_TITLE,)`; `:160` edge spaces do not rescue 201 | PASS |
| PCE-05 exactly 5,000 observations accepted | Accept | `tests/server/unit/test_domain_validation.py:178` — `issues_for(observations="a" * 5000) == ()` | PASS |
| PCE-06 over 5,000 observations rejected | Reject | `tests/server/unit/test_domain_validation.py:183` — `issues_for(observations="a" * 5001) == (TOO_LONG_OBSERVATIONS,)` | PASS |
| PCE-07 line breaks retained | Observations keep line breaks | `tests/server/integration/test_services_create.py:217` — `stored_tasks(settings)[0].observations == "First line\nSecond line\n\nFourth line"`; `tests/server/unit/test_contracts_input.py:70` | PASS |
| PCE-08 valid in-range deadline retained | Calendar date retained | `tests/server/integration/test_services_create.py:206` — `stored[0].deadline == date(2026, 9, 14)` | PASS |
| PCE-09 past deadline accepted | Accept | `tests/server/integration/test_services_create.py:226` — `result.outcome == "succeeded"` and `stored_tasks(settings)[0].deadline == date(2020, 1, 31)` | PASS |
| PCE-10 non-calendar deadline rejected | Reject | `tests/server/unit/test_domain_validation.py:277` — parametrized invalid dates yield `(INVALID_DEADLINE,)`; `:298` non-`YYYY-MM-DD` spellings; `:309` non-ASCII digits | PASS |
| PCE-48 user-perceived character counting | Grapheme clusters, not code points | `tests/server/unit/test_domain_validation.py:130-133` — `title = COMBINING_E * 200`, `assert len(title) == 400`, `issues_for(title=title) == ()`; `:143-146` `JOINED_FAMILY * 200`, `assert len(title) == 1400`, accepted; `:137` and `:150` reject at 201 | PASS |
| PCE-51 `0001-01-01` and `9999-12-30` accepted | Accept both endpoints | `tests/server/unit/test_domain_validation.py:248` / `:253`; `tests/server/integration/test_services_create.py:236` — `stored_tasks(settings)[0].deadline == date(1, 1, 1)`; `:246` — `== date(9999, 12, 30)` | PASS |
| PCE-52 outside range rejected, state unchanged | Reject as `INVALID_DEADLINE`, no state change | `tests/server/unit/test_domain_validation.py:258` — `issues_for(deadline="9999-12-31") == (INVALID_DEADLINE,)`; `:262` below-range; `tests/server/integration/test_services_edit.py:644-648` — `result.error.fields == (INVALID_DEADLINE,)` and `stored_columns(settings, task_id) == before` | PASS |

The 200/201 and 5,000/5,001 pairs are preserved exactly, in plain, combining-mark and joined-emoji forms. The combining and emoji fixtures assert the code-point length alongside acceptance, which is what makes them discriminate a code-point counter.

### P1: Edit a pending task without losing identity or valid state

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-11 valid edit persists title/observations/deadline | All three persisted | `tests/server/integration/test_services_edit.py:296` — every editable field persisted; `:319` whole editable state replaced | PASS |
| PCE-12 identity preserved | Same `task_id` | `tests/server/integration/test_services_edit.py:375` — `result.task.task_id == task_id` | PASS |
| PCE-13 original creation time preserved | `created_at` unchanged | `tests/server/integration/test_services_edit.py:376` — `result.task.created_at == before.created_at`; `:390` — `stored.created_at == SERVER_NOW` after editing under a later clock | PASS |
| PCE-14 pending status retained | `status == "pending"` | `tests/server/integration/test_services_edit.py:377-378` — `result.task.status == "pending"` and `result.task.completed_at is None` | PASS |
| PCE-15 invalid edit rejected, state unchanged | Reject; whole task unchanged | `tests/server/integration/test_services_edit.py:485` (invalid title) and `:501` (invalid deadline), each comparing full `stored_columns` before/after; `tests/server/unit/test_domain_validation.py:334` | PASS |
| PCE-16 removing optional values persists absence | Absence persisted | `tests/server/integration/test_services_edit.py:333` (observations cleared) and `:347` (deadline cleared) | PASS |

### P1: Enforce task uniqueness

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-17 case/space-insensitive comparison | `Read notes` equals ` READ  NOTES ` | `tests/server/unit/test_domain_title_key.py:26` — `title_key("Read notes") == title_key(" READ  NOTES ")`; `:101-103` pins the literal key `"read notes"` | PASS |
| PCE-18 accents preserved | `Review résumé` differs from `Review resume` | `tests/server/unit/test_domain_title_key.py:31` — `title_key(ACCENTED_TITLE) != title_key(PLAIN_TITLE)`; `:55` — `title_key("Résumé") == "résumé"` | PASS |
| PCE-19 dated conflict rejected, any status | Reject; population ignores pending/completed | `tests/server/integration/test_services_uniqueness.py:340` (pending); `:402` — conflicts with a **completed** dated fixture, `result.error.conflicting_task_id == completed` | PASS |
| PCE-20 undated pending conflict rejected | Reject | `tests/server/integration/test_services_uniqueness.py:474-477` — `result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT` and `conflicting_task_id == existing` | PASS |
| PCE-21 equivalent titles, different dates coexist | Permit | `tests/server/integration/test_services_uniqueness.py:425-426` — `result.outcome == "succeeded"`, `len(stored_tasks(settings)) == 2` | PASS |
| PCE-22 undated and dated coexist | Permit | `tests/server/integration/test_services_uniqueness.py:437` and `:449` — both directions succeed with two stored tasks | PASS |
| PCE-23 self-exclusion on edit | Task excluded from its own comparison | `tests/server/integration/test_services_uniqueness.py:578` (same combination) and `:591` (equivalent respelling) — both succeed | PASS |
| PCE-24 deleted tasks excluded | Deleted never block | `tests/server/integration/test_services_uniqueness.py:492` (dated), `:503` (undated), `:661` (on editing) — all succeed | PASS |
| PCE-25 completed undated excluded | Completing an undated task frees its title | `tests/server/integration/test_services_uniqueness.py:487` — succeeds against a completed undated fixture; `:647` on editing | PASS |
| PCE-26 rejection identifies the conflict | Conflict named in the result | `tests/server/integration/test_api_operations.py:266-273` — `error.code == TASK_UNIQUENESS_CONFLICT`, `original_http_status == 409`, `error.conflicting_task_id == original["task"]["task_id"]` | PASS |
| PCE-27 both tasks unchanged on conflict | Neither task modified | `tests/server/integration/test_services_uniqueness.py:379` (creation leaves the conflicting task untouched), `:391` (no task created), `:563` (edit leaves both, compared by full `stored_columns`) | PASS |

Both protected title examples are asserted verbatim, and the two uniqueness populations are exercised separately against pending, completed and deleted fixtures in both the dated and undated directions.

### P1: Retain authoritative task state and product time

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-28 creation time from the server clock | Server instant at application | `tests/server/integration/test_services_create.py:448-449` — `result.task.created_at == SERVER_NOW` and the stored row matches | PASS |
| PCE-29 configured zone retained | Zone fixed on first setup | `tests/server/integration/test_services_configuration.py:140-142` — `view.configured is True`, `product_time_zone == PRODUCT_ZONE`, `retained_zone(settings) == PRODUCT_ZONE` | PASS |
| PCE-30 product date from server time in retained zone | Date derived in the retained zone | `tests/server/integration/test_services_configuration.py:151-152` — `view.server_now == SERVER_NOW`, `product_date == PRODUCT_DATE_IN_SAO_PAULO`; `:161` a different zone gives a different date from the same instant | PASS |
| PCE-31 desktop clock/zone changes do not move interpretation | Server-based rules preserved | `tests/server/integration/test_services_configuration.py:239-240` — a clock in another zone yields the same `server_now` and `product_date`; `:250` a moved desktop cannot replace the zone | PASS |
| PCE-32 cutoff is midnight immediately after the date | 2026-09-14 → 2026-09-15 00:00 product zone | `tests/server/unit/test_clock_cutoff.py:71-74` — `cutoff == datetime(2026, 9, 15, 3, 0, tzinfo=UTC)` and its Sao Paulo reading is `2026-09-15 00:00` | PASS |
| PCE-33 overdue once the cutoff is reached | Valid through Sept 14; overdue at Sept 15 00:00, no grace | `tests/server/unit/test_clock_cutoff.py:81` — `last_moment < deadline_cutoff(...)` for `23:59:59.999999`; `:89-90` — `midnight == cutoff` and `midnight >= cutoff` | PASS |
| PCE-34 accepted state survives restart | State retained | `tests/server/integration/test_durability.py:349-350` and `:368` — `survivor == created.json()["task"]`, across a genuinely new server process | PASS |
| PCE-35 configured zone survives restart | Zone retained | `tests/server/integration/test_durability.py:417-418` — `configuration["configured"] is True`, `product_time_zone == PRODUCT_ZONE` after restart | PASS |
| PCE-36 persisted tasks available to a fresh session | State readable by a new session | `tests/server/integration/test_durability.py:465-469` — new session reads the task list with no carried cookie/session state | PASS |
| PCE-49 repeated midnight uses the FIRST occurrence | Earlier UTC instant | `tests/server/unit/test_clock_cutoff.py:118-119` — `cutoff == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)` and `cutoff < datetime(2026, 11, 1, 5, 0, tzinfo=UTC)`; `:129-130` confirms both instants read as the same local midnight | PASS |
| PCE-50 missing midnight uses first valid instant at/after the boundary | Apia `2011-12-29` → `2011-12-30T10:00:00.000000Z` | `tests/server/unit/test_clock_cutoff.py:154-155` — `cutoff == datetime(2011, 12, 30, 10, 0, tzinfo=UTC)` and its Apia reading is `2011-12-31 00:00`; `:137` Havana; `:147` Sao Paulo 2018 | PASS |

**Oracle independence confirmed.** Every expected instant in `test_clock_cutoff.py` is a literal `datetime` constant read from IANA zone-transition data (fixtures at `:40-64`, documented at `:5-19`). No expected value is produced by calling `deadline_cutoff`. The `Pacific/Apia` oracle is exactly the approved `2011-12-30T10:00:00Z`. `:192` additionally re-derives the boundary independently from `deadline + 1 day` and checks that the preceding microsecond falls short, across all 13 fixtures including both supported date endpoints in UTC, `+14:00` and `-11:00`.

### P1: Recover original operation results without duplicate application

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-37 success only after persistence | Confirmed only once committed | `tests/server/integration/test_services_create.py:489-491` — reported task equals the stored task and the retained result; `tests/server/integration/test_services_runner.py:497-504` — a failed COMMIT raises and leaves **no** retained outcome and **no** task | PASS |
| PCE-38 consulted outcome returned | The operation's own outcome | `tests/server/integration/test_services_runner.py:518` — `lookup_operation(...) == original`; `tests/server/integration/test_api_operations.py:194-196` — consulted snapshot matches field for field | PASS |
| PCE-39 repetition prevents duplicate application | Applied once only | `tests/server/integration/test_services_runner.py:355-357` — `repeated == original`, **`command.runs == 1`**, one task stored; `tests/server/integration/test_services_create.py:503` — `len(stored_tasks(settings)) == 1` | PASS |
| PCE-40 lost response: original outcome available | Original persisted outcome on consultation | `tests/server/integration/test_api_operations.py:193-196` — consulted result carries the created task with `created_at == "2026-09-14T12:00:00.123456Z"`; `tests/server/integration/test_durability.py:472` — consultable after a restart | PASS |
| PCE-41 original uniqueness rejection returned | Same rejection on consultation | `tests/server/integration/test_services_uniqueness.py:514`; `:751` — the retained rejection survives even after the conflict is freed | PASS |
| PCE-42 different conflicting operation rejected, not replayed | Reject the conflict; do not report the earlier success | `tests/server/integration/test_services_uniqueness.py:539-544` — `refused.outcome == "rejected"`, `refused.operation_id == second.operation_id`, code `TASK_UNIQUENESS_CONFLICT`, `len(stored_tasks(settings)) == 1` | PASS |
| PCE-43 rejection distinguishable from unknown | Unknown is not a rejection | `tests/server/integration/test_api_operations.py:281-285` — unknown is `404` with `OPERATION_RESULT_UNKNOWN`; `:293-295` — carries no terminal `outcome`; contrasted with `:234` where a stored rejection is `200` with `outcome == "rejected"`; `:250-252` — a `200` consultation of a rejection persisted no task | PASS |

### P1: Serve the private personal collection within approved constraints

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PCE-44 Python 3.13 or later | Runtime baseline is >= 3.13 | `pyproject.toml:9` — `requires-python = ">=3.13"`, now pinned by `tests/server/unit/test_packaging_metadata.py:46` — `declared_floor() == (3, 13)`; `:51` — `(3, 12) < declared_floor()`; `:56` — `(3, 11) < declared_floor()`; `:61` — `not (3, 13) < declared_floor()`; `:68` — `metadata["project"]["requires-python"] == ">=3.13"`. Local half covered and discriminated. **Target interpreter still unverified** — see Finding 3. | PARTIAL (local half PASS) |
| PCE-45 dedicated self-hosting supported | Explicit paths, installed distribution, no implicit fallback | `tests/server/integration/test_durability.py:519-521` — a configured runtime path cannot become a test's database and `not Path("C:/runtime/production.db").exists()`; `tests/server/integration/test_installed_distribution.py:465` (installed initializer creates a disposable database), `:503` (persisted state survives restarting the installed server), `:523` (absent database fails without creating one) | PASS |
| PCE-46 one collection, no product accounts/authentication | Served without sign-in; forwarded identity is not an account | `tests/server/integration/test_api_app.py:380` — `response.status_code == 200` with no credential; `:395-396` — `forwarded.status_code == anonymous.status_code` and `forwarded.json() == anonymous.json()` for `Authorization`, `X-Forwarded-User` and `Tailscale-User-Login` headers | PASS (local half) |
| PCE-47 private access through Tailscale | Private tailnet path verified | **No local evidence exists and none is possible.** No test in scope exercises a tailnet path; `docs/architecture/deployment/server.md` and the systemd asset are documentation, which the Design states cannot satisfy PCE-47. | **UNMET** |

**Status: 51 of 52 criteria are fully satisfied within the locally verifiable scope. 0 spec-precision gaps. PCE-44's declared baseline is now covered and discriminated, while its target-interpreter half stays externally unverified. PCE-47 is UNMET and externally blocked.**

---

## Discrimination Sensor

**Isolation method.** All mutations ran in temporary `git worktree` scratches under the session scratchpad (`git worktree add <scratch> HEAD`), removed with `git worktree remove --force` afterwards. `git stash` was never used. The real working tree was never mutated.

- **Pre-sensor baseline** (`git status --porcelain`): three untracked `__pycache__/` directories (plus this report, on the re-verification pass).
- **Post-sensor** (`git status --porcelain`): identical each time, `pyproject.toml` intact, `git worktree list` back to the single real tree. `HEAD` was `b50a9fe` for pass 1 and `5fe1955` for pass 2.

**Methodological correction — the first sensor run was void.** An initial pass reported all 10 mutations surviving with identical pass counts. The cause was that the development environment installs the package in editable mode through `__editable__.task_analyzer_server-0.1.0.pth`, whose single path entry points at the **real repository**. Tests executed inside the worktree therefore imported the unmutated real source, and the mutations were never exercised. The run was discarded and repeated with `PYTHONPATH` set to the worktree's package root, plus two guards: a provenance check asserting the imported `task_analyzer_server.__file__` resolves inside the worktree, and an unmutated baseline run of the full suite in the worktree (583 passed, exit 0). Only the guarded results below are reported. A worktree-based sensor on this repository is invalid without that override.

**Sensor depth:** P0-full (data integrity, durability and time semantics are critical paths).

### Pass 1 — at `b50a9fe`

| # | File | Mutation | Tests run | Killed? |
| --- | --- | --- | --- | --- |
| M1 | `domain.py:201` | Grapheme counter iterates code points instead of `\X` clusters | `test_domain_validation.py` | Killed (4 failed) |
| M2 | `domain.py:91` | Title key skips internal-space collapsing | `test_domain_title_key.py`, `test_services_uniqueness.py` | Killed (19 failed) |
| M3 | `domain.py:92` | Title key strips accents (NFD + drop combining marks) | `test_domain_title_key.py`, `test_services_uniqueness.py` | Killed (4 failed) |
| M4 | `clock.py:148` | Repeated midnight resolves to the **later** occurrence (`min` → `max`) | `test_clock_cutoff.py` | Killed (4 failed) |
| M5 | `clock.py:140` | Cutoff computed as deadline start **+ 24 hours** instead of next-day midnight | `test_clock_cutoff.py` | Killed (1 failed) |
| M6 | `domain.py:43` | Deadline upper bound accepts `9999-12-31` | `test_domain_validation.py`, `test_services_create.py`, `test_services_edit.py` | Killed (3 failed) |
| M7 | `storage.py:100` | Dated uniqueness predicate drops the `is_deleted = 0` condition | `test_services_uniqueness.py` | Killed (2 failed) |
| M8 | `storage.py:106` | Undated uniqueness predicate drops the `status = 'pending'` condition | `test_services_uniqueness.py` | Killed (2 failed) |
| M9 | `services.py:759` | Ledger replay **reapplies** the command instead of returning the stored result | `test_services_runner.py`, `test_services_edit.py` | Killed (4 failed) |
| M10 | `storage.py:247` | Commit ordering: terminal result returned with a rollback instead of `COMMIT` | `test_services_runner.py`, `test_services_create.py` | Killed (39 failed) |
| M11 | `pyproject.toml:9` | Runtime baseline lowered from `>=3.13` to `>=3.9` | full `tests/server` suite | **SURVIVED** (583 passed) |

Pass 1 result: 10 of 11 killed. Every mutation the brief named as a minimum target was injected and killed. The suite discriminates grapheme counting, accent retention, space collapsing, both exceptional-midnight rules, the deadline range bound, both uniqueness populations, ledger replay semantics and commit ordering. The lone survivor was M11.

### Pass 2 — re-verification at `5fe1955`

Fix commit `5fe1955` adds `tests/server/unit/test_packaging_metadata.py` (5 tests, standard library only; no source or existing test was touched). M11 was re-injected independently by the Verifier in a fresh worktree, under the same provenance discipline, in two lowering variants. Unmutated baseline in that worktree: 588 passed, exit 0.

| # | File | Mutation | Tests run | Killed? |
| --- | --- | --- | --- | --- |
| M11a | `pyproject.toml:9` | Baseline lowered `>=3.13` → `>=3.9` | full `tests/server` suite | **Killed** (4 failed, 584 passed) |
| M11b | `pyproject.toml:9` | Baseline lowered `>=3.13` → `>=3.12` (subtler, one minor version) | full `tests/server` suite | **Killed** (3 failed, 585 passed) |

Per-test breakdown, independently reproduced rather than taken from the fix author's report:

| Variant | `..._is_the_approved_minimum` | `..._excludes_the_preceding_version` | `..._excludes_the_superseded_minimum` | `..._admits_the_approved_minimum` | `..._written_as_the_approved_specifier` |
| --- | --- | --- | --- | --- | --- |
| `>=3.9` | FAIL | FAIL | FAIL | **PASS** | FAIL |
| `>=3.12` | FAIL | FAIL | PASS | PASS | FAIL |
| `>=3.13` (unmutated) | PASS | PASS | PASS | PASS | PASS |

This confirms the fix author's specific claim: on `>=3.9`, exactly 4 of the 5 tests fail and `test_the_declared_floor_admits_the_approved_minimum` correctly still passes, because that test guards the *upper* bound — it catches a floor raised above the approved minimum, not one lowered below it. Its passing on `>=3.9` is correct behavior, not a weak assertion.

**Overall sensor result across both passes: 12 distinct behavior-level mutations judged, 12 killed, 0 survived.**

### Adequacy probes on the new tests (characterization, not regressions)

Three further variants were injected to judge the new tests rather than the implementation:

| Variant | Outcome | Reading |
| --- | --- | --- |
| `>=3.14` (floor raised) | 3 of 5 fail, incl. `..._admits_the_approved_minimum` | Test 4 earns its place: it is the only guard against drifting *above* the approved decision |
| `>3.13` (excludes 3.13 itself) | All 5 fail | Correct: `>3.13` would exclude the approved minimum; the helper's `startswith(">=")` guard trips first |
| `>=3.13.0` (same floor, different spelling) | Only `..._written_as_the_approved_specifier` fails | The one assertion that can fail without a semantic regression — see the adequacy note in Finding 2 |

---

## Edge Cases

- [x] Blank input and exact bounds — 200/201 and 5,000/5,001 preserved in plain, combining and emoji forms (`test_domain_validation.py:119-209`).
- [x] Space normalization versus task identity — equivalence is comparison-only; identity is a server UUID and survives a title change (`test_domain_title_key.py:96`, `test_services_edit.py:375`).
- [x] Partial edit with invalid data or conflict — whole persisted task compared before and after (`test_services_edit.py:485`, `test_services_uniqueness.py:563`).
- [x] Competing conflicting creations or edits — `tests/server/integration/test_concurrency.py` exercises overlapping writes on independent connections with explicit synchronization; at most one conflicting state is accepted.
- [x] Lost response or overlapping repeated attempts — persisted state and original outcome inspected, not merely response receipt (`test_services_runner.py:339-357`, `test_api_operations.py`).
- [x] Cutoff boundary — September 14/15 00:00 preserved with no grace period (`test_clock_cutoff.py:77-90`).
- [x] Existing completed or deleted comparison candidates — isolated fixtures used, as 1A requires (`test_services_uniqueness.py:402, 479, 492`).
- [x] Unknown lookup distinct from rejection — `404 OPERATION_RESULT_UNKNOWN` versus a `200` stored rejection (`test_api_operations.py:281, 234`).

---

## Code Quality

| Check | Status |
| --- | --- |
| No features beyond what was asked | Pass — no lifecycle, metrics or emphasis code; 1A writes pending tasks only |
| No abstractions for single-use code | Pass — no ORM, repository layer, broker or job queue, as the Design requires |
| No unnecessary flexibility added | Pass — `Clock` is the only substitution point |
| Only touched files required for the tasks | Pass — changes confined to the approved module list and supporting locations |
| Didn't improve unrelated code | Pass |
| Matches existing patterns/style | Pass — Ruff (79-col, Google docstrings) and mypy strict both clean |
| Tests map to acceptance criteria and are non-shallow | Pass — assertions target stored state and published contract values, not internal calls |
| Spec-anchored outcome check | Pass for 50 criteria; PCE-44 partial, PCE-47 unmet |
| Per-layer coverage expectation | Pass — domain rules map 1:1 to criteria; every `/v1` route has happy, edge and error coverage |
| Every test maps to a spec requirement | Pass — each module header records its PCE and REQ IDs |
| Documented guidelines followed | Pass — `AGENTS.md` (Python 3.13+, annotations, Google docstrings, isolated disposable test databases) and the 1A Design gates |

Traceability is recorded per module rather than per test function. That is adequate for review but means a single criterion's evidence must be located by reading the module, which is why this report cites line-level assertions.

Tests use newly allocated temporary directories and disposable databases, and `test_durability.py:505` proves a configured runtime path cannot be reached by a test. No real database was touched by this validation.

---

## Findings

### Finding 1 — PCE-47 private Tailscale access is UNMET (Blocker, external)

- **What:** No evidence exists that the server is reachable only through the private tailnet. `tests/server/integration/test_api_app.py` verifies the *absence of a product sign-in* (PCE-46), which is genuinely local, but no test exercises a Tailscale path. `docs/architecture/deployment/server.md` and `docs/architecture/deployment/task-analyzer-server.service` describe the intended setup; the Design states plainly that documentation alone cannot satisfy PCE-47.
- **Why it cannot be closed here:** The target is the user's own Ubuntu server. Establishing the tailnet hostname, HTTPS availability and authorized device access requires an explicitly authorized deployment session, which has not occurred.
- **Resolution:** Not a code defect and not fixable locally. It requires an authorized session on the target host, recording service startup/restart, configuration retention and access from an authorized desktop through Tailscale.

### Finding 2 — PCE-44's declared baseline was not test-discriminated — **RESOLVED 2026-09-14**

- **Original defect:** `pyproject.toml:9` declared `requires-python = ">=3.13"` correctly, but no test asserted that value. Mutation M11 lowered it to `>=3.9` and the entire 583-test suite still passed, because the session interpreter is 3.13.2 and `Requires-Python` only bites when installing on an older interpreter. A future edit reversing the baseline the user raised from 3.11 on 2026-09-13 would have passed every gate unnoticed.
- **Fix:** Commit `5fe1955`, authored by an implementer and verified here, adds `tests/server/unit/test_packaging_metadata.py` — 5 tests, standard library only, parsing `requires-python` with `tomllib`.
- **Verification:** Re-injected M11 in two lowering variants in an isolated worktree; both killed (M11a, M11b above). The mutant that previously survived a full-suite run now fails it.
- **Adequacy judgment — accepted, with one note.** Each test maps to PCE-44/REQ-003 and none is shallow:
  - `:46` pins the parsed floor exactly; `:51` and `:56` encode the excluded versions explicitly, including the superseded 3.11 the user moved away from; `:61` guards the opposite direction (a floor raised above the approved minimum) and is the only test that does so; `:68` pins the literal specifier spelling.
  - `:51` and `:56` are logically implied by `:46`, so they are mild redundancy rather than independent coverage. At this cost they read as intent documentation and are not worth rejecting.
  - `:68` is the one assertion that can fail without a semantic regression: `>=3.13.0` denotes the same floor but fails it. That is defensible — the specifier is an approved value and any edit to it should be deliberate — but it is a spelling pin, not a semantic one, and should be understood as such rather than as a second check of the floor.
  - Avoiding `packaging` is correct: it is a transitive dependency in the locked environment, not a declared one, so depending on it would have introduced an undeclared test dependency contrary to AGENTS.md.
  - **Scope limitation (accepted, not a defect):** all five read the checkout's `pyproject.toml`, not the built wheel's `Requires-Python` metadata. In practice these agree, because `test_installed_distribution.py` builds from a copy of the same file. The tests therefore pin the *declaration*; they do not and cannot pin the interpreter on the deployment target.
- **Residual:** none locally. The target-interpreter half of PCE-44 moves to Finding 3.

### Finding 3 — PCE-44's target interpreter is unverified (Blocker, external)

- **What:** The declared baseline is now pinned, but no evidence exists of the interpreter version set actually installed on the Ubuntu Server 26.04.1 LTS target. AD-003's host-compatibility prerequisite and the Design's target-lock requirement are both still open.
- **Why it cannot be closed here:** The local lock was resolved on Windows against Python 3.13.2. The Design states explicitly that a local lock does not establish target compatibility.
- **Resolution:** Requires the same authorized deployment session as Finding 1 — confirm the target interpreter, produce and validate the target-specific lock, and run the gates on that environment.

### Observation — the worktree sensor needs a PYTHONPATH override (process, no code change)

The editable install pins imports to the real checkout, so any mutation-based verification run from a scratch worktree silently tests the unmutated source unless `PYTHONPATH` points at the worktree package root. This produced a false all-survived result on the first attempt. Any future re-verification must keep the provenance guard described in the Sensor section.

---

## Requirement Traceability Update

Proposed statuses. Nothing is marked `Verified`, because the Design conditions `Verified` traceability on the external evidence that remains outstanding.

| Requirement | Previous | Proposed | Basis |
| --- | --- | --- | --- |
| REQ-007 | In Execute | Locally verified | PCE-01 to PCE-10, PCE-11, PCE-14 to PCE-16, PCE-48, PCE-51, PCE-52 all matched |
| REQ-008 | In Execute | Locally verified | PCE-01, PCE-11, PCE-12, PCE-14 to PCE-16, PCE-27, PCE-52 all matched |
| REQ-010 | In Execute | Locally verified | PCE-07, PCE-11, PCE-16, PCE-34, PCE-36, PCE-37, PCE-40 all matched |
| REQ-011 | In Execute | Locally verified | PCE-08, PCE-32, PCE-33, PCE-49, PCE-50 matched against independent oracles |
| REQ-028 | In Execute | Locally verified | PCE-13, PCE-28 to PCE-31, PCE-35 all matched |
| REQ-029 | In Execute | Locally verified | PCE-12, PCE-17 to PCE-27, PCE-41, PCE-42 all matched |
| REQ-031 | In Execute | Locally verified | PCE-26, PCE-37 to PCE-43 all matched |
| REQ-003 | In Execute | **Blocked** | PCE-45 matched; PCE-44's declared baseline now pinned and discriminated, target interpreter still unverified (Finding 3) |
| REQ-027 | In Execute | **Blocked** | PCE-46 matched locally; PCE-47 has no evidence and is externally blocked |

---

## Summary

**Overall: Not ready — every local check passes, feature completion is blocked externally.**

- **Spec-anchored check:** 51/52 criteria fully satisfied within the locally verifiable scope; 0 spec-precision gaps; PCE-44 local half covered, target half pending; PCE-47 unmet.
- **Sensor:** 12 distinct mutations across two passes, **12 killed, 0 survived**.
- **Gate:** 5/5 green — format, lint, mypy strict, 588 tests, pip check, all exit 0.

**What works.** The behavioral core is implemented accurately and the tests genuinely discriminate it. Grapheme-cluster counting, accent-preserving comparison keys, both exceptional-midnight rules with independently sourced IANA oracles, the inclusive `0001-01-01`..`9999-12-30` range, the two distinct uniqueness populations, single-transaction mutation-plus-outcome commit, replay without reapplication, and unknown-versus-rejection separation each survived targeted fault injection. The approved protected values — 200/201, 5,000/5,001, `Read notes` / ` READ  NOTES `, `Review résumé` / `Review resume`, September 14/15, the `Pacific/Apia` `2011-12-30T10:00:00.000000Z` oracle — are all present and unaltered.

The declared runtime baseline is now pinned too: lowering it one minor version is enough to fail the suite.

**Issues found.** Finding 2 (test-coverage gap) is **resolved** by `5fe1955` and independently re-verified. What remains is entirely external: Finding 1 (PCE-47 private access) and Finding 3 (PCE-44 target interpreter). Neither is a code defect and neither can be closed locally.

**Next steps.**

1. No further local work is required for delivery 1A. There is no open fix task.
2. Leave PCE-47 and PCE-44's target-interpreter half open until an explicitly authorized deployment session on the user's Ubuntu server produces the evidence. Local task completion cannot substitute for it.
3. Do not mark delivery 1A complete, and do not record `Verified` traceability, until both are closed. `validate_state.py` will correctly keep exiting 1 while the verdict stands at FAIL — that exit is the intended signal here, not an obstacle to work around.

---

## Open questions

- When will an authorized deployment session on the user's own Ubuntu server take place, so PCE-47's private-access evidence and PCE-44's target-interpreter evidence can be recorded? Until then delivery 1A stays incomplete regardless of local results.
- Which tailnet hostname, authorized device identifiers, installation paths and installed interpreter version set will that session use? These values are still owed by the user and are not decided by this report.
- **Resolved 2026-09-14:** the PCE-44 baseline regression assertion landed as a standalone `tests/server/unit/test_packaging_metadata.py` reading the checkout's `pyproject.toml`. Should it additionally assert the built wheel's `Requires-Python` metadata inside `test_installed_distribution.py`? Not required to close Finding 2, and only worth doing if the wheel could ever be built from metadata other than that file.
- Should per-test PCE annotations supplement the current per-module headers, to make future criterion-level re-verification cheaper? This is a documentation preference, not a defect, and needs no behavioral approval.
