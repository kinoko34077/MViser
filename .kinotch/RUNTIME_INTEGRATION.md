# Repository Base and KiNoTch. Runtime responsibility boundary

この文書は、Repository BaseとKiNoTch. Runtimeを接続する責任境界を定義する。
Base versionやRuntime package versionを混同せず、Default実装をRuntime機能と
誤認しない。

## Repository Base owns

- Project Manifest、Profile、Repository structure
- Surface declaration and Default Catalog
- Base validation compatibility schemas
- Runtime version reference and explicit `runtime.modules` declaration
- `knt` command vocabulary、doctor、verify、Base integrity

Surface Profileの選択はRuntime moduleを自動選択しない。Runtimeを使用する
Projectだけが必要なmoduleをManifestへ明示する。

## Runtime owns

KiNoTch. Runtimeは、異なるRepository・言語・Surfaceで同じ実行意味を共有する
必要が確認されたExecution Contractと、そのreference implementationを所有する。

- Action execution semantics
- Action Result / Action Error execution semantics
- Progress、Cancellation、Resource、Artifactの確定したruntime behavior
- Runtime-specific bindings and execution lifecycle

ActionRegistry、ActionErrorException、Python dataclass、Hono Context、Rust
channel、Surface固有Responseなどは、Portable Contractでない限り各実装側の
primitiveである。

Runtime側で候補として評価するものには、`ActionRequest`、`ActionContext`、
Cancellation、Config execution semantics、filesystem / logging bindingがある。
候補は実装済みというだけで確定Contractやstableとは扱わない。

## Schema ownership

Runtime Execution Schemaのcanonical sourceはRuntime repositoryである。

```text
kinotch-runtime/project/contracts/execution/
        ↓ explicit, reviewed synchronization when needed
Repository Base .kinotch/schemas/ compatibility copy
```

BaseとRuntimeでExecution Schemaを独立編集しない。Base側のcopyはBaseが必要と
する互換検証のためだけに置き、自動同期は変更頻度とレビュー負荷が明確になる
まで導入しない。

## Defaultとの関係

CLI、Windows、MCP、API、AgentのSurface Kit、およびci-test、PWA、generated-
integrity、file-io、config、loggingはL2 Defaultである。これらは安全に外せる
実装補助であり、Runtimeへ昇格したことを意味しない。DefaultはFramework
dispatch、HTTP status / error taxonomy、auth、deploy、provider retry、Domain
state、authorityを固定しない。

## Integration shape

```text
Surface Default / Project Adapter -> Application / Domain Core
                                   +-> optional Runtime Contract
```

同一process内の共通化のためにGUI→HTTP、CLI→MCPなど不要なtransportを追加しない。
既存FrameworkやProjectのApplication boundaryがある場合、それをauthoritativeな
境界として利用する。

## Current Runtime reference

`kinotch-runtime`はRuntime package `0.1.0`のprovisional Python reference
implementationとExecution Contract正本を持つ。Portable Contractの成熟度は
Runtime側のContract Matrix / Pilot Reportで管理し、Baseは一括してstableと
みなさない。

`.ai-guidelines`はUI/UXおよびDomain横断設計policyを所有し、BaseはRepository、
Agent入口、implementation workflowを所有する。両者は全文を複製しない。
