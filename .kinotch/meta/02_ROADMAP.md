# 02 — Roadmap

Current position: Phase 5 — gradual repository adoption / maintenance after the
v0.5.0 Default feature slice, v0.5.1 Hosted CI bugfix, v0.5.2 lifecycle, and
v0.5.3 integrity-boundary hardening
safety release.
Phase 3B safe Default behavior, Phase 4A read-only Canary validation, Phase 4B
adoption-safety hardening, and the Phase 4C adoption decision review are
complete. Eight repositories are recorded as cleanly adopted at Base v0.3.8;
Base v0.5.3 is the current Surface Default Kit safety/lifecycle release over the
v0.5.0 feature slice. Additional
repositories are explicitly staged, not adopted, or unavailable according to
the operation-state table in `project/docs/DEFAULT_ROLLOUT_DRY_RUN.md`.
Phase 2A Portable Contract validation remains independent and provisional;
Default adoption does not wait for Portable Contract maturity.

## Phase 0 — Repository Base v0.1系

目的: 個別差分と共通基盤の境界を実物として固定する。

含める:

- 共通 `AGENTS.md`
- `.kinotch/` 共通規約
- `project/` 個別領域
- Project Manifest
- Action / Result / Error / Progress / Resource / Surface Schema
- `knt` command router
- doctor / verify / base-check
- Current State / SPEC / ADRの最小骨格
- Base / Runtime構想のMeta資料

完了条件:

- 新規repoの開始点としてZIPをそのまま利用できる。
- 共通と個別の変更場所が迷わず判別できる。
- Baseファイルの意図しない変更を検出できる。

## Phase 1 — KiNoTch. Runtime Kernel v0.1

目的: 複数Surface / repoが共有する最小実装を切り出す。

初期候補:

- Action / ActionRequest / ActionContext
- ActionResult / ActionError
- Resource / Artifact
- Progress / Cancellation
- Config
- Filesystem
- Logging

注意:

- Domain処理は入れない。
- 言語横断では契約を優先し、巨大な共通libraryを無理に共有しない。

## Phase 2A — 代表repoでPortable Contractを検証

最低3系統で検証する。

1. CLI + MCP: `jev-audit`系
2. Windows GUI + CLI: `SynTrail-LM`系
3. API / Web: `kinotch-api` / `standby-display`系

追加候補:

- Agent: `dev_agent`
- Local GUI/Web: `srt2subtitle`
- Library/Web: `IDS-Composit`

目的は「移行すること」ではなく、**Base / Runtimeの意味を持つ抽象が実際に簡素化になるか検証すること**。

Phase 2Aでは、Default導入の可否をPortable Contract成熟度でブロックしない。

## Phase 2B — Default extraction

目的: Portable Contractの安定を待たず、低リスクで外せる共通便利機能を
Project単位で選択できるDefaultとして定義する。

- Default状態 `DEFAULT` / `OVERRIDE` / `DISABLED`
- CLI / Windows / MCP / APIのDefault候補整理
- 既存Framework・Project実装との二重化確認
- `knt init`の生成境界と非破壊条件
- Surface DefaultとTool Defaultを別軸で管理するDefault Catalog

DefaultはDomain処理、公開互換性、永続形式、provider policyを所有しない。

## Phase 3A — Default Catalog / state / selection

複数repoで厳密なPortable Contract証明を待たず、Default条件を満たすものを
Surface Default / Tool Defaultとして提供する。Projectからoverride / disable
できることを必須とする。Surface選択はRuntime module選択と独立させる。

### Surface Defaults

- `minimal`
- `web-app`
- `cli`
- `windows` (`windows-gui` profile alias)
- `mcp`
- `api`
- `agent`
- `library`

### Tool Defaults

- `ci-test`
- `generated-integrity`
- `file-io`
- `pwa`
- `config`
- `logging`

Default identifier・互換Surface・説明の正本は
`.kinotch/defaults/catalog.json` とする。

完了:

- Surface / Tool Defaultの分離
- 8 Surface profileと`windows` alias
- Runtime module自動注入の廃止
- Catalog駆動`init` / `migrate`
- `DEFAULT` / `OVERRIDE` / `DISABLED` state管理

## Phase 3B — Actual Default behavior

Safe, removable implementation slice complete. Catalogで選択したDefaultへ、
Domainを拘束しない実装を与える。

- `ci-test`: separate non-deploy GitHub Actions workflow with doctor→setup→verify
- `generated-integrity`: Project-root-safe source and artifact SHA-256 metadata、stale check、update helper
- `web-app` / `pwa`: relative-base manifest、pass-through service worker、registration helper、check
- `file-io`: format-independent callback boundary and UTF-8 text-only helper
- Surface helpers: `cli` JSON/error/help/exit, `windows` shell boundary, `mcp`
  tool guidance, and permissive `api` error-envelope schema

未実装・Project-owned:

- Pages deploy
- Domain-specific file format、GUI picker、D&D、provider retry
- Runtime module、ActionResult、Artifact domain object

### CLI

- common options
- JSON output
- stdout / stderr
- exit code
- dry-run

### Windows

- native menu
- File / Folder picker
- Save / Save As
- D&D
- Progress
- Cancel
- Error dialog
- Reveal output

### MCP

- Action → Tool mapping
- schema validation
- working-directory/resource resolution
- structured error

### API

- validation
- error envelope
- request ID
- auth hook
- rate-limit hook
- smoke / health

### Agent / Config / Logging

- `agent`: invocation context, diagnostics, capabilities, and named boundary hook
- `config`: explicit map merge and caller-selected secret redaction
- `logging`: UTC structured record, stderr rendering, and sink/redactor hooks

These are L2 helpers. They do not define Portable Runtime semantics.

## Phase 4A — Read-only Canary validation

Canaryごとのshape probeと既存検証を完了した。外部Baseを指定したshape
probeはread-onlyであり、既存repoへBaseファイルやDefaultを投入していない。

## Phase 4B — Adoption safety hardening

Surface / Tool互換性、doctor再検証、repository-local `.kinotch/` 書込み境界、
structured command引数、Project-root path containment、Default Catalog
semantic validation、既存ファイル衝突時のOVERRIDE記録、Project commandの
native exit code伝播と互換Shape候補フィルタを実装する。Base v0.3.8
としてこの安全点を固定した。v0.3.9ではDefault materializationのatomic
preflight、OS-aware path containment、Surface/Manifest consistencyを保守修正する。

## Phase 4C — init / migrate and existing repository adoption (complete)

既存repoは一括変更せず、`jev-audit`、`kinotch-api`、
`lyric_reader_page`、`weather-widget`、`memory-game`、
`Structured-Cell-Automaton`、`2bit-cell-automaton`、`colony-ai` の初回適用を完了した。
`refil-viewer` はBase適用準備まで完了したが、既存Vite build失敗のため
clean Canaryには数えない。`standby-display`、`SynTrail-LM`、
`dev_agent`、`IDS-Composit`、`srt2subtitle`を含む残りのrepoは、既存実装、
root hygiene、dirty worktree、またはcheckout可否を個別に確認し、導入しない
判断も含めてrollout tableへ記録した。残りのrepoへ一括適用しない。

- `knt init --profile <surface> --default <tool-default>`
- 複数Surface / Tool Default選択による初期化
- `knt migrate` dry-runと明示的`--apply`
- generated artifact管理
- stale check
- より詳細なdoctor
- Base conformance report
- ManifestなしRepositoryのread-only shape probe

`knt init` はCatalogを参照して選択SurfaceとTool Defaultの構成、Project
Overlayを生成する。Surface選択からRuntime moduleを自動注入しない。
`knt migrate` は差分を表示し、明示選択されたものだけ適用する。Domain
fileは自動書換えしない。Manifestなしのshape probeでは、既存相当実装を
`OVERRIDE`候補として表示し、既存repoへBase構造を自動投入しない。外部Base
overrideはshape probe専用で、既存repoのapplyには使用しない。

完了条件は全repoへのBase導入ではなく、代表repoごとの採用可否、Project
failureとBase failureの分離、全repoの運用状態記録、およびBase v0.5.0の
Surface Default Kit検証済み状態である。

## Phase 5 — 既存repoへの段階導入 / maintenance (current)

専用adoption campaignを継続せず、通常のProject作業に同期判断を組み込む。
Base v0.5.3を基準版として固定し、全repoを一括書換えしない。

- 改修するrepoから順次適用
- project固有ロジックは無理に移動しない
- 複数repoで反復確認できた知識だけBase / Runtimeへ昇格
- 既存互換性を壊してまで形式統一しない
- activeになったrepoだけ、必要ならread-only shape probeまたは既存Base状態を確認する
- `ADOPTED` / `STAGED` / `NOT_ADOPTED` / `N/A` の運用状態を維持し、
  Default stateの `DEFAULT` / `OVERRIDE` / `DISABLED` と混同しない
- 既存repoを改修するときだけ、必要ならBase同期後に`doctor`、
  `base-check`、既存`verify`を実行する
- Base変更は明確なBase bug、Security/Data loss、2repo以上の同一障害、
  同一手作業の反復、または現行Defaultで安全に表現できない共通問題に限定する
- 詳細な運用手順は [07_PHASE5_OPERATIONS.md](07_PHASE5_OPERATIONS.md) を参照する

v0.5.3でv0.5.0のSurface Kit安全実装範囲（CLI、Windows、MCP、API、Agent）と
Tool Default（ci-test、generated-integrity、file-io、pwa、config、logging）を
固定し、Root/link境界、provenance lifecycle、DISABLED cleanup、Surface別Project
CI runnerを追加した。以後は実Projectで同じ手作業や障害が反復した場合だけ、
追加のBase変更を検討する。v0.5.3では同一Base version保護、link/reparse-point
境界、Default所有pathに限定したlifecycle cleanupを固定した。

## Phase 6 — 安定化

必要性が実証された場合のみ進める。

- Base version migration policy
- Runtime version compatibility
- multi-language bindings
- generated docs / MCP / API descriptors
- project scaffolding高度化

Phase 6は必須到達点ではない。Base / Runtimeが十分単純なまま実用性を満たすなら、そこで止める。
