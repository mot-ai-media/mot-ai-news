# 12. DESIGN TOKENS

実装時は `build_site.py` の `STYLE_CSS` 内 `:root` にこのままCSS変数として追加する。
既存の `--mot-breaking/trending/popular/positive/primary/border/text-secondary` は
名前を変えずに維持し、下記を追加する形にする(破壊的変更を避ける)。

```css
:root {
  /* --- 既存(維持) --- */
  --mot-breaking: #EF4444;
  --mot-trending: #F97316;
  --mot-popular: #F59E0B;
  --mot-positive: #10B981;
  --mot-primary: #2563EB;
  --mot-border: #E2E8F0;
  --mot-text-secondary: #64748B;

  /* --- Typography scale (05) --- */
  --mot-text-caption: 0.75rem;
  --mot-text-small: 0.8125rem;
  --mot-text-body: 0.9375rem;
  --mot-text-body-lg: 1.0625rem;
  --mot-text-heading-sm: 1.25rem;
  --mot-text-heading: 1.625rem;
  --mot-text-heading-lg: 2.125rem;

  /* --- Spacing scale (07) --- */
  --mot-space-tight: 8px;
  --mot-space-normal: 16px;
  --mot-space-loose: 32px;
  --mot-space-dramatic: 64px;

  /* --- Radius scale (10) --- */
  --mot-radius-sm: 4px;
  --mot-radius-md: 10px;
  --mot-radius-full: 999px;

  /* --- Shadow: 1段階のみ(majorカードにだけ使う) --- */
  --mot-shadow-major: 0 2px 10px rgba(0,0,0,0.07);

  /* --- Container --- */
  --mot-container: 720px;

  /* --- Motion --- */
  --mot-motion-fast: 150ms ease;
  --mot-motion-normal: 220ms ease;
}
```

## 揺らぎについて

すべての値を上記トークンだけに統一する必要はない。たとえば記事本文中の
`<h3>`と`<h4>`のような**細かな入れ子の相対差**は`em`で調整してよい。
トークン化するのは「他のコンポーネントと合わせるべき、繰り返し使う値」だけ。
