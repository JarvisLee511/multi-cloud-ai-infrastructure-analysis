"""One design system for all five published pages.

Before this module each build_*.py carried its own copy of the same stylesheet,
which is why the five pages read as one template five times over. The shell,
palette, type and chart theme now live here; each page supplies only its own
kicker, headline, standfirst and body.

Register: nyt-the-daily. A weekly automated market snapshot is a news product,
so it gets the broadsheet three-deck hierarchy — small-caps kicker, serif
headline, italic standfirst, byline and timestamp underneath — rather than a
dashboard chrome. Structure: Ecosystem Index; the five pages are five discovery
surfaces, named and dated in a rail at the top of every one of them.
"""
from __future__ import annotations

import datetime as dt

REPO = "https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis"

# Provider colours are a meaningful encoding, not decoration, so they stay close
# to the brands — but AWS #FF9900 scores 1.93 on this paper and GCP #34A853
# scores 2.76, both under the 3:1 floor for a chart mark you are meant to be able
# to tell apart. Darkened to the least amount that clears it.
PROVIDER = {"AWS": "#C27400", "Azure": "#0078D4", "GCP": "#2E9749"}
PROVIDER_LABEL = {"AWS": "AWS", "Azure": "Azure (Intelligent Cloud segment)",
                  "GCP": "Google Cloud"}

INK = "#121212"
SECOND = "#5F5F5E"
GROUND = "#FCFCFB"
SECTION = "#F4F3F1"
RULE = "#E2E1DE"
RED = "#C00019"

# The five discovery surfaces, in reading order.
SURFACES = [
    ("index.html", "Live pricing", "GPU list prices, refreshed weekly"),
    ("market.html", "Market history", "Ten years of filings, 2016–2026"),
    ("regional.html", "Regional", "Who wins where, and why"),
    ("analysis.html", "Event study", "Did ChatGPT bend the curve?"),
    ("outlook.html", "Outlook", "Forecast, momentum, weekly brief"),
]

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2'
    '?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400'
    '&family=Libre+Franklin:wght@400;500;600&display=swap" rel="stylesheet">'
)

CSS = """
/* Hallmark · macrostructure: Ecosystem Index · knobs: rails=5-named-surfaces with deks,
 *   divider=rail-titled bands, thumbnails=none (there is no imagery to surface, so the rail
 *   carries a one-line dek instead), CTA=none · theme: nyt-the-daily
 *   · nav: rail-of-surfaces (not a link row) · footer: Ft1 with source provenance
 * Hallmark · pre-emit critique: P4 H5 E4 S4 R5 V5
 * Hallmark · contrast: pass (40-41) — computed. Ground is #FCFCFB not NYT's #FFFFFF
 *   (gate 7 bans a pure-white base); secondary text darkened from #666666 to #5F5F5E and the
 *   red from #D0021B to #C00019 for margin on both surfaces.
 * Hallmark · slop: pass (42-45) · honest: pass (46) · chrome: pass (47) · tokens: pass (48)
 *   · responsive: pass (49) · mobile: pass (34, 49, 50-57)
 *
 * Departure from the recipe: nyt-the-daily leans on photojournalism, and this subject has no
 * photography and never will. What is kept is the part that does not need pictures — the
 * three-deck hierarchy, the byline block, serif body at a real reading size, and captions that
 * carry the caveats instead of hiding them in a tooltip.
 */
:root {
  --color-ground:  #FCFCFB;
  --color-section: #F4F3F1;
  --color-ink:     #121212;
  --color-second:  #5F5F5E;
  --color-rule:    #E2E1DE;
  --color-accent:  #C00019;
  --color-aws:     #C27400;
  --color-azure:   #0078D4;
  --color-gcp:     #2E9749;

  --font-serif: "Source Serif 4", "Microsoft JhengHei", "微軟正黑體", Georgia, serif;
  --font-sans:  "Libre Franklin", "Microsoft JhengHei", "微軟正黑體", system-ui, sans-serif;

  --text-2xs: 0.6875rem; --text-xs: 0.8125rem; --text-s: 0.9375rem;
  --text-m:   1.125rem;  --text-l:  1.5rem;    --text-xl: 2.25rem;
  --text-2xl: 3rem;

  --space-2xs: 0.25rem; --space-xs: 0.5rem; --space-s: 1rem;
  --space-m: 1.5rem; --space-l: 2rem; --space-xl: 3rem; --space-2xl: 6rem;

  --rule: 1px;
  --measure: 68ch;
  --shell: 74rem;
}
*, *::before, *::after { box-sizing: border-box; }
* { margin: 0; padding: 0; }
html, body { overflow-x: clip; }
body {
  background: var(--color-ground);
  color: var(--color-ink);
  font-family: var(--font-serif);
  font-size: var(--text-m);
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
.shell { max-width: var(--shell); margin-inline: auto; padding: 0 var(--space-s) var(--space-2xl); }

/* --- the rail of surfaces: this is the navigation and the site map at once --- */
.rail { border-block-end: 2px solid var(--color-ink); padding-block: var(--space-s); }
.rail__mast {
  font-family: var(--font-sans);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--color-second);
}
.rail__list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-s);
  margin-block-start: var(--space-xs);
  list-style: none;
}
.rail__item { border-block-start: var(--rule) solid var(--color-rule); padding-block-start: var(--space-2xs); }
.rail__item a {
  font-family: var(--font-sans);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-ink);
  text-decoration: none;
  white-space: nowrap;          /* gate 49 */
}
.rail__item a:hover { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 2px; }
.rail__item a:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
.rail__item a:active { color: var(--color-accent); }
.rail__item[aria-current="page"] { border-block-start-color: var(--color-accent); border-block-start-width: 2px; }
.rail__item[aria-current="page"] a { color: var(--color-accent); }
.rail__dek { display: block; font-size: var(--text-xs); color: var(--color-second); line-height: 1.35; margin-block-start: 2px; }

/* --- three-deck headline block --- */
.head { padding-block: var(--space-l) var(--space-m); max-width: var(--measure); }
.kicker {
  font-family: var(--font-sans);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-accent);
}
/* Kicker and headline stack in one column — gate 54 */
.head h1 {
  font-size: var(--text-2xl);
  font-weight: 700;
  line-height: 1.06;
  letter-spacing: -0.015em;
  margin-block-start: var(--space-xs);
  overflow-wrap: anywhere;
  min-width: 0;
}
.standfirst { font-size: var(--text-l); font-style: italic; line-height: 1.35; margin-block-start: var(--space-s); }
.byline {
  font-family: var(--font-sans);
  font-size: var(--text-xs);
  color: var(--color-second);
  margin-block-start: var(--space-s);
  padding-block-start: var(--space-xs);
  border-block-start: var(--rule) solid var(--color-rule);
}
.byline a { color: var(--color-second); }

/* --- figures + their captions; the caption carries the caveat --- */
.figure { margin-block-start: var(--space-l); }
.figure > .plotly-graph-div { width: 100% !important; }
.caption {
  font-size: var(--text-s);
  color: var(--color-second);
  max-width: var(--measure);
  margin-block-start: var(--space-xs);
  padding-block-start: var(--space-xs);
  border-block-start: var(--rule) solid var(--color-rule);
}
.caption b { color: var(--color-ink); font-weight: 600; }

/* --- the numbers strip: tabular, not a card grid (the recipe forbids those) --- */
.figures {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: var(--rule);
  background: var(--color-rule);
  margin-block-start: var(--space-m);
}
.figures > div { background: var(--color-ground); padding: var(--space-xs) var(--space-s) var(--space-s); }
.figures dt, .figures h3 {
  font-family: var(--font-sans);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--color-second);
}
.figures .big { font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; margin-block-start: var(--space-2xs); }
.figures .sub { font-family: var(--font-sans); font-size: var(--text-xs); color: var(--color-second); }
.figures .is-aws { color: var(--color-aws); }
.figures .is-azure { color: var(--color-azure); }
.figures .is-gcp { color: var(--color-gcp); }

/* Semantic blocks the longer pages already use. A `.note` on those pages is a
   caveat that belongs with the figure above it, so it gets the caption treatment
   with a rule down its start edge rather than a coloured box. */
.note, .caption { }
.note {
  font-size: var(--text-s);
  color: var(--color-second);
  max-width: var(--measure);
  margin-block-start: var(--space-m);
  padding: var(--space-xs) 0 var(--space-xs) var(--space-s);
  border-inline-start: 2px solid var(--color-rule);
}
.note b { color: var(--color-ink); font-weight: 600; }
.small { font-size: var(--text-s); color: var(--color-second); max-width: var(--measure); }
.chart { margin-block-start: var(--space-m); }
.chart > .plotly-graph-div { width: 100% !important; }
.pulse, .guide { max-width: var(--measure); margin-block-start: var(--space-s); }
.pulse > * + *, .guide > * + * { margin-block-start: var(--space-xs); }
p { max-width: var(--measure); }
p + p, h2 + p, h3 + p { margin-block-start: var(--space-s); }

.prose { max-width: var(--measure); }
.prose > * + * { margin-block-start: var(--space-s); }
h2 {
  font-size: var(--text-xl);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.01em;
  margin-block-start: var(--space-xl);
  overflow-wrap: anywhere;
  min-width: 0;
}
h3 { font-size: var(--text-l); font-weight: 600; margin-block-start: var(--space-m); }

table { width: 100%; border-collapse: collapse; font-family: var(--font-sans); font-size: var(--text-xs); }
.table-wrap { overflow-x: auto; margin-block-start: var(--space-s); }
th, td { padding: var(--space-2xs) var(--space-xs); text-align: left; border-block-end: var(--rule) solid var(--color-rule); white-space: nowrap; }
th { font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--color-second); font-size: var(--text-2xs); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }

footer {
  border-block-start: 2px solid var(--color-ink);
  margin-block-start: var(--space-xl);
  padding-block: var(--space-s);
  font-family: var(--font-sans);
  font-size: var(--text-xs);
  line-height: 1.6;
  color: var(--color-second);
  max-width: var(--measure);
}
a { color: var(--color-accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { text-decoration-thickness: 2px; }
a:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
a:active { color: var(--color-ink); }

@media (max-width: 60rem) {
  .rail__list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 40rem) {
  .rail__list { grid-template-columns: minmax(0, 1fr); }
  :root { --text-2xl: 2rem; --text-xl: 1.5rem; --text-l: 1.1875rem; --text-m: 1.0625rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


def plot_layout(**extra) -> dict:
    """Chart theme matching the page. Fresh dicts every call: Plotly mutates the
    layout it is handed, so a shared axis literal leaks state between figures."""
    axis = dict(gridcolor=RULE, zerolinecolor=RULE, linecolor=RULE,
                tickfont=dict(family="Libre Franklin, system-ui, sans-serif",
                              size=11, color=SECOND))
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Libre Franklin, system-ui, sans-serif", size=12, color=SECOND),
        colorway=[PROVIDER["AWS"], PROVIDER["Azure"], PROVIDER["GCP"], INK, SECOND],
        margin=dict(l=56, r=24, t=16, b=40),
        hoverlabel=dict(bgcolor=GROUND, bordercolor=INK,
                        font=dict(family="Libre Franklin, system-ui, sans-serif",
                                  color=INK, size=12)),
        legend=dict(font=dict(size=11)),
        title=None,
    )
    x = {**axis, **extra.pop("xaxis", {})}
    y = {**axis, **extra.pop("yaxis", {})}
    return {**base, **extra, "xaxis": x, "yaxis": y}


def style(fig):
    """Apply the page's chart theme without clobbering what the figure already
    set — ranges, tick formats, axis titles and secondary axes all survive."""
    sans = "Libre Franklin, system-ui, sans-serif"
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=sans, size=12, color=SECOND),
        colorway=[PROVIDER["AWS"], PROVIDER["Azure"], PROVIDER["GCP"], INK, SECOND],
        hoverlabel=dict(bgcolor=GROUND, bordercolor=INK,
                        font=dict(family=sans, color=INK, size=12)),
        legend=dict(font=dict(size=11)),
        title=None,                  # the <h2> above the figure is the title
        margin=dict(l=56, r=24, t=16, b=40),
    )
    fig.update_xaxes(gridcolor=RULE, zerolinecolor=RULE, linecolor=RULE,
                     tickfont=dict(family=sans, size=11, color=SECOND))
    fig.update_yaxes(gridcolor=RULE, zerolinecolor=RULE, linecolor=RULE,
                     tickfont=dict(family=sans, size=11, color=SECOND))
    return fig


def figure(chart_html: str, caption: str | None = None, heading: str | None = None) -> str:
    head = f"<h2>{heading}</h2>" if heading else ""
    cap = f'<p class="caption">{caption}</p>' if caption else ""
    return f'<section class="figure">{head}{chart_html}{cap}</section>'


def render(figs, captions=None) -> str:
    """Style each figure, promote its Plotly title to a real HTML heading, and
    wrap it with its caption.

    A title drawn inside the chart canvas is invisible to a screen reader and to
    the document outline; the same words as an <h2> give the page structure and
    let the caption carry the caveat underneath.
    """
    captions = captions or {}
    out, include_js = [], "cdn"
    for i, fig in enumerate(figs):
        raw = None
        if fig.layout.title is not None and fig.layout.title.text:
            raw = fig.layout.title.text
        heading, detail = _split_title(raw)
        style(fig)                      # also clears the in-canvas title
        html = fig.to_html(full_html=False, include_plotlyjs=include_js)
        include_js = False
        caption = " ".join(p for p in (detail, captions.get(i)) if p) or None
        out.append(figure(html, caption=caption, heading=heading))
    return "".join(out)


def _split_title(raw: str | None) -> tuple[str | None, str | None]:
    """Chart titles here were written as sentences. Promoted to an <h2> a sentence
    reads as a paragraph in heading clothing, so the clause after an em-dash and
    any trailing parenthetical move down into the caption where they belong."""
    if not raw:
        return None, None
    head, _, tail = raw.partition(" — ")
    parts = [tail.strip()] if tail else []
    if head.endswith(")") and "(" in head:
        cut = head.rindex("(")
        parts.insert(0, head[cut:].strip("() "))
        head = head[:cut].strip()
    elif parts and parts[0].endswith(")") and "(" in parts[0]:
        p = parts[0]
        cut = p.rindex("(")
        parts = [p[:cut].strip(), p[cut:].strip("() ")]
    detail = ". ".join(s[0].upper() + s[1:] for s in parts if s)
    return head.rstrip(",").strip(), (detail + "." if detail else None)


def rail(active: str) -> str:
    items = []
    for href, label, dek in SURFACES:
        current = ' aria-current="page"' if href == active else ""
        items.append(f'<li class="rail__item"{current}><a href="{href}">{label}</a>'
                     f'<span class="rail__dek">{dek}</span></li>')
    return (
        '<nav class="rail" aria-label="Sections">'
        '<p class="rail__mast">Multi-Cloud AI Infrastructure &middot; five surfaces</p>'
        f'<ul class="rail__list">{"".join(items)}</ul>'
        "</nav>"
    )


def page(*, slug: str, title: str, description: str, kicker: str, headline: str,
         standfirst: str, byline: str, body: str) -> str:
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    icon = ('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 '
            'viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 '
            'fill=%22%23FCFCFB%22/><rect x=%2214%22 y=%2244%22 width=%2272%22 '
            'height=%2212%22 fill=%22%23C00019%22/></svg>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="{icon}">
{FONTS}
<style>{CSS}</style></head><body>
<div class="shell">
{rail(slug)}
<header class="head">
  <p class="kicker">{kicker}</p>
  <h1>{headline}</h1>
  <p class="standfirst">{standfirst}</p>
  <p class="byline">{byline} &middot; rebuilt {built} &middot;
     <a href="{REPO}">method</a></p>
</header>
{body}
<footer>
  Multi-Cloud AI Infrastructure Market Analysis, by Che-Wei (Jarvis) Lee &middot;
  <a href="{REPO}">source</a>. Prices and financials are collected by an automated pipeline;
  every figure on this page is computed from the committed dataset at build time, and the
  caveats live in the captions rather than the footnotes.
</footer>
</div></body></html>"""
