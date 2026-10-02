---
phase: 14-operator-dashboard-alerting
plan: "05"
subsystem: auth
tags: [web, sqlite, scrypt, sessions, typer, waitress, isolation]
requires:
  - phase: 14-02
    provides: Verified pinned web dependencies and bot-web script declaration
  - phase: 14-03
    provides: Temporary operator evidence fixtures and bounded read contracts
provides:
  - Immutable credential-free WebSettings and registered source authority
  - Independently versioned operational operator/session/action/artifact storage
  - Dedicated scrypt authentication and concurrent absolute twelve-hour sessions
  - Hidden local setup/reset and lazy production Waitress serving CLI
affects: [14-06, 14-07, 14-08, 14-09, 14-10, 14-12]
tech-stack:
  added: []
  patterns: [independent metadata owner, fixed registered resource IDs, server-authoritative absolute sessions, transactional login throttle]
key-files:
  created: [trading_bot/web_config.py, trading_bot/web_store.py, trading_bot/web_auth.py, trading_bot/web_cli.py, tests/test_web_config.py, tests/test_web_store.py, tests/test_web_auth.py, tests/test_web_cli.py]
  modified: []
key-decisions:
  - "WebSettings reads only init values and BOT_WEB_ environment; dotenv and trading Settings are excluded."
  - "Source directory topology is reserved even for missing evidence; writable operational/artifact roots must be separate and source-disjoint."
  - "Password verification, throttle accounting and successful session issuance use one transaction, so reset cannot race an old-password login."
  - "Waitress serving requires exactly one explicit trusted proxy peer in private mode; wildcard trust is forbidden."
requirements-completed: [UI-02]
coverage:
  - id: D1
    description: Independent settings, registered sources and write topology
    requirement: UI-02
    verification:
      - kind: unit
        ref: tests/test_web_config.py
        status: pass
      - kind: integration
        ref: tests/test_web_store.py
        status: pass
    human_judgment: false
  - id: D2
    description: Dedicated operator password, persistent throttle and independent twelve-hour sessions
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_web_auth.py
        status: pass
    human_judgment: false
  - id: D3
    description: Hidden local provisioning/reset and validated production-serving adapter
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_web_cli.py
        status: pass
    human_judgment: false
duration: 14min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 05: Operator Authentication and Storage Summary

**원본 쓰기 권한과 분리된 운영 SQLite, 전용 scrypt 암호, 독립적인 12시간 절대 세션 및 로컬 bot-web 명령을 구현했다.**

## Performance

- Started: 2026-10-02T01:32:18Z
- Completed: 2026-10-02T01:45:51Z
- Duration: approximately 14 minutes
- Tasks: 3/3
- Files created: 8 implementation/test files and this summary
- Execution: sequential main checkout, existing main branch preserved; no worktree

## Accomplishments

- 불변 WebSettings/ResourceDescriptor는 거래 capability/secret 필드를 거부하고, `.env`를 로드하지 않는다. ID 기반 등록과 양의 account hash/target/owner/schema attribution을 사용한다. 기본값은 127.0.0.1:8765, 50/100 rows, 31일 export, hard maximum 366일·10,000 rows·10MiB다.
- 매 운영 파일 open 전에 원본 root, operational parent, artifact root의 topology를 검사한다. 동일·상하위 경로, symlink component, hardlink, 기존 writable tree 안의 링크 및 source/artifact 충돌을 거부한다. 원본은 내용 연결·migration 없이 metadata만 검사한다.
- phase14_web_metadata version 2는 PRAGMA user_version과 분리된다. 초기화·재시작·v1→v2 upgrade·실패 rollback·미래 버전 및 foreign-owner DB 거부를 검증했다. 신규 directory는 0700, 운영 DB는 0600이다. action audit는 append-only이고 자유 텍스트 대신 bounded codes/IDs/numeric detail만 허용한다.
- Werkzeug `scrypt:131072:8:1`로 전용 암호를 저장한다. 32-byte 난수에서 만든 opaque session token은 hash reference만 DB에 저장한다. 서버 issued_at부터 정확히 43,200초 뒤 만료하며 polling은 시간을 바꾸지 않는다. PC/phone 로그인과 로그아웃은 독립적이고 로컬 암호 재설정은 전체 세션을 폐기한다.
- 계정 및 source address별 실패는 5분에 5회로 제한하고 DB에 hashed buckets를 저장한다. 최대 2,048 buckets, 실패 카운트 최대 5, 잠금 기간 중 암호 검증을 생략한다. unknown identity와 잘못된 암호는 동일한 실패로 응답한다. 암호 검증과 성공 세션 발급은 동일 writer transaction이다.
- `bot-web setup`, `reset-password`, `serve`는 보호된 `--config` JSON을 읽는다. setup은 암호 확인을 숨기고 기존 계정 덮어쓰기를 거부한다. signing secret은 0600 config에 원자적으로 저장된다. serve는 factory/Waitress를 lazy import하고 debug/tracebacks를 끈다. 테스트는 fake app/server를 사용하고 네트워크를 열지 않는다.

## Task Commits

1. T1 RED: `961a90a` — test(14-05): define credential-free settings and storage boundaries
2. T1 GREEN: `95f9294` — feat(14-05): isolate web settings and operational storage authority
3. T2 RED: `b6b84e2` — test(14-05): define absolute sessions and persistent login limits
4. T2 GREEN: `b8b3923` — feat(14-05): enforce dedicated auth and independent absolute sessions
5. T3 RED: `2d6fa20` — test(14-05): define hidden operator CLI and safe production serve
6. T3 GREEN: `c01c5f8` — feat(14-05): add isolated local operator setup reset and Waitress serve

Normal git hooks were retained. No tracked file deletions occurred. No REFACTOR stage was required. STATE/ROADMAP/REQUIREMENTS/VALIDATION updates remain the parent orchestrator's ownership under the plan output contract.

## Verification

Actual executed commands and outcomes:

| Command | Outcome |
| --- | --- |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_config.py tests/test_web_store.py` before implementation | RED: 2 missing-module collection errors, 0.09s |
| Same command after implementation | 22 passed in 0.09s |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_auth.py` before implementation | RED: missing web_auth collection error, 0.08s |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_auth.py tests/test_web_store.py` | 13 passed in 1.27s |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_cli.py` before implementation | RED: missing web_cli collection error, 0.09s |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_cli.py tests/test_web_auth.py` | 15 passed in 1.52s |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_config.py tests/test_web_store.py tests/test_web_auth.py tests/test_web_cli.py` final | **37 passed in 1.58s** |
| `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m trading_bot.web_cli --help` | All three dedicated commands reachable |
| AST import scan of four new modules | No config/cli/broker/llm/sqlite_audit/soak_store/portfolio_store/mutation_lease imports |
| Stub scan of four modules | No TODO/FIXME/placeholder/coming-soon/unwired UI patterns |

Every focused command was below 60 seconds. Parent runs the full regression suite at the wave boundary; no full-suite result is claimed here.

### Threat Negative Checks

| Threat | Tests/evidence |
| --- | --- |
| T14-PATH | Six equal/parent/artifact/symlink/hardlink/nested source overlap cases; nested artifact aliases; source bytes unchanged; path-ID injection rejection; construction-to-initialization link swap rejection; foreign-owner rejection and migration rollback |
| T14-AUTH | Random salted real scrypt integration; wrong/unknown account failure; persistent per-account and source lock; forged/expired/revoked tokens; exact 12h minus epsilon versus boundary; polling does not slide; independent phone/PC sessions/logout; reset revokes all |
| T14-PROXY | Public/wildcard/default remote bind rejection; private origin/HTTPS/host/proxy negative settings; validated serve host override; fake production server receives only one trusted IP and one proxy hop; debug off and untrusted-header clearing enabled |
| T14-DISCLOSURE | Cookie SecretStr repr; operator hash/session reference redaction; password/token/secret sentinels absent from DB audit and CLI errors; hidden setup/reset confirmation; unknown login identifiers stored as hashes |

Actual HTTP Host/origin/proxy enforcement, cookie flags and CSRF are owned by 14-10 and tested by subsequent security plans. This plan verifies configuration and server adapters, and makes no HTTP security certification claim.

### Hash Cost Measurement

The working Python 3.14.3 interpreter measured a single real `hash_password("synthetic-cost-measurement-password")` with `time.perf_counter()` and `resource.getrusage(RUSAGE_SELF).ru_maxrss`:

- Method: scrypt:131072:8:1
- Hash wall time: **0.2887s**
- Process peak RSS on macOS: **180,486,144 bytes**, approximately 172.13MiB (includes interpreter/import overhead; this is not incremental hash allocation)
- Parameter memory term is approximately 128MiB; no silent downgrade to the library default occurred.

The real-parameter test also checks correct/wrong password verification and random salt differentiation. Other auth/CLI tests inject a fast deterministic test hasher, never owner passwords.

## Downstream API Contract

- `WebSettings(**values)` is independent frozen BaseSettings with `BOT_WEB_` environment prefix; `settings.resource(resource_id)` resolves only registered IDs; `settings.validate_topology()` returns canonical operational DB/artifact Paths after source-disjoint checks. ResourceDescriptor fields are `id`, `path`, `owner`, `schema_family` (defaults to owner), `account_hash`, `target`; `resource_id` aliases id. Missing resources are reserved paths and remain unavailable to readers.
- `WebStore(settings).initialize()` handles only web-owned metadata. `connection()` provides a bounded SQLite writer transaction after topology/ownership checks. 14-08 may place its own independently versioned alert metadata/tables in this operational DB; it must not change phase14_web_metadata or PRAGMA user_version. Future versions of phase14_web_metadata are refused.
- Operator/session methods: `get_operator()`, `provision_operator(username,password_hash,at,reset=False)`, `create_session(reference_hash,issued_at,expires_at)`, `get_session(reference_hash)`, `revoke_session(reference_hash,at)`, `revoke_all_sessions(at)`. All at values must be aware datetime objects. `get_operator()` returns Operator or None; session rows return immutable Session with actor/issued_at/expires_at/revoked_at. Do not expose hash/reference fields.
- `append_action(actor=...,action=UPPERCASE_CODE,result_code=UPPERCASE_CODE,at=...,resource_id=None,details=None)` is append-only. Details allow only `row_count`, `byte_count`, `attempt_count` nonnegative integers bounded at 10,000,000; raw prompts/errors/passwords/tokens/notes are intentionally unavailable. Notes for incident acknowledgement belong to 14-08's bounded sanitized alert schema.
- `record_artifact(artifact_id,resource_id=...,actor=...,filename=...,format=...,at=...)` requires a registered resource, fixed `artifact_id.{txt|json|csv}` basename and safe artifact topology. `get_artifact(artifact_id,actor=...)` returns only that actor's ReportArtifact metadata. The report writer still owns bounded content creation and authenticated download.
- `WebAuth(store,clock=...,hasher=...,verifier=...)`: `provision_operator(username,password)` and `reset_password(password)` are local-only. `authenticate(username,password,source_address)` returns opaque token or None; use only a server-validated client IP. `validate_session(token)` returns Session or None on **every protected request**, and never updates expiry. `logout(token)` revokes the current client. Reuse one auth service instance per app; signed Flask session must contain only opaque token/CSRF material.
- `web_cli.load_settings(config,host=None,port=None)` revalidates overrides and protected local config. `_create_app(settings)` lazily imports `web_app.create_app(settings)` from 14-10; `_serve(application,**options)` calls Waitress. In private mode Waitress's API accepts one trusted peer IP, so CLI requires exactly one registered proxy, count=1, explicit x-forwarded-{proto,for,host,port}, and clearing untrusted headers. Settings may describe multiple private IPs, but serve fails closed until exactly one is selected. 14-10 must enforce Host/origin and authentication after server proxy normalization.

## Decisions Made

Followed D-05 through D-08 and the specified schema ownership boundary. Conservative topology validation reserves source directories rather than only DB filenames, including nonexistent registered files. Protected JSON config is explicit local authority, never browser input.

Official documentation was read after Context7 tools/CLI were found unavailable: [Werkzeug security helpers](https://werkzeug.palletsprojects.com/en/stable/utils/), [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), [Waitress proxy arguments](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html). Waitress documents a single trusted peer IP; the CLI enforces that concrete limitation and never substitutes wildcard trust.

## Deviations from Plan

None requiring architectural changes. The CLI's single trusted-proxy requirement makes the reviewed production server API fail closed. Parent-owned planning state was deliberately left for orchestrator updates as specified in the plan output.

## Issues Encountered

During T1 GREEN, Pydantic's default regex engine rejected Python `\Z`; using the compiled Python pattern and explicit start anchor resolved the implementation/test feedback before the task commit. No package installation or authentication gates occurred.

## User Setup Required

No actual owner credential provisioning, business DB reads, HTTP listener, VPN deployment, scheduler, KIS/LLM/Discord call or additional package installation was performed. Optional real local setup requires an owner-protected registered JSON configuration and a dedicated password; actual serving awaits 14-10's app and later end-of-phase acceptance. All tests used temporary independent DBs and synthetic identities.

## Next Phase Readiness

14-06/07 readers/reports and 14-08/09 alert storage can consume the registered settings and independent operational DB. 14-10 supplies Flask cookie/CSRF/request guards and the app factory; that absence is an intentional later-plan dependency, not an implementation stub. No goal-blocking stubs remain in this plan.

## Self-Check: PASSED

- Eight created implementation/test files exist.
- All six RED/GREEN task commits exist in git history.
- SUMMARY exists; owned files contain no unfinished stub pattern or unauthorized capability import.
- Final focused verification passed: 37 tests. Normal hook commits retained the branch and introduced no tracked file deletions.
