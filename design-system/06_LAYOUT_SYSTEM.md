# 06. LAYOUT SYSTEM

## 現状の問題

HOME・記事一覧・記事詳細・about・products・contactのすべてが `max-width: 720px`
の単一センター列。HEROもLATEST NEWSのカードも「箱の大きさが違うだけ」で構造は
同じ。これが「均一なカードグリッド」に見える最大の原因。

## MOTのレイアウト原則

「離散的で対等な実体」(`reference-analysis/UNIVERSAL_PRINCIPLES.md` 原則1)
にあたるのは、通常のニュース記事一覧そのものであり、カード形式自体は否定しない。
問題は**重要度を持つ実体を、対等な実体と同じ形式で扱っていること**。

### 3段階のレイアウト構造

1. **HERO(1本のみ)**
   - 幅いっぱい、画像は大きく、見出しは`--mot-text-heading-lg`
   - 他のどの記事とも形が異なる(カードの拡大版ではない)
   - 1画面に必ず1本だけ。複数のHERO級記事を並べない。

2. **MAJOR ROW(重要記事、`_entry_importance == "major"`)**
   - 横長のカード、画像とテキストが左右または上下で明確に分かれる
   - 見出しは`--mot-text-heading-sm`

3. **MINOR LIST(通常記事)**
   - 画像を小さくするか省略し、**テキスト密度の高いリスト行**にする
   - 現状のような「画像+角丸+影」の縮小コピーにしない
   - 一覧性・スキャンのしやすさを優先する

### 記事詳細ページ

- 本文列は現状の720px程度を維持してよい(可読行長として妥当)
- ただし「MOT ANALYSIS(本文)」「FACT(出典)」「mot_take」は同じ箱の意匠で
  並べず、読者の理解段階が視覚的に進んでいくように余白と罫線で区切る
  (`13_COMPONENT_RULES.md`のMOT Analysis Blockを参照)

## 非対称性について

yutonamisha分析(`DESIGN_DECISION_TREE.md`)が示す通り、非対称は
「実体の重要度が違うから形が違う」時にのみ生まれる。MOTでは重要度の差は
既にデータとして存在する(`importance_score`, `_entry_importance`)ため、
それをレイアウトの違いとして初めて可視化する。
