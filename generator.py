"""Claude APIでAIニュース記事のキャッチーな見出し・要約を生成する。"""

from __future__ import annotations

import json

import anthropic

from sources import Article

MODEL = "claude-haiku-4-5-20251001"

PROMPT_TEMPLATE = """あなたはAI分野のニュースキュレーションサイトの編集者です。
以下の元記事をもとに、日本語で「見出し」「要約」「本文」を作成してください。

# 元記事
タイトル: {title}
概要: {summary}
出典: {source}

# 見出しのトーン
ネットニュースのバズるタイトルのように、強く・断定的な言い回しにする。
- 体言止め、断定形（「〜する」「〜が判明」「〜の衝撃」等）を積極的に使う
- 具体的な数字・固有名詞（企業名・製品名）を前面に出す
- 「まさかの」「ついに」「衝撃」等の強い言葉は使ってよいが、乱用して安っぽくしない
- 弱い例: 「AIエージェントの活用進む」→ 強い例: 「AIエージェント、ついに全社導入で業務激変」

# 各項目の役割
- headline: 一覧ページ・記事内の見出し(H1)に出す、バズるトーンの見出し。30字前後
- seo_title: 検索結果のタイトルとして使う、SEO向けタイトル。32字前後。
  検索する人が実際に入力しそうな言葉(「とは」「使い方」「料金」「いつから」「比較」等)を自然に含める。
  誇張・釣りタイトルにはせず、記事内容を正確に反映すること。
  例: 「ChatGPT新機能◯◯とは？何ができる・使い方を解説」
- summary: 一覧ページのカードに出す短い一言コメント。1文、40字前後
- body: 記事詳細ページの本文。2〜3段落(合計8〜12文程度)で、読み応えのある内容にする。
  以下の要素を含めて厚みを持たせる:
  1) 何が起きたか(元記事の事実を、元記事とは異なる言葉遣い・構成で説明する。文の並び順や言い回しを元記事のまま踏襲しない)
  2) なぜ注目すべきか・背景にある業界動向や技術的な文脈の一般的な解説
  3) 読者にとっての意味合い(実務やビジネスにどう関わってくるかなど)
  ただし背景・解説部分はAIニュース分野の一般的な知識の範囲にとどめ、元記事に書かれていない具体的な事実(数字・日付・固有名詞・発言・出来事)を新たに作ってはいけない。
  また、元記事の文章をそのまま(一字一句、あるいはほぼそのまま)転載してはいけない。必ず自分の言葉で書き直すこと。
- tags: 記事に関連する企業名・製品名・技術名を2〜4個。例: ["OpenAI", "ChatGPT"]。関連記事表示に使う。
- faq: 検索されそうな疑問とその答えを2〜3個。「とは」「料金」「使い方」「いつから」「何が変わる」等の中から、
  この記事のテーマに合うものを選ぶ。答えは元記事に書かれている範囲の情報のみで簡潔に(1〜2文)。
  元記事に情報が無い項目(料金や提供時期が書かれていない等)は無理に作らず、その項目自体を含めない。

# 制約
- **元記事に書かれていない事実は絶対に作らない**。強くするのは言い回し・トーンだけで、事実関係(誰が・何を・いつ)は元記事の範囲を超えないこと
- faqの答えも同様に、元記事に無い具体的事実(数字・日付・料金等)を作らない。分からない項目はfaqに含めない
- bodyの段落と段落の間は"\\n\\n"(改行2つ)で区切ること
- 出力は次のJSON形式のみ。説明や前置き、コードブロック記号は一切つけない
{{"headline": "ここに見出し", "seo_title": "ここにSEOタイトル", "summary": "ここに要約", "body": "1段落目\\n\\n2段落目\\n\\n3段落目", "tags": ["タグ1", "タグ2"], "faq": [{{"q": "質問", "a": "回答"}}]}}
"""


class GenerationError(Exception):
    """生成結果が期待したJSON形式でなかった場合に送出する。"""


def generate_headline_and_summary(article: Article, client: anthropic.Anthropic | None = None) -> dict:
    client = client or anthropic.Anthropic()
    prompt = PROMPT_TEMPLATE.format(
        title=article.title,
        summary=article.summary or "(概要なし)",
        source=article.source,
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError(f"JSON解析に失敗しました: {text!r}") from exc

    if not all(k in data for k in ("headline", "summary", "body")):
        raise GenerationError(f"必要なキーが含まれていません: {data!r}")

    data.setdefault("seo_title", data["headline"])
    data.setdefault("tags", [])
    data.setdefault("faq", [])
    return data
