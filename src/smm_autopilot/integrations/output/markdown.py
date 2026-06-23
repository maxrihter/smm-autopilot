"""Render the pipeline Report as a clean, language-neutral Markdown report —
the product's headline deliverable."""

from __future__ import annotations

from collections.abc import Callable

from ...models import Report

Writer = Callable[[str], None]


def render_markdown(report: Report, *, title: str = "Growth Report") -> str:
    """Render a full growth report as Markdown."""
    out: list[str] = []
    w = out.append

    w(f"# {title}")
    w("")
    w(f"_Run `{report.run_id}` · generated {report.generated_at:%Y-%m-%d %H:%M} UTC_  ")
    w(
        f"_Posts scraped: {report.total_posts_scraped} · "
        f"relevant after filter: {report.total_posts_filtered}_"
    )
    w("")

    _trends(report, w)
    _competitors(report, w)
    _signal_posts(report, w)
    _briefs(report, w)
    _ideas(report, w)
    _actions(report, w)
    _region(report, w)

    return "\n".join(out).rstrip() + "\n"


def _pct(value: float) -> str:
    # Engagement rate is a [0,1] fraction by convention; tolerate a value already
    # expressed as a percent rather than rendering "520.0%".
    pct = value * 100 if value <= 1 else value
    return f"{pct:.1f}%"


def _trends(report: Report, w: Writer) -> None:
    if not report.trends:
        return
    w("## 📈 Trends")
    w("")
    for t in report.trends:
        w(f"### {t.rank}. {t.title} — score {t.trend_score_display}/10")
        w("")
        if t.description:
            w(t.description)
            w("")
        meta: list[str] = []
        if t.engagement_rate:
            meta.append(f"ER {_pct(t.engagement_rate)}")
        if t.views_total:
            meta.append(f"{t.views_total:,} views")
        meta.append(f"{t.post_count} posts")
        if t.top_formats:
            meta.append(", ".join(t.top_formats))
        w(f"*{' · '.join(meta)}*")
        if t.hook_description:
            w(f"> Hook: {t.hook_description}")
        w("")


def _competitors(report: Report, w: Writer) -> None:
    rep = report.competitor_report
    if rep is None or not rep.competitors:
        return
    w("## 🥊 Competitors")
    w("")
    for c in rep.competitors:
        w(f"### @{c.username}")
        if c.summary:
            w("")
            w(c.summary)
        meta: list[str] = []
        if c.posting_frequency:
            meta.append(c.posting_frequency)
        if c.avg_engagement_rate:
            meta.append(f"avg ER {_pct(c.avg_engagement_rate)}")
        if c.content_formats:
            meta.append(", ".join(c.content_formats))
        if meta:
            w("")
            w(f"*{' · '.join(meta)}*")
        if c.top_topics:
            w(f"Topics: {', '.join(c.top_topics)}")
        w("")


def _signal_posts(report: Report, w: Writer) -> None:
    digest = report.influencer_digest
    if digest is None or not digest.top_viral_posts:
        return
    w("## 🔥 Signal posts")
    w("")
    for p in digest.top_viral_posts:
        w(
            f"- **@{p.account_username}** ({p.category}) — "
            f"{p.views:,} views, ER {_pct(p.engagement_rate)}"
        )
        if p.caption_snippet:
            w(f"  > {p.caption_snippet}")
        w(f"  {p.url}")
    w("")


def _briefs(report: Report, w: Writer) -> None:
    if not report.briefs:
        return
    w("## ✍️ Content briefs")
    w("")
    for b in report.briefs:
        status = "approved" if b.approved else "draft"
        w(f"### {b.title}  ·  {b.format}  ·  _{status}_")
        w("")
        if b.hook:
            w(f"**Hook:** {b.hook}")
            w("")
        w(b.body)
        w("")
        if b.cta:
            w(f"**CTA:** {b.cta}")
        if b.hashtags:
            w(" ".join(f"#{h.lstrip('#')}" for h in b.hashtags))
        w("")


def _ideas(report: Report, w: Writer) -> None:
    ideas = report.marketing_ideas
    if ideas is None or not ideas.ideas:
        return
    w("## 💡 Marketing ideas")
    w("")
    for i in ideas.ideas:
        w(f"### {i.title}  ·  {i.idea_type}  ·  viral {i.viral_score:.1f}/10  ·  {i.priority}")
        w("")
        w(i.concept)
        w("")
        if i.why_now:
            w(f"**Why now:** {i.why_now}")
        if i.cta:
            w(f"**CTA:** {i.cta}")
        w("")


def _actions(report: Report, w: Writer) -> None:
    plan = report.action_plan
    if plan is None or not plan.recommendations:
        return
    w("## 🎯 Strategic actions")
    w("")
    for r in plan.recommendations:
        w(f"### {r.title}  ·  {r.category}  ·  _{r.urgency}_")
        w("")
        w(r.scenario)
        w("")
        if r.rationale:
            w(f"**Why:** {r.rationale}")
            w("")


def _region(report: Report, w: Writer) -> None:
    ctx = report.region_context
    if ctx is None:
        return
    has_content = ctx.upcoming_events or ctx.news_headlines
    if not has_content:
        return
    w("## 🗓️ Regional events & news")
    w("")
    if ctx.upcoming_events:
        w("**Upcoming events**")
        w("")
        for e in ctx.upcoming_events:
            when = f"{e.event_date:%b %d}"
            tail = f" — in {e.days_until} days" if e.days_until else ""
            w(f"- **{e.name}** ({when}{tail}) · potential: {e.social_potential}")
        w("")
    if ctx.news_headlines:
        w("**Relevant news**")
        w("")
        for n in ctx.news_headlines:
            w(f"- [{n.title}]({n.url}) — {n.source}")
        w("")
