# MViser

MV素材生成・音楽同期可視化ツール。

`.mvproj.yaml`（またはMIDI / μChordbot `.mcb`）のコード進行・歌詞・BPMから、コード変化に同期した背景・コード表示・歌詞（ルビ／縦書き／複数字幕セット）を描画し、
**背景＋字幕層**を MP4 / PNG連番 / 透過動画（ProRes 4444・WebM）として書き出します。イラスト・カメラワーク・最終合成は After Effects / AviUtl 側で行う前提で、
`.exo` / `.jsx` による受け渡しも生成します。GUI（tkinter）でプレビュー・音声同期再生・字幕編集・設定ができます。

## Quick start (Windows)

```powershell
.\knt.cmd setup                                   # pip install -r project/requirements.txt
python project/tools/manual_check.py --prepare    # sample click.wav / sample.mid
python project/tools/run_mviser.py gui project/samples/sample.mvproj.yaml
```

## CLI

```powershell
python project/tools/run_mviser.py inspect project/samples/sample.mvproj.yaml
python project/tools/run_mviser.py frame   project/samples/sample.mvproj.yaml --time 4.0 -o project/output/f.png
python project/tools/run_mviser.py render  project/samples/sample.mvproj.yaml -o project/output/sample.mp4
python project/tools/run_mviser.py render  project/samples/sample.mvproj.yaml --frames project/output/frames --start 4 --end 8
python project/tools/run_mviser.py render  project/samples/sample.mvproj.yaml --layers chords,lyrics --format prores4444 -o project/output/text.mov
python project/tools/run_mviser.py handoff project/samples/sample.mvproj.yaml -o project/output/handoff   # AviUtl .exo + AE .jsx
python project/tools/run_mviser.py audit --out project/output/audit   # automated PASS/WARN/FAIL audit + JSON report (MViser#38)
```

Options: `--subtitle-set NAME`, `--all-subtitle-sets`, `--split-layers`, `--no-audio`. Input formats, schema and GUI keys: [SPEC](project/docs/SPEC.md).

## Documents

- Agent entry: [AGENTS.md](AGENTS.md) (KiNoTch. Repository Base 0.5.9)
- [Specification](project/docs/SPEC.md) / [Current State](project/docs/CURRENT_STATE.md) / [Decisions](project/docs/adr/README.md) / [Index](project/docs/INDEX.md)
- Manual verification on real hardware: MViser#14 (source: `project/verification/manual_checks.yaml`)
