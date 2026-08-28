# CLAUDE.md (ai_news_site / MOT)

このファイルは親フォルダの`CLAUDE.md`のルール（破壊的操作の許可制、個人情報・秘密情報の扱い等）を
継承したうえで、本プロジェクト（AI特化メディアMOT）固有のAIO(AI Overviews)/GEO(Generative Engine
Optimization)最適化の開発原則を追加するものです。親のルールを緩めるものではありません。

## AIO/GEO最適化の開発原則

生成AI検索(Google AI Overviews、ChatGPT検索、Perplexity等)に正しく引用・要約されることを
狙い、以下を維持・徹底する。

1. **構造化データ(JSON-LD)を全記事に必須で付与する**
   - `NewsArticle`(headline / description / datePublished / dateModified / author / publisher /
     mainEntityOfPage / citation)を`<head>`に埋め込む(`_render_structured_data`)
   - FAQがある記事は`FAQPage`も併記する
   - `</script>`混入対策として、JSON文字列側をエスケープしてから`<script>`タグで包む

2. **セマンティックHTMLで出典を明示する**
   - 出典表記は`<blockquote cite="元記事URL">`と`<cite>`タグを用いる(`_write_article_page`内)
   - 本文はAIによる要約・言い換えであり元記事の逐語引用ではないため、
     「引用」ではなく「出典表示」として正確に構成する(誤った直接引用の印象を与えない)

3. **1次情報への導線を明示する**
   - 記事ページのSOURCE/FACT表記には必ず元記事へのリンクを含める
   - 元記事URLは`_safe_http_url()`でhttp/https以外のスキームを弾いてから使う

4. **PR・アフィリエイトリンクには`rel="sponsored nofollow"`を付与する**
   - A8.net等の広告リンクは検索エンジンに「広告である」ことを明示する
   - 出典リンク(元記事へのリンク)は広告ではないため対象外(`rel="noopener noreferrer"`のまま)

5. **`llms.txt`をビルド時に自動生成・更新する**
   - `docs/llms.txt`(サイト公開ルート直下)に記事の URL・タイトル・概要・更新日を一覧化する
   - `_write_llms_txt()`が`build()`実行のたびに最新化する。手動更新は不要

6. **新規記事の本文構造: TL;DR + 3見出し(h3)**
   - 冒頭に結論(TL;DR)、続けて「何が起きたか」「なぜ重要か」「今後の影響」の3つのh3見出し
   - `generator.py`のプロンプトでこの4項目(`tldr`/`what_happened`/`why_it_matters`/
     `future_impact`)を生成し、`_render_article_body()`がHTML化する
   - **既存の過去記事は書き換えない**(旧`body`フィールドのまま表示され続ける。この方針は
     スラッグ形式変更・難易度分類など、本プロジェクトの他のテンプレート変更でも一貫している)

## 変更時の注意

- 上記の原則を変更する場合も、親CLAUDE.mdの「大規模なコード変更」の確認ルールに従うこと
- 事実を捏造しない(架空のPV数・偽の引用文・元記事に無い数字等)という本プロジェクトの
  大原則は、AIO最適化のためであっても絶対に破らない
