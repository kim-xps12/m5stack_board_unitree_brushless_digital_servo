# AGENTS.md

M5Stack と Unitree J288 / S288 サーボをつなぐ基板の KiCad 9 プロジェクトです。JLCPCB の部品実装 (PCBA) にそのまま発注できる状態を保ちます。

## 参照先

| ファイル | 読むとき |
| --- | --- |
| `docs/design.md` | 部品、ピン配置、配置、銅箔、回路図、製造ルールを変える前。決めたことと理由、レビューでの指摘と対応 |
| `README.md` | 仕様、ピン配置、BOM (利用者向け) |
| `work/README.md` | 作業ファイル (git 管理外。ない環境もある) |
| `digital_servo/atoms3r/docs/ttl_board_redesign.md` (作者の別リポジトリ) | 送信の自動切り替えの定数 (R1、C6、D1、U1) やタイミングを変えるとき |

## コマンド

```bash
tools/check_all.sh                # 変更のたびに実行し、最後が "== ALL OK" であることを確かめる
tools/render_images.sh            # スクショ 9 枚と README 用の画像を production/images/ に作る
tools/render_images.sh --readme   # 中身が変わった README の画像を docs/ に上書きする
```

- `check_all.sh` は次を順に実行する。
  - DRC (回路図との整合を含む)、ERC
  - ベタの塗り直し漏れ、ビアによるベタの出っ張り、取り付け穴まわりの銅
  - JLCPCB の発注ファイルの出力 (`tools/jlcpcb_export.py`)
  - CPL の照合 (`work/jlc/` があるときだけ)
- 結果は `production/checks/` に残る。
- KiCad の場所は `KICAD_CLI` と `KICAD_PYTHON` で変えられる (既定は macOS の KiCad 9 のアプリ)。

## 編集のルール

- **正本**: リポジトリ直下の KiCad ファイルが正本。KiCad のアプリか、KiCad 同梱の Python (pcbnew) で直接編集する。
  - `work/kicad/` の生成スクリプトは再実行しない。部品の UUID が変わり、直接加えた変更も消える。
- **書き換える前**: `~*.lck` があれば、ユーザが KiCad で開いている。ファイルを書き換える前にユーザに伝える。
- **pcbnew で保存するとき**:
  - 保存の前にゾーンを塗り直す (`pcbnew.ZONE_FILLER(board).Fill(board.Zones())`)。ガーバーは保存済みの塗りをそのまま出力する。
  - 保存で `.kicad_pro` が書き直されたら、意図しない差分を戻す。
- **作業用のスクリプトと中間ファイル**: `work/` に置く。
- **部品を足すとき**: フットプリントは `Library.pretty` にコピーしてシルクの線幅を 0.15 mm にしたものを使う。`LCSC` フィールドに品番を入れる。
- **品番やフットプリントを変えたら**: `tools/jlcpcb_export.py` の `CORRECTION` を求め直す (`docs/design.md` §5)。
- **DRC と ERC**: 警告も含めて 0 件を保つ。
- **`check_all.sh` では見つけられない制約**: 守るか、変えるならユーザに確認する。
  - 部品本体 (F.Fab) を基板端から 2.5 mm 以上離す。
  - ベタや配線に 90° の入り隅や矩形の切り欠きを作らず、45° で面取りする。
  - 外形、取り付け穴、J1〜J7 のピン番号は変えない。JP1 (BAT–+5V のジャンパ) は戻さない。
  - 回路図は左から右へ信号の流れで描き、線をラベルで飛ばさない (`docs/design.md` §6)。

## やりとり

- 回答と報告は日本語で書く。用語は説明してから使い、平易に書く。
- 仕様、部品、配置、外観の判断は推測で決めない。選択肢と推奨を添えて、1 件ずつユーザに質問する。
- 変更したら、変更前と変更後の画像を自分で見て確かめてから、ユーザに示す。
- README は日本語の段落と英語の段落の 2 言語で書く。日本語の句読点は「，」「．」。
- 回路の出自 (「OpenRB-150 風」など) は、README、回路図、シルクに書かない。

## Git

- ブランチは `main` だけで、remote はない。push の前に、remote (リポジトリ名と公開範囲) をユーザに確認する。
- コミットはユーザに頼まれたときだけ作る。1 コミット = 1 つの論理的な変更。
- コミットメッセージは英語で書く。件名は命令形、本文に理由を書く。
- DYNAMIXEL 版から残っている `docs/` の画像と `example_m5core2_dynamixel_arduino_ide/` は扱いが決まっていない。消したりコミットしたりしない。
