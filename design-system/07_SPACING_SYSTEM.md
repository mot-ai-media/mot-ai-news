# 07. SPACING SYSTEM

## 原則

spacingを「数値」ではなく「呼吸の深さ」として4段階だけ定義する。
段階を増やしすぎない(増やした瞬間、また場当たり的な値が紛れ込む)。

| トークン | 値 | 用途 |
|---|---|---|
| `--mot-space-tight` | 8px | バッジ内、アイコンとテキストの間 |
| `--mot-space-normal` | 16px | カード内の要素間、本文の段落間 |
| `--mot-space-loose` | 32px | セクション内の要素グループ間 |
| `--mot-space-dramatic` | 64px | セクションとセクションの間、HEROの前後 |

## 運用ルール

- HEROの前後だけは`--mot-space-dramatic`を必ず使い、「今日の主役」の前後に
  意図的な間を作る。他のセクションでこの値を乱用しない(乱用すると
  "dramatic"が普通になり効果を失う)。
- カードのpaddingは`--mot-space-normal`で統一し、カードごとに微妙に違う
  paddingを作らない(現状のCSSは要素ごとにpaddingがバラバラ)。
