# ラベルジェネレータ（Label Generator / lblgen）

**枠で囲んだ数字・文字のラベル画像を一括作成**するツールです。数字の連番・文字リスト・CSV から、円・角丸・多角形・登録した形などの枠付きラベルをまとめて作り、印刷向けの高解像度 PNG のほか、文字を編集できる SVG・PowerPoint でも保存できます。Windows アプリ版と Web 版があります（1.3.0 までの名前は「数字画像メーカー」）。

## Web 版

インストールせずにブラウザで使える Web 版があります：**https://onsoos.github.io/lblgen/**

処理はすべてブラウザの中で行い、画像やファイルはどこにも送信しません。PNG / JPEG / WEBP / SVG / PowerPoint で保存できます（ソース：[`docs/index.html`](docs/index.html)）。

## ダウンロード（Windows アプリ）

[Releases](https://github.com/ONSOOS/lblgen/releases/latest) から入手してください。

| ファイル | 内容 |
|---|---|
| `SujiMaker-<版>-setup.exe` | インストーラ（おすすめ）。管理者権限なしで入り、スタートメニューに登録されます |
| `SujiMaker-<版>.exe` | インストールせずに使える単体の exe |

初めて起動したときに「Windows によって PC が保護されました」と出た場合は、「詳細情報」→「実行」で起動できます。

## できること

- **内容**：数字の範囲（0で埋める 07・右寄せ＝ゼロサプレス・中央寄せ、前後に文字を付ける）、または A〜Z・あ〜ん などの文字リスト。リストは CSV（UTF-8 / Shift_JIS）から読み込める
- **文字**：PC に入っているフォントから選択。文字の高さ・最大幅・太さ・位置を調整。日本語を含む文字は自動で日本語フォントに
- **枠**：なし（文字だけ）・円・楕円・正方形・長方形・角丸正方形・角丸長方形・六角形・八角形・ひし形・三角形・任意の形状。枠線の有無、線の太さ、余白
- **形の登録**：好きな形の画像を名前を付けて登録（見本：星・ハート・吹き出し・盾・五角形・ホームベース）
- **色**：文字・枠線・内側・外側の色。内側・外側はそれぞれ透過にできる
- **出力**：幅・高さ・解像度（dpi）、PNG / JPEG / TIFF / BMP / WEBP / PDF、保存先、ファイル名の付け方
- **ベクター出力**：SVG（文字はテキストのまま、またはアウトライン化）、PowerPoint（.pptx。枠は図形・文字はテキストで、Word / Excel に貼っても編集できる）
- **オンラインアップデート**：新しいリリースを確認し、チェックサムを確かめてから更新

使い方はアプリの「ヘルプ ＞ 使い方」（F1）を見てください。

## ソースから動かす

Python 3.12 以降と Pillow が必要です。PowerPoint 出力には python-pptx、SVG のアウトライン化には fontTools も使います。

```
pip install pillow python-pptx fonttools
python 数字画像メーカー.pyw
```

| ファイル | 役割 |
|---|---|
| `数字画像メーカー.pyw` | 画面（tkinter） |
| `suji_core.py` | 画像の描画エンジン（スクリプトからも使えます） |
| `shape_lib.py` | 登録した形の管理 |
| `vector_out.py` | SVG・PowerPoint の書き出し |
| `updater.py` | GitHub Releases を使った更新 |
| `app_info.py` | アプリ名・バージョン・クレジット・更新の確認先 |
| `help_text.py` | ヘルプの文章 |
| `docs/index.html` | Web 版（1 ファイル。GitHub Pages で公開） |
| `build.py` / `installer.iss` | 配布用ファイルの作成（PyInstaller / Inno Setup 6） |

## リリースの作り方

1. `app_info.py` の `VERSION` を上げる
2. `python build.py` を実行（`release\<版>\` に setup.exe・単体 exe・`SHA256SUMS.txt` ができる）
3. タグ `v<版>` でリリースを作り、3 つのファイルをすべて添付する（`SHA256SUMS.txt` が無いとアプリは更新しません）

## クレジット

企画・開発：Akira Sudo
発行：OnsooSystem Corp.
© 2026 OnsooSystem Corp. All rights reserved.

使用ソフトウェア：Python / Pillow / python-pptx / fontTools / PyInstaller / Inno Setup（Windows 版）、JSZip / PptxGenJS（Web 版）
