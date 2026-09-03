# 04. VISUAL LANGUAGE(概要)

詳細は各ファイルに分割している。ここでは全体方針だけをまとめる。

| 領域 | 方針 | 詳細 |
|---|---|---|
| Typography | 場当たり的な約20段階のfont-sizeを、意味を持った7段階に統合 | `05_TYPOGRAPHY.md` |
| Layout | 均一カードグリッドをやめ、重要度で構造そのものを変える | `06_LAYOUT_SYSTEM.md` |
| Spacing | 数値の羅列ではなく4段階の呼吸のリズムとして定義 | `07_SPACING_SYSTEM.md` |
| Color | 既存のVon Restorff思想(コード内コメント)は維持し、運用ルールを厳格化 | `08_COLOR_SYSTEM.md` |
| Image | 装飾グラデーションを廃止し、証拠(実画像)かタイポグラフィ処理かの二択にする | `09_IMAGE_DIRECTION.md` |
| Graphic | 角丸・バッジ・アイコンの語彙を絞る | `10_GRAPHIC_LANGUAGE.md` |
| Motion | 意味の切り替わりにのみ使う | `11_MOTION_PRINCIPLES.md` |

## 一貫性の核

MOTのVisual Languageの核は「**情報の重要度と視覚的な重さを一致させる**」こと。
色数・角丸・影を増やして装飾するのではなく、**サイズ・位置・余白**で重要度を語る。
これが「量産テンプレート感」から最も遠ざかる方向性であり、既存コードの
`--mot-*`変数コメント(Von Restorff効果)が最初から目指していた方向と一致する。
実装が追いついていなかっただけ、というのが監査の結論。
