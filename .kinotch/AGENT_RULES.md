# Common Agent Rules

## Read Economy

毎回全ファイルを読まない。`AGENTS.md` の読取順序から開始し、現在問に必要な資料だけ取得する。

## Source of Truth

- 個別定義: `project/project.json`
- 個別仕様: `project/docs/`
- 現在状態: `project/docs/CURRENT_STATE.md`
- Action: `project/contracts/actions.json`
- Surface差分: `project/contracts/surfaces.json`
- Base Meta: `.kinotch/meta/`
- 新規Repository用Template: `.kinotch/templates/project/`

実装コードが仕様と衝突した場合、勝手にコードを正本化しない。

Base-wide MetaとTemplateは共通層に置く。個別Projectの情報を `.kinotch/` へ書かない。

## Cross-repository GitHub workflow

複数Repositoryの横断管理、GitHub Issue / PRを使った監査・実装運用、またはAgentのGitHub操作境界を扱う場合は、まず`.kinotch/meta/08_GITHUB_DEVELOPMENT_CONTROL.md`でBaseとの接続境界を確認し、横断運用の正本として`kinoko34077/devflow/docs/spec/CROSS_REPOSITORY_DEVELOPMENT_CONTROL.md`を参照する。

GitHub Projectは表示層であり、横断Current Stateの正本ではない。横断Current StateはdevflowのRepository Control Issue / Work Orderを参照する。

通常のGitHub変更はdefault branchへ直接書かず、専用branchからPull Requestを作成する。

要件が十分に定義されている場合、現行版取得、監査、Issue / Work Order作成、branch作成、実装、検証、PR作成、PR再監査までは継続してよい。

既にユーザーから包括的に許可され、Riskが低く、致命的問題の可能性が低く、revert PRで安全に戻せるmergeは追加確認なしで進めてよい。

release、deploy、publication、破壊的削除、history rewrite、security-sensitive permission / credential変更、その他復元困難または高Riskの確定操作は実行前にユーザー確認を得る。

監査ではAudit SHAを残す。P0 / P1 findingは原則としてIssue化し、P2 / P3は監査結果への集約を既定とする。

Security、privacy、secret、credential、exploitに関するfindingは、公開前に機密分類とtracking境界を確認する。`SENSITIVE`なfindingは公開Issueへ自動投稿しない。

監査の既定レベルは`STANDARD`とし、Audit SHAには対象Repositoryの完全なcommit SHAを使う。dirty worktreeの観察はSHAと分けて記録する。

Repository Control itemとfinding Issueはcanonical keyで既存項目を再利用し、同じ状態を持つIssue/PRを並行作成しない。

## Modification Boundary

個別案件の作業では `README.md` / `project/**` を変更対象とする。Base / Runtimeそのものを変更するタスクでない限り共通層を触らない。

## Implementation

- Domain CoreにSurface固有I/Oを埋め込まない。
- UI状態をDomain正本にしない。
- 同じ変換・判定・定数を複数Surfaceへ複製しない。
- 生成物を手編集しない。
- fallbackは元データを破壊しない方向を優先する。
- destructive operationには復元可能性・確認・dry-runのいずれかを検討する。

## Verification

完了宣言の前に、利用可能なら `knt verify` を実行する。外部接続やUIを変更した場合は対応するsmoke/実利用経路も確認する。
