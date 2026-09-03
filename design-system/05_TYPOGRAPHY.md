# 05. TYPOGRAPHY

## 現状の問題

`build_site.py`のCSS内だけでfont-sizeが概ね20段階(0.62rem〜1.9rem)存在し、
どの値がどの意味段階に対応するか一貫していない。

## MOTの型スケール(7段階)

既存のフォント指定(Zen Kaku Gothic New / Zen Old Mincho)は変更しない。
サイズだけを以下の7段階に統合する。

| トークン | サイズ | 用途 |
|---|---|---|
| `--mot-text-caption` | 12px (0.75rem) | メタ情報、日時、出典ラベル |
| `--mot-text-small` | 13px (0.8125rem) | タグ、バッジ内テキスト |
| `--mot-text-body` | 15px (0.9375rem) | 要約文、本文 |
| `--mot-text-body-lg` | 17px (1.0625rem) | 記事本文の主要段落 |
| `--mot-text-heading-sm` | 20px (1.25rem) | カード見出し(minor) |
| `--mot-text-heading` | 26px (1.625rem) | セクション見出し、記事h1(モバイル) |
| `--mot-text-heading-lg` | 34px (2.125rem) | HERO見出し、記事h1(デスクトップ) |

## 原則

- **既存の日本語フォントペアリングは維持する**(Zen Old Mincho = 見出し・
  権威性、Zen Kaku Gothic New = 本文・可読性)。これはyutonamishaの模倣ではなく
  MOTがすでに持っていた資産。
- 新しいサイズを追加したくなったら、まずこの7段階のどれかで代用できないか検討する。
- `letter-spacing`は「メタ情報・ラベル」(caption/small)にのみ0.04〜0.08em程度
  与え、本文には付けない(現状すでにこの傾向はあるので踏襲)。
- MOT ANALYSIS本文は`--mot-text-body-lg`を使い、他の付随情報より明確に
  読みやすいサイズにする(現在は本文もmetaも大差ないサイズ感になっている)。
