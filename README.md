# MViser

MV素材生成・音楽同期可視化ツール MViser。

コード進行・歌詞・固定BPMを記述した `.mvproj.yaml` から、コード変化に同期した背景色・コード名・歌詞表示を描画し、音声付きMP4またはPNG連番（AviUtl / After Effects取込用）として書き出します。現在はMVP-0（MViser#2）段階です。

## Quick start

```powershell
.\knt.cmd setup                      # pip install -r project/requirements.txt
python project/tools/make_click_wav.py project/samples/click.wav 135 16
python project/tools/run_mviser.py render project/samples/sample.mvproj.yaml -o project/output/sample.mp4
python project/tools/run_mviser.py render project/samples/sample.mvproj.yaml --frames project/output/frames --start 4 --end 8
python project/tools/run_mviser.py frame  project/samples/sample.mvproj.yaml --time 4.0 -o project/output/f.png
python project/tools/run_mviser.py inspect project/samples/sample.mvproj.yaml
# MIDI: add `imports: [{format: midi, path: song.mid}]` to a project (see project/docs/SPEC.md)
```

## Documents

- Agent entry: [AGENTS.md](AGENTS.md) (KiNoTch. Repository Base)
- [Specification](project/docs/SPEC.md) / [Current State](project/docs/CURRENT_STATE.md) / [Decisions](project/docs/adr/README.md)
