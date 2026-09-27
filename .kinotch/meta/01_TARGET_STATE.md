# 01 — Target State

## 最終的に目指す開発体験

新規repoでは、開発者・Agentが最初に考える項目を極力次へ限定する。

- このプログラムは何をするか
- 入力は何か
- 出力は何か
- Domain Coreは何か
- どのSurface Default / Tool Defaultを採用するか
- どのPortable Contractが本当に必要か

それ以外は、Repository operationならHard Base、安全に外せる共通実装なら
Default、意味まで共有する実行契約ならRuntime / Portable Contract、固有の
意味ならProjectへ置く。

## Repositoryの最終像

```text
repository/
├─ README.md          # GitHub上の個別表紙
├─ AGENTS.md          # 共通
├─ .kinotch/          # 共通・原則編集禁止
├─ knt.cmd            # 共通操作入口
└─ project/           # 個別仕様・実装・設定
```

通常作業での判断は共通層と個別層を分ける。

```text
Repository運用を知る → .kinotch / Base
再利用可能なSurface補助を知る → 選択したDefault Kit
実行意味を共有する契約を知る → KiNoTch. Runtime
このrepo固有を知る → README.md / project/
```

## 責任層の最終像

Runtimeは一枚岩にせず、Defaultと混同しない。

```text
L1 Hard Base
  repository structure / manifest / doctor / verify / Base integrity
L2 Default Kits
  CLI / Windows / MCP / API / Agent helpers
  ci-test / generated-integrity / file-io / pwa / config / logging
L3 Portable Contract / Runtime
  only meanings proven across implementations
L4 Project Overlay / Domain
  algorithm / state / UI / persistence / provider / policy
```

Surface選択はRuntime module選択を意味しない。Runtimeを使うProjectだけが
`runtime.modules`を明示する。

## Surfaceの考え方

同じ処理をSurfaceごとに再実装しない。

```text
GUI ─┐
CLI ─┤
MCP ─┼→ Action / Application → Domain Core
API ─┤
Agent┘
```

共通化するのは「Fileを選ぶ」「Actionを実行する」「Errorを返す」等の意味であり、Windows File DialogやHTTP multipart等の物理実装まで同一化しない。

## 到達基準

この構想が十分進んだ状態では、新規小型ツールについて次が成立する。

1. Baseから開始するだけでRepository構造を再設計しなくてよい。
2. Agentは`AGENTS.md → project/project.json → docs`で迷わず着手できる。
3. `knt setup/test/build/verify/smoke/doctor`が技術スタック差を吸収する。
4. CLI、Windows、MCP、API、Agentの標準補助を必要なProjectだけ再利用できる。
5. ci-test、PWA、generated-integrity、file-io、config、loggingを必要なProjectだけ選べる。
6. Base / Default / Runtime更新と個別Domain変更が混ざらない。
7. Runtime不要moduleを読み込まず、Default選択だけでRuntime依存を増やさない。
