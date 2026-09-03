# 03. INFORMATION ARCHITECTURE

## 現状のIA(実装から確認)

トップナビ: TODAY / LATEST / TOPICS / PRODUCTS / CONTACT
記事一覧: HERO(1本) → 今日のブリーフィング → テーマ探索 → 難易度フィルタ付き
LATEST NEWS一覧(無限スクロール)
記事詳細: サムネイル → 見出し → trust-strip(難易度/出典/更新日) →
MOT ANALYSIS(本文) → タグ → 広告 → FACT(出典引用) → FAQ → シェア → リアクション

## 維持すべき点

- 「今日」と「すべて」を分けている構造(TODAY / LATEST)は良い判断。捨てない。
- trust-strip(出典・更新日・難易度を本文より前に置く)は誠実さの表現として正しい。
  レイアウトを変えてもこの情報の**掲載順序**は変えない。
- 難易度フィルタ(やさしい/テクニカル)は読者を尊重する設計として維持する。

## 変更すべき点

- 一覧のHEROとLATEST NEWSのカードが**視覚的に地続き**(同じカード意匠の拡大版)
  になっている。HEROは構造からして別カテゴリの表示物であるべき
  (`06_LAYOUT_SYSTEM.md`で定義)。
- 記事の重要度(`_entry_importance` major/minor)がコード上は既に存在するのに、
  LATEST NEWS内では`.card-minor`の透明度80%程度の違いしかない。
  重要度による**レイアウトの違い**(サイズ・情報量)を作る。
- MOT ANALYSIS(本文)・FACT(出典)・mot_take・risk/opportunityという
  MOT独自の4種のブロックが、視覚的に並列のカードとして扱われている。
  これらは**読者の理解プロセスの段階**(要約→詳細→MOTの見解→検証)を表す
  ものなので、段階が伝わる並び・視覚差を与える。
