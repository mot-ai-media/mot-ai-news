# 13. COMPONENT RULES

各コンポーネントは Purpose / Structure / Visual hierarchy / Spacing / Typography /
Responsive / Interaction / When to use / When NOT to use の順で定義する。

---

## Header / Navigation

- **Purpose**: MOTのトップへの帰属と、TODAY/LATEST/TOPICS/PRODUCTS/CONTACTへの導線。
- **Structure**: ロゴ(左)+リンク群(中央〜右)+検索/テーマ切替/ハンバーガー(右端)。既存構造を維持。
- **Visual hierarchy**: ロゴ>リンク>アイコン群。リンクに強い色を付けない(常時表示物に意味色を使わない)。
- **Spacing**: `--mot-space-normal`で統一。
- **Typography**: `--mot-text-small`。
- **Responsive**: モバイルはハンバーガーに畳む(既存実装を維持)。
- **Interaction**: ホバーで色変化のみ、拡大・下線アニメーションは付けない。
- **When to use**: 全ページ共通。
- **When NOT to use**: LP的な単発ページ(MOT NAGANOなど独立ブランドページ)では
  MOT本体ナビをそのまま流用しない(`docs/nagano/`は独自ナビを持つ、が正しい判断)。

## Hero(今日いちばん重要な1本)

- **Purpose**: 「今日はこれを読め」という編集の意思表示。
- **Structure**: フルブリード画像+`--mot-text-heading-lg`見出し+要約1〜2行。カードの拡大版にしない。
- **Visual hierarchy**: ページ内で最大。他のどの要素より明確に大きい。
- **Spacing**: 前後に`--mot-space-dramatic`。
- **Typography**: `--mot-text-heading-lg`。
- **Responsive**: モバイルでも画像を大きく保ち、テキストを小さくして対応(画像を削らない)。
- **Interaction**: なし(静的)。
- **When to use**: 1画面に必ず1つだけ。
- **When NOT to use**: major記事が複数ある日でも、HEROを複数並べない(1本に絞る編集判断をコードでも強制する)。

## Major Card(重要記事)

- **Purpose**: HEROに次ぐ重要度を、通常記事と区別して示す。
- **Structure**: 横長、画像とテキストが左右分割。
- **Visual hierarchy**: `--mot-text-heading-sm`、`--mot-shadow-major`を唯一許可。
- **Spacing**: `--mot-space-normal`。
- **Typography**: 見出し`--mot-text-heading-sm` / 要約`--mot-text-body`。
- **Responsive**: モバイルは上下分割に切り替え。
- **Interaction**: ホバーで見出し色変化のみ。
- **When to use**: `_entry_importance == "major"`。
- **When NOT to use**: 通常記事には使わない(格上げしない)。

## Minor List Row(通常記事)

- **Purpose**: 一覧性の確保。読者が素早くスキャンできること。
- **Structure**: 画像は小さいサムネイル or 省略、テキスト密度を優先した1行〜2行のリスト行。
- **Visual hierarchy**: `--mot-text-body`基準、影なし、角丸`--mot-radius-sm`程度。
- **Spacing**: `--mot-space-tight`〜`--mot-space-normal`。
- **Typography**: `--mot-text-body` / メタは`--mot-text-caption`。
- **Responsive**: モバイルでもリスト行のまま(カード化しない)。
- **Interaction**: ホバーで背景がわずかに変わる程度。
- **When to use**: 通常記事全般。既存の`.card`を置き換える主要コンポーネント。
- **When NOT to use**: major/HERO級には使わない。

## MOT Analysis Block(記事詳細・本文)

- **Purpose**: MOTの編集による要約・解説であることを明示する、MOT最大の差別化要素。
- **Structure**: `MOT ANALYSIS`ラベル+本文。既存のTL;DR+3見出し構造(AIO/GEO CLAUDE.md準拠)を維持。
- **Visual hierarchy**: 本文は`--mot-text-body-lg`で、周辺情報より明確に大きく読みやすくする。
- **Spacing**: 前後`--mot-space-loose`。
- **Typography**: ラベルは`--mot-text-caption`+letter-spacing、本文は`--mot-text-body-lg`。
- **Responsive**: 変更なし(既に単一列)。
- **Interaction**: なし。
- **When to use**: 全記事詳細ページ。
- **When NOT to use**: 一覧ページには出さない(要約で十分)。

## Fact Block(出典・引用)

- **Purpose**: 一次情報への誠実な導線(親CLAUDE.md/AIO原則)。
- **Structure**: `<blockquote cite>` + `<cite>` + 元記事リンク。既存構造を維持。
- **Visual hierarchy**: MOT Analysis Blockより控えめだが、隠さない・埋もれさせない。
- **Spacing**: `--mot-space-normal`。
- **Typography**: `--mot-text-body`。
- **Responsive**: 変更なし。
- **Interaction**: リンクホバーのみ。
- **When to use**: 全記事詳細ページ、必ずMOT Analysis Blockの後。
- **When NOT to use**: 一覧ページのカードには出さない。

## Metadata / Trust Strip

- **Purpose**: 難易度・出典・更新日という「誠実さ」を本文より前に見せる。
- **Structure**: 既存の`trust-strip`構造を維持。
- **Visual hierarchy**: `--mot-text-caption`、目立たせすぎない(装飾ではなく事実の提示)。
- **Spacing**: `--mot-space-tight`。
- **Typography**: `--mot-text-caption`。
- **Responsive**: 折り返し可。
- **Interaction**: なし。
- **When to use**: 全記事(一覧・詳細とも本文より前)。
- **When NOT to use**: HEROの見出しより上に出さない(見出しの視覚的優先度を守る)。

## Image / Thumbnail

`09_IMAGE_DIRECTION.md`を参照。実画像=証拠として`--mot-radius-md`で表示、
実画像なし=タイポグラフィックプレースホルダー(装飾グラデーション禁止)。

## Category / Topic Pill

- **Purpose**: テーマ別ハブへの導線。
- **Structure**: テキスト+`--mot-radius-sm`(丸ピルにしない)。
- **Visual hierarchy**: 本文より弱く、リンクとわかる程度。
- **Spacing**: `--mot-space-tight`。
- **Typography**: `--mot-text-small`。
- **Responsive**: 折り返し可。
- **Interaction**: ホバーで下線。
- **When to use**: 記事タグ、トピック一覧。
- **When NOT to use**: 1記事に大量のタグを羅列しない(3〜4個程度に絞る、既存の`MAX_RELATED_ARTICLES`的な上限思想を踏襲)。

## Search / Level Filter

- **Purpose**: 読者が情報の粒度を選べるようにする(MOTの価値観そのもの)。
- **Structure**: 既存の`level-filter-btn`構造を維持。
- **Visual hierarchy**: 選択中のみ`--mot-radius-full`+濃い背景。非選択はボーダーのみ。
- **Spacing**: `--mot-space-tight`。
- **Typography**: `--mot-text-small`。
- **Responsive**: 横スクロール可。
- **Interaction**: クリックで即時反映。
- **When to use**: LATEST NEWSセクション上部。
- **When NOT to use**: HERO・記事詳細には不要。

## Footer

- **Purpose**: サイト全体の補助導線(RSS/about/products/contact)。
- **Structure**: 既存構造を維持、装飾を追加しない。
- **Typography**: `--mot-text-caption`。
- **When NOT to use**: フッターに新しい強調色・バッジを追加しない。
