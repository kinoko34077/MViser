# 04 — Extraction Criteria

個別repo内の仕組みを、Hard Base、Default、Portable Contract / Runtime、
Project、Domain Libraryのどこへ置くかを決める基準。

## 判断順

```text
候補 X
  ↓
Repository運用そのものに必須か？
  ├─ Yes → L1 Hard Base
  └─ No
       ↓
Domain意味を持たず、安全に外せて、毎回の実装を減らすか？
  ├─ Yes → L2 Default
  └─ No
       ↓
異なる実装で同じ意味・責任・変更理由を共有する必要があるか？
  ├─ Yes → L3 Portable Contract / Runtime候補
  └─ No → L4 Project / Domain Library
```

## A. L1 Hard Base

Repositoryの配置・規則・操作入口・検証を所有する。

- `AGENTS.md`、`.kinotch/`、`project/`境界
- Project Manifest、Profile、Surface宣言、Schema
- `knt setup/test/build/verify/smoke/doctor`語彙
- doctor、verify、base-check、base-refresh
- Base保護、Default Catalog、init / migrateの安全境界

Project固有情報、Domain処理、公開API policy、永続形式は入れない。

## B. L2 Default

低リスクで安全に外せる共通実装。`DEFAULT`、`OVERRIDE`、`DISABLED`だけで
Project単位の採用状態を表す。

現行Surface Kit:

- CLIの共通option、JSON / stderr / exit補助
- Windowsのpicker、Save、D&D、Progress、Cancel、Explorer / Clipboard境界
- MCPのtool name、input validator、Project path、diagnostic、capability補助
- APIのrequest context、health、permissive envelope、replaceable hook
- Agentのinvocation context、diagnostic、capability、boundary hook

現行Tool Default:

- `ci-test`
- `generated-integrity`
- `file-io`
- `pwa`
- `config`
- `logging`

Defaultは既存Frameworkを置き換えず、Domain format、公開error taxonomy、
deploy、auth方式、authority、永続状態、Runtime moduleを所有しない。

## C. L3 Portable Contract / Runtime

複数repo・異種実装で同じ実行意味を共有する必要があり、変換層より削減効果が
大きい場合だけ候補にする。Pilotや成熟度評価はここに限る。

例: operation identity、input、request/correlation identity、error semantics、
narrow progress / artifact reference。PythonのActionRegistry、例外型、
PowerShellのSurface helper、Hono / Rust固有のdispatcherはPortable Contract
ではない。

## D. L4 Project / Domain Library

- Domain Core、データモデル、UI状態機械、永続形式
- provider / deploy / auth / retry policy
- resource authority、AgentBackend、planner、memory
- 一度しか現れない処理、変更理由が他repoと異なる処理

複数repoで再利用するがRuntime一般機能でないものは、`kinotch-text`等の
独立Domain Libraryを検討し、Runtimeへ押し込まない。

## 昇格時の安全策

個別実装を即削除しない。共通版を作り、既存Frameworkを`OVERRIDE`として
保持したまま、対象repoの既存test / smokeで同等性を確認する。Defaultが
意味・設定・依存を増やすだけなら採用せず、Portable Contract候補がDomain差を
吸収できないならProjectまたはDefaultへ戻す。
