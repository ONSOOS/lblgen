"""アプリの名前・バージョン・クレジット・更新の確認先（リリースのたびに VERSION を上げる）"""
APP_NAME = "ラベルジェネレータ"
APP_NAME_EN = "Label Generator"
APP_TAGLINE = "枠で囲んだ数字・文字のラベル画像を一括作成"
APP_FEATURES = ("数字の連番・文字リスト・CSV から、円・角丸・多角形・登録した形などの枠付きラベルを"
                "まとめて作成。PNG・JPEG・TIFF・BMP・WEBP・PDF のほか、文字を編集できる SVG・PowerPoint で保存できます。")
# ファイル名・設定フォルダ・更新ファイル名に使う英字名（変えると更新や設定の引き継ぎができなくなるので変えない）
APP_ID = "SujiMaker"
OLD_NAMES = ["数字画像メーカー"]   # 以前の名前（インストーラで古いショートカットを消す）
VERSION = "1.4.0"
AUTHOR = "Akira Sudo"
COMPANY = "OnsooSystem Corp."
COPYRIGHT = "© 2026 OnsooSystem Corp."

# 更新の確認先：GitHub の「所有者/リポジトリ名」（公開リポジトリ）
GITHUB_REPO = "ONSOOS/lblgen"
WEB_URL = "https://onsoos.github.io/lblgen/"
