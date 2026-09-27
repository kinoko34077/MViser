# KiNoTch. Base / Runtime Roadmap

この文書は共通層から参照する短いRoadmap Indexである。詳細な判断基準は
[`../meta/README.md`](../meta/README.md) と各正本Metaを参照する。

## Phase 0 / 0.5 — Repository Base

- Base / Project境界、AGENTS、Manifest、Schema、knt router
- doctor / verify / base-check / base-refresh
- deterministic Base protection、self-test、Meta、Project template

## Phase 1 — Runtime reference

- Python reference kernel and Runtime Execution Contract
- Runtime packageとBaseの責任分離

## Phase 2A — Portable Contract validation

- jev-audit、kinotch-api、SynTrail-LM、standby-display、dev_agentのPilot
- Portable meaningの成熟度を評価する。Default導入をブロックしない。

## Phase 2B — Default extraction

- `DEFAULT` / `OVERRIDE` / `DISABLED`
- Surface DefaultとTool Defaultを分離
- Catalog駆動init / migrateと非破壊境界

## Phase 3 — Default implementation

現行Base v0.5.3でSurface Default実装、Hosted CI、Root/link境界、Default lifecycle、同一Base version保護を固定する。

- Surface Kits: `minimal`, `web-app`, `cli`, `windows`, `mcp`, `api`, `agent`, `library`
- Tool Defaults: `ci-test`, `generated-integrity`, `file-io`, `pwa`, `config`, `logging`
- provenance、template-driven doctor、PWA finalization、CLI/API契約、Windows CI

## Phase 4 — init / migrate and Canary adoption

read-only probe、explicit apply、Base-local write boundary、OVERRIDE preservationを
検証済み。既存repoへ一括適用せず、採用状態を個別に記録する。

## Phase 5 — gradual repository adoption / maintenance (current)

新規repoでは必要なDefaultを選択できる。既存repoはactiveな改修時だけ、既存実装を
`OVERRIDE`として保持できるか確認し、必要なら明示的に同期する。Base変更は、複数repo
で反復するbug・手作業・安全問題が確認された場合に限定する。

## Phase 6 — only if actual need appears

Version migration、multi-language binding、generated descriptor等は、実Projectで
現行DefaultやRuntime境界が不足した場合のみ検討する。Defaultを理由にRuntimeを
拡大しない。
