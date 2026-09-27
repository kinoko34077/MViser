# GitHub Development Control — Repository Base Integration

## 目的

本書は、KiNoTch. Repository Base と横断GitHub開発管理基盤の**接続境界**だけを定義する。

横断的な状態語彙、Repository Control、Work Order、Audit level、Finding escalation、GitHub Project field、同期方式、Agent操作境界の正本は本Repositoryでは所有しない。

現在の横断正本:

- Repository: `kinoko34077/devflow`
- Canonical specification: `docs/spec/CROSS_REPOSITORY_DEVELOPMENT_CONTROL.md`
- Project synchronization operations: `docs/project/PROJECT_SYNC.md`
- Machine-readable workflow definition: `.devflow/WORKFLOW.yaml`
- Current cross-repository state: devflowのRepository Control Issue / Work Order
- Derived display: GitHub Project `KiNoTch. Development Control`

本書とdevflow正本が衝突する場合、devflow正本を優先する。

## 1. Authority boundary

横断管理の権限方向は次のとおりとする。

```text
individual repository canonical state
  -> devflow canonical operational state
  -> Project synchronizer
  -> GitHub Project display
```

GitHub Projectは表示・俯瞰層であり、横断Current Stateの正本ではない。
Project値からRepositoryやdevflow Issueへ逆同期して正本化しない。

各RepositoryのDomain仕様・実装・詳細Current Stateは各Repository自身が所有する。devflowは横断的な要約・監査SHA・優先度・Risk・Next Action等を保持し、詳細仕様を複製しない。

## 2. Repository Baseとの分離

横断管理対象に登録されることとRepository Base adoptionは別概念である。

Repository Control IssueやGitHub Project Itemが存在しても、以下を自動的には意味しない。

- Base adoption
- Base-managed fileの同期
- Default Pack導入
- Runtime統合
- Repository構造の統一
- 定期FULL audit

Base adoption stateは既存Phase 5規則どおり、必要な場合のみ以下で扱う。

```text
ADOPTED / STAGED / NOT_ADOPTED / N/A
```

具体的なProject側の反復コストや共通問題が確認できない限り、一括adoptionや一括Base同期を行わない。

## 3. Repository onboarding

横断基盤へRepositoryを実運用化する初回監査では、Base adoptionより先に次を確認する。

1. default branchの具体的な監査SHA
2. Repository固有の仕様・Current State・テスト/verify入口
3. 現在のRepository State / Risk / Priority / Next Action
4. PR-only運用が技術的または運用規則として成立しているか
5. Base adoptionが既に存在するか、または具体的に必要か

`.kinotch/`がないRepositoryは、それだけを未完了扱いしない。まずread-only shape probe / STANDARD auditで既存構造を確認し、既存正本を尊重する。

## 4. Project field compatibility

Base文書内でProject fieldへ言及する必要がある場合、現行devflow mappingを参照する。

特に旧名称を正本として固定しない。

- devflow `Work Status` -> Project built-in `Status`
- devflow `Type` -> Project custom `Work Type`
- devflow `Repository` -> Project custom `Managed Repository`

その他のfield、option、workflow設定はdevflow正本から取得し、本書へ複製しない。

## 5. Audit / Work Order

QUICK / STANDARD / FULL、Finding escalation、Work Order必須項目、Audit SHA等の横断運用定義はdevflow正本に従う。

Repository Base固有の追加条件は次のみである。

- Base-managed fileとProject-owned fileの境界を確認する。
- `DEFAULT / OVERRIDE / DISABLED`を既存実装へ強制上書きしない。
- Base変更候補はPhase 5 return conditionを満たす場合にのみBaseへ昇格する。
- 個別repoの問題をBase側の共通問題として推測で一般化しない。

## 6. Agent operation boundary

通常のRepository変更はdefault branchへ直接書かず、専用branchとPull Requestを経由する。

要件が十分に定義されている場合、Agentは現行取得、関連正本確認、QUICK/STANDARD監査、finding整理、Work Order、branch、実装、検証、PR、再監査まで継続してよい。

**既にユーザーから包括的に許可され、Riskが低く、致命的問題の可能性が低く、revert PRで安全に戻せるmergeは追加確認なしで進めてよい。**

以下は引き続き実行前のユーザー確認を必要とする。

- release
- deploy
- publication
- destructive delete / history rewrite
- security-sensitive permission / credential changes
- その他、復元困難または外部へ確定的に反映される高Risk操作

問題がmerge後に発覚した場合、shared `main`を書き換えずdedicated rollback branch + revert PRで戻す。

FULL auditは定期実行せず、明示依頼または具体的必要性がある場合に限る。

## 7. Verification handoff

通常Chat等がPrivate GitHub Projectを直接確認できない場合、devflowの以下を通常確認経路とする。

1. `[SYSTEM] GitHub Project Sync Health`
2. 対象Repository Control Issue
3. active Work Order / repo-local Issue / PR
4. 必要なActions run/log

Project構造変更、APIで検証不能なUI条件、machine/UI不一致、`CODEX_REQUIRED`、明示要求がある場合のみCodex等のProject-capable agentへ直接確認をhandoffする。

## 8. Phase 5との関係

`.kinotch/meta/07_PHASE5_OPERATIONS.md`の方針を維持する。

横断的な可視化・監査・Work Order運用を全Repositoryへ適用することは、全RepositoryをBase-managed構造へ変更することではない。

Baseは共通化の必要性が具体的に成立したときだけ同期・更新する。
