"""Generate source-grounded SVG flowcharts and render shareable PNG/PDF copies.

Run with the project's Python environment, which already includes Playwright.
Only files in this directory are written; collection/report scripts are not run.
"""

from html import escape
from pathlib import Path
import argparse
import json
import os
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
W, H = 2600, 2060
INK = "#172b42"
MUTED = "#53677c"
LINE = "#7890a4"
AMBER = "#ad7012"
RED = "#aa4b48"
FONT = "Segoe UI, Arial, sans-serif"


class Chart:
    def __init__(self, client, accent, pale, heading=None, subtitle=None, panels=None):
        self.client, self.accent, self.pale = client, accent, pale
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description">',
                      f'<title id="title">{client.upper()} news collection and report drafting flowchart</title>',
                      '<desc id="description">Two connected stages show RSS collection, filtering, article extraction, saved archives, separate report classification, decision branches, output files and editorial review.</desc>']
        self.rect(0, 0, W, H, "#f3f6fa", radius=0)
        self.text(65, 67, "WCS / WORKFLOW GUIDE", 20, MUTED, weight=700)
        self.text(65, 143, heading or f"{client.upper()}: from news feeds to report drafts", 55, INK, weight=700)
        self.text(65, 191, subtitle or "Follow the arrows through collection, then a separately invoked report run. Branches show what happens to each story.", 25, MUTED)
        self.rect(60, 232, 1090, 1400, "#ffffff", stroke="#dbe3ed", radius=24)
        self.rect(1245, 232, 1295, 1400, "#ffffff", stroke="#dbe3ed", radius=24)
        self.rect(60, 232, 1090, 8, accent, radius=0)
        self.rect(1245, 232, 1295, 8, accent, radius=0)
        panels = panels or ("01  COLLECT & ENRICH", "02  BUILD A REPORT DRAFT", f"scripts/{client}.py", f"scripts/{client}Report.py  /  separate command")
        self.text(100, 291, panels[0], 29, accent, weight=700)
        self.text(1285, 291, panels[1], 29, accent, weight=700)
        self.text(100, 320, panels[2], 20, MUTED)
        self.text(1285, 320, panels[3], 20, MUTED)

    def rect(self, x, y, w, h, fill, stroke=None, radius=16):
        border = f' stroke="{stroke}" stroke-width="2"' if stroke else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"{border}/>')

    def text(self, x, y, value, size=23, color=INK, weight=400, anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>')

    def box(self, x, y, w, h, title, lines, tone="main", size=23):
        fill, border, heading = {
            "main": (self.pale, "#d5e2ec", INK),
            "side": ("#f4f7fb", "#dbe3ed", INK),
            "review": ("#fff5e4", "#ebd4aa", AMBER),
            "exclude": ("#fff0ed", "#e9c9c4", RED),
            "output": (self.accent, self.accent, "#ffffff"),
        }[tone]
        self.parts.append('<g data-box="true">')
        self.rect(x, y, w, h, fill, border)
        self.text(x + 22, y + 36, title, 26, heading, 700)
        for i, line in enumerate(lines):
            self.text(x + 22, y + 64 + 27 * i, line, size, "#ffffff" if tone == "output" else MUTED)
        self.parts.append('</g>')

    def diamond(self, cx, cy, label, sub=None):
        hw, hh = 242, 60
        self.parts.append(f'<polygon points="{cx},{cy-hh} {cx+hw},{cy} {cx},{cy+hh} {cx-hw},{cy}" fill="{self.pale}" stroke="{self.accent}" stroke-width="2.5"/>')
        self.text(cx, cy + (8 if not sub else -4), label, 25, INK, 700, "middle")
        if sub:
            self.text(cx, cy + 26, sub, 19, MUTED, anchor="middle")

    def arrow(self, points, color=LINE, dashed=False, label=None, lx=None, ly=None):
        d = "M " + " L ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="9 7"' if dashed else ''
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"{dash}/>')
        x, y = points[-1]
        px, py = points[-2]
        if x > px:
            tip = f"{x},{y} {x-12},{y-6} {x-12},{y+6}"
        elif x < px:
            tip = f"{x},{y} {x+12},{y-6} {x+12},{y+6}"
        elif y > py:
            tip = f"{x},{y} {x-6},{y-12} {x+6},{y-12}"
        else:
            tip = f"{x},{y} {x-6},{y+12} {x+6},{y+12}"
        self.parts.append(f'<polygon points="{tip}" fill="{color}"/>')
        if label:
            self.text(lx, ly, label, 20, color, 700)

    def down(self, x, start, end, label=None):
        self.arrow([(x, start), (x, end)], label=label, lx=x + 16, ly=(start + end) / 2 + 6)

    def save(self):
        value = "\n".join(self.parts + ["</svg>"])
        ET.fromstring(value)
        (OUT / f"{self.client}-flowchart.svg").write_text(value, encoding="utf-8")


def build(client):
    tricare = client == "tricare"
    accent = "#245c99" if tricare else "#087e82"
    c = Chart(client, accent, "#edf4fc" if tricare else "#eaf7f5")
    reject = "TricareNo.csv" if tricare else "shippingNo.csv"
    ts = "tricareTS.json" if tricare else "shipping.json"
    c.box(100, 355, 600, 113, "Read RSS news feeds", ["One Google Alerts feed for TRICARE" if tricare else "Multiple feeds listed in static/shipping.csv", "Extract headlines, links, dates and excerpts."])
    c.down(400, 468, 505)
    c.box(100, 505, 600, 132, "Clean links & remove known stories", ["Remove blocked domains and tracking parameters.", f"Skip URLs already in masterdata/{client}.csv", f"or the rejection history: {reject}."], size=22)
    c.down(400, 637, 664)
    c.diamond(400, 724, "Any new stories?")
    c.arrow([(642, 724), (770, 724)], label="No", lx=686, ly=710)
    c.box(770, 670, 340, 108, "Log zero & stop", ["Append the run timestamp.", "Keep existing exports."], "side", size=21)
    c.down(400, 784, 834, "Yes")
    c.box(100, 834, 600, 164, "AI relevance filter", ["Ollama / qwen3:8b reads the headline + excerpt.", "Keep explicit, substantive TRICARE/DHA/MHS" if tricare else "Keep maritime emissions policy, sustainable fuels",
           "news: policy, reputation, benefits or operations." if tricare else "and major environmental industry/advocacy action.", "Only an 'interested' answer advances."], size=22)
    c.arrow([(700, 892), (770, 892)], color=RED)
    c.box(770, 834, 340, 164, "Reject & remember", ["'Not interested' or an", "unexpected reply is saved", f"to {reject}.", "Skip these on future runs."], "exclude", size=21)
    c.box(770, 1036, 340, 106, "Model call fails?", ["Skip for this run; leave", "eligible for a future retry."], "side", size=21)
    c.arrow([(700, 968), (744, 968), (744, 1085), (770, 1085)], dashed=True)
    c.down(400, 998, 1050, "Accepted")
    c.box(100, 1050, 600, 142, "Fetch & extract each article", ["Browser capture + body/metadata extraction (60s cap).", "Retain saved text on timeout; otherwise use the", "feed excerpt with error=Y if no body is available."], size=22)
    c.down(400, 1192, 1238)
    if tricare:
        c.box(100, 1238, 600, 110, "Add TRICARE sentiment", ["qwen3:8b scores the title + description:", "-1 negative  /  0 neutral  /  +1 positive."])
    else:
        c.box(100, 1238, 600, 110, "Standardize the article records", ["Keep title, source, body, description and firstEyes.", "The collection script has no sentiment scoring."], size=22)
    c.down(400, 1348, 1400)
    c.box(100, 1400, 600, 166, "Save archive, exports & run logs", [f"Full history: masterdata/{client}.csv", f"Recent exports: data/{client}.csv + uploads/{client}.csv", f"Run counts: timestamps/{ts}", "Extraction totals: development/scraped_bytes.txt"], "output", size=21)
    c.box(770, 1238, 340, 135, "Export time window", ["Last 3 days, based on", "publication date.", "Archive keeps full history."], "side", size=21)
    # This is a data dependency, not an automatic invocation of the report script.
    c.arrow([(700, 1500), (1197, 1500), (1197, 410), (1285, 410)], color=accent, dashed=True)
    c.text(825, 1480, "Archive input to a separate report run", 20, accent, 700)

    c.box(1285, 355, 625, 132, "Load archive & choose the report window", [f"Default input: masterdata/{client}.csv", "Default: last 72 hours of firstEyes (first observed).", "Set cutoff, lookback and AM / PM / adhoc edition."], size=22)
    c.down(1597, 487, 527)
    c.box(1285, 527, 625, 132, "Prepare & deduplicate candidates", ["Keep records observed inside the selected window.", "Clear existing manual category and ordering fields.", "Check URLs, cutoff dates and explicit --sent-csv files."], size=22)
    c.arrow([(1910, 591), (1980, 591)])
    c.box(1980, 527, 515, 132, "Route special cases", ["Already sent / duplicate URL: audit only.", "Invalid URL or future publication: review.", "Missing firstEyes / outside window: skip."], "side", size=22)
    c.down(1597, 659, 707)
    c.box(1285, 707, 625, 113, "Score relevance & possible categories", ["Cached facebook/bart-large-mnli zero-shot model.", "Uses title + description + a short body excerpt."], size=22)
    c.box(1980, 707, 515, 113, "Incomplete article text", ["If error=Y, omit the body from model input.", "The title and description still inform scoring."], "side", size=22)
    c.down(1597, 820, 864)
    if tricare:
        category = ["Propose topics such as Congress, T5 or Pharmacy.", "Social domains override to Social; official DHA/", "TRICARE domains to Outbound. Market stays blank."]
    else:
        category = ["Propose Policy, Industry, Technology and other topics.", "Tag markets from explicit headline/description geography.", "Missing or ambiguous geography requires review."]
    c.box(1285, 864, 625, 132, "Apply topic & client-specific rules", category, size=22)
    c.down(1597, 996, 1048)
    c.diamond(1597, 1108, "Apply decision rules", "relevance + category confidence")
    c.arrow([(1839, 1108), (1980, 1108)], color=AMBER, label="Review", lx=1860, ly=1092)
    c.box(1980, 1056, 515, 106, "Uncertain or flagged", ["Route to review.csv for an editor to assess.", "Includes weak/conflicting scores or data issues."], "review", size=22)
    c.arrow([(1760, 1128), (1945, 1188), (1945, 1276), (1980, 1276)], color=RED, label="Exclude", lx=1845, ly=1239)
    c.box(1980, 1226, 515, 106, "Clearly irrelevant", ["Exclude from the draft; keep the decision", "and scoring evidence in decisions.csv."], "exclude", size=22)
    c.down(1597, 1168, 1255, "Include")
    c.box(1285, 1255, 625, 133, "Assemble the proposed report", ["Sort by category, then newest publication first.", "Suppress exact normalized headline duplicates.", "Assign categoryorder and articleorder."], size=22)
    c.down(1597, 1388, 1443)
    # Review, exclusion and preliminary decisions all remain visible in the run.
    c.arrow([(2495, 591), (2517, 591), (2517, 1420), (2240, 1420), (2240, 1443)], dashed=True)
    c.arrow([(2495, 1108), (2517, 1108)], dashed=True, color=AMBER)
    c.arrow([(2495, 1276), (2517, 1276)], dashed=True, color=RED)
    c.box(1285, 1443, 1210, 133, "Write a new, uniquely named report run", [f"reports/{client}/<cutoff>_<edition>_<unique-id>/", "draft.csv: included stories   |   review.csv: flagged stories   |   decisions.csv: all candidate decisions",
           "manifest.json: settings, counts and provenance; optional --evaluate adds a harvested-CSV comparison."], "output", size=21)

    c.rect(60, 1664, 2480, 104, INK)
    c.text(91, 1705, "EDITORIAL HANDOFF", 23, "#a9cce2", 700)
    c.text(410, 1705, "Review the draft and flagged stories, resolve event-level duplicates, then finalize and send separately.", 25, "#ffffff", 600)
    c.text(410, 1743, "These scripts create draft files. Sending and updating finalized/sent history remain separate steps.", 23, "#d2dfea")
    c.box(60, 1810, 795, 148, "Two different time windows", ["Collection exports use publication date (3 days).", "Report candidates use firstEyes (72 hours by default).", "A late-discovered older article can enter a report."], "side", size=22)
    c.box(875, 1810, 850, 148, "Default decision thresholds", ["Include: relevance >= .75; relevance gap >= .10.", "Topic score >= .55 and topic gap >= .10, unless overridden.", "Exclude: relevance <= .30 and irrelevance >= .75."], "side", size=22)
    c.box(1745, 1810, 795, 148, "Reading this chart", ["Solid arrows: processing or a decision branch.", "Dashed arrows: saved-data input or exception/audit route.", "Scores are initial rules; other flags can require review."], "side", size=22)
    c.text(65, 2001, f"Source: scripts/{client}.py, {client}Report.py, getFunc.py, newsFunc.py and aiFunc.py. Based on the local implementation.", 20, MUTED)
    note = ("TRICARE is in run_scripts.py; report drafting is invoked separately. No accepted stories: TRICARE logs zero and exits."
            if tricare else "Shipping and shippingReport.py are invoked separately; neither is in the current run_scripts.py batch list.")
    c.text(65, 2036, note, 20, MUTED)
    c.save()


def build_state_summary():
    c = Chart("state-summary", "#66539b", "#f2effa",
              heading="STATE SUMMARY: from launcher to policy briefings",
              subtitle="Follow stateSummary.ps1 through its Python analysis, generated reports and the State Summary web viewer.",
              panels=("01  LAUNCH, PREPARE & CLASSIFY", "02  SUMMARIZE, SAVE & VIEW",
                      "scripts/stateSummary.ps1  ->  scripts/stateSummary.py", "scripts/stateSummary.py  ->  files and viewer"))
    # Replace generic accessibility copy with the state-summary workflow.
    c.parts[1] = '<title id="title">State Summary launcher, classification, summarization and report workflow</title>'
    c.parts[2] = '<desc id="description">The launcher starts Python, which reads the state-news archive, filters the last 24 hours, classifies headlines, summarizes accepted stories, writes reports and exports data for the web viewer.</desc>'
    c.box(100, 355, 600, 113, "Start the PowerShell launcher", [r"Append transcript to C:\Scripts\stateSummary.txt.", "Set the working directory to the WCS project."])
    c.down(400, 468, 515)
    c.box(100, 515, 600, 113, "Run Python in the Pipenv environment", ["Loop over the launcher script list (currently one):", "pipenv run python ./scripts/stateSummary.py"], size=22)
    c.box(770, 355, 340, 191, "Upstream input", ["stateNews.py runs separately.", "RSS feeds are listed in", "static/media_outlets.csv.", "Their text and metadata", "populate the states archive."], "side", size=20)
    c.arrow([(940, 546), (940, 751), (700, 751)], color=c.accent, dashed=True)
    c.down(400, 628, 690)
    c.box(100, 690, 600, 145, "Load, deduplicate & filter the archive", ["Read masterdata/states.csv.", "Deduplicate exact titles first; keep the first row.", "Then keep articles published in the last 24 hours."], size=22)
    c.down(400, 835, 883)
    c.box(100, 883, 600, 113, "Map each outlet to a state", ["Read the name -> state lookup from", "static/media_outlets.csv and replace the name field."], size=22)
    c.down(400, 996, 1045)
    c.box(100, 1045, 600, 141, "Classify headlines into six policy topics", ["facebook/bart-large-mnli on CUDA GPU 0.", "Process headline batches of 16 with multi-label scores.", "Select only the highest-scoring topic per article."], size=22)
    c.box(770, 833, 340, 245, "Topic thresholds", ["State Budget: .70", "K-12 Education: .70", "Public Health: .70", "Public Opinion Polls: .70", "Protests / civil unrest: .95", "Immigration / enforcement:", ".90"], "side", size=20)
    c.down(400, 1186, 1210)
    c.diamond(400, 1270, "Top topic passes?", "score >= that topic's threshold")
    c.arrow([(642, 1270), (770, 1270)], color=RED, label="No", lx=685, ly=1255)
    c.box(770, 1210, 340, 132, "Skip this article", ["classified_issue = None.", "Remove it before sending", "articles to the summarizer."], "exclude", size=21)
    c.down(400, 1330, 1390, "Yes")
    c.box(100, 1390, 600, 132, "Pass accepted articles to summarization", ["Carry the assigned state, topic and headline score.", "Keep the article text, source title, outlet and URL.", "No second topic is assigned if the top topic fails."], "output", size=22)
    c.arrow([(700, 1484), (1197, 1484), (1197, 410), (1285, 410)], color=c.accent)
    c.text(792, 1466, "Accepted stories, within the same Python run", 19, c.accent, 700)

    c.box(1285, 355, 625, 132, "Prepare each accepted article's text", ["Use up to four concurrent worker threads.", "Strip HTML tags and collapse whitespace.", "Build a prompt with the state and assigned issue."], size=22)
    c.arrow([(1910, 414), (1980, 414)], color=RED, dashed=True)
    c.box(1980, 355, 515, 132, "Empty cleaned text?", ["Return no summary for that article.", "The active path uses the text field; it has", "no explicit description fallback."], "exclude", size=22)
    c.down(1597, 487, 535)
    c.box(1285, 535, 625, 164, "Generate an issue-focused summary", ["POST to localhost:11434/api/generate.", "Actual default model: mistral-nemo; stream=False.", "Prompt requests <= 5 sentences about the issue,", "favoring government, policy and political impacts."], size=22)
    c.arrow([(1910, 611), (1980, 611)], color=RED, dashed=True)
    c.box(1980, 535, 515, 164, "No usable model response?", ["An API error returns an empty string.", "Empty responses or a literal SKIP are omitted.", "Each summary request has a 600-second timeout.", "The script continues with other articles."], "exclude", size=21)
    c.down(1597, 699, 760)
    c.box(1285, 760, 625, 142, "Collect summaries by state and issue", ["Gather worker results as they finish.", "Store summary, title, outlet, URL and headline score.", "Article order follows completion, rather than date."], size=22)
    c.down(1597, 902, 955)
    c.box(1285, 955, 625, 113, "Clean the summary text", ["Remove bullet characters and asterisks; trim spaces.", "Keep each summary with its original story metadata."], size=22)
    c.down(1597, 1068, 1140)
    c.box(1285, 1140, 625, 230, "Write the reports and data exports", ["development/state_issue_summary.json", "development/issue_weekly_report.docx", "development/state_weekly_report.docx", "uploads/state_summary.csv", "CSV: state, topic, outlet, headline, summary, URL.", "Outputs use the same file paths on each run."], "output", size=21)
    c.arrow([(1910, 1230), (1980, 1230)], color=c.accent, dashed=True, label="CSV", lx=1930, ly=1215)
    c.box(1980, 1168, 515, 185, "State Summary web viewer", ["Flask serves templates/state_summary.html.", "D3 loads the CSV and displays linked headlines",
           "with summaries, grouped State -> Topic or",
           "Topic -> State. Jump links include story counts.", "Fetch the timestamp for the last-updated label."], "side", size=21)
    c.down(1597, 1370, 1440)
    c.box(1285, 1440, 625, 132, "Log the result & finish the run", ["Append timestamp + row count to static/stateSummary.json.", "Request Ollama to unload mistral-nemo (keep_alive=0).", "Return to PowerShell and stop the transcript."], size=21)
    c.arrow([(1910, 1500), (1945, 1500), (1945, 1370), (2240, 1370), (2240, 1353)], color=c.accent, dashed=True)
    c.text(1995, 1404, "Timestamp input", 20, c.accent, 700)
    c.rect(60, 1664, 2480, 104, INK)
    c.text(91, 1705, "REPORT VIEWS", 23, "#d0c6ef", 700)
    c.text(410, 1705, "Issue-first Word report: topic -> states. State-first Word report: state -> topics, with a page break per state.", 24, "#ffffff", 600)
    c.text(410, 1743, "Both include linked headlines and summaries. The web viewer offers both grouping modes for the same exported stories.", 23, "#d2dfea")
    c.box(60, 1810, 795, 148, "Actual data window", ["The analysis uses the last 24 hours by published date.", "It does not use firstEyes for eligibility.", "The 'weekly' filenames do not change this window."], "side", size=22)
    c.box(875, 1810, 850, 148, "One topic per story", ["Six scores are calculated; only the top topic is considered.", "A below-threshold top score means the story is skipped.", "There is no review queue or alternate-topic fallback."], "side", size=22)
    c.box(1745, 1810, 795, 148, "Reading this chart", ["Solid arrows: processing or an acceptance decision.", "Dashed arrows: upstream/viewer inputs or skip branches.", "The viewer reads files; it is not launched by PowerShell."], "side", size=22)
    c.text(65, 2001, "Source: scripts/stateSummary.ps1, stateSummary.py, stateNews.py, getFunc.py, app.py and templates/state_summary.html.", 20, MUTED)
    c.text(65, 2036, "The launcher currently calls only stateSummary.py. State-news collection and web deployment are separate operations.", 20, MUTED)
    c.save()


def render(clients=("tricare", "shipping"), pdf_name="news-workflows.pdf"):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Use an existing cached headless browser; do not download dependencies.
        cache = Path(os.environ["LOCALAPPDATA"]) / "ms-playwright"
        installed = sorted(cache.glob("chromium_headless_shell-*/chrome-win/headless_shell.exe"))
        if not installed:
            raise RuntimeError("No cached Playwright headless Chromium found")
        browser = p.chromium.launch(headless=True, executable_path=str(installed[-1]), timeout=15000)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for client in clients:
            svg = (OUT / f"{client}-flowchart.svg").read_text(encoding="utf-8")
            page.set_content('<html><head><meta charset="utf-8"><style>body{margin:0}svg{display:block}</style></head><body>' + svg + '</body></html>')
            png = page.screenshot(full_page=True, timeout=10000)
            # Check actual browser text metrics before accepting the output.
            overflow = page.evaluate("""() => [...document.querySelectorAll('text')].filter(t => {
                const r = t.getBBox(); return r.x < 0 || r.x + r.width > 2600 || r.y + r.height > 2060;
            }).map(t => t.textContent)""")
            if overflow:
                raise ValueError(f"Text outside canvas: {overflow}")
            box_overflow = page.evaluate("""() => [...document.querySelectorAll('g[data-box]')].flatMap(g => {
                const box = g.querySelector('rect').getBBox();
                return [...g.querySelectorAll('text')].filter(t => {
                    const r = t.getBBox(); return r.x + r.width > box.x + box.width - 10 || r.y + r.height > box.y + box.height - 5;
                }).map(t => t.textContent);
            })""")
            if box_overflow:
                raise ValueError(f"Text outside its box: {box_overflow}")
            temporary = OUT / f"{client}-flowchart.png.tmp"
            temporary.write_bytes(png)
            temporary.replace(OUT / f"{client}-flowchart.png")
        svgs = [(OUT / f"{name}-flowchart.svg").read_text(encoding="utf-8") for name in clients]
        html = '<html><head><meta charset="utf-8"><style>@page{size:2600px 2060px;margin:0}body{margin:0}svg{display:block;break-after:page}svg:last-child{break-after:auto}</style></head><body>' + ''.join(svgs) + '</body></html>'
        page.set_content(html)
        pdf = page.pdf(width=f"{W}px", height=f"{H}px", print_background=True, margin={key: "0" for key in ("top", "bottom", "left", "right")})
        temporary = OUT / f"{pdf_name}.tmp"
        temporary.write_bytes(pdf)
        temporary.replace(OUT / pdf_name)
        browser.close()
    print(json.dumps({"generated": [p.name for p in OUT.iterdir() if p.suffix in {".svg", ".png", ".pdf"}]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", choices=("news", "state-summary"), default="news")
    args = parser.parse_args()
    if args.workflow == "state-summary":
        build_state_summary()
        render(("state-summary",), "state-summary-workflow.pdf")
    else:
        for name in ("tricare", "shipping"):
            build(name)
        render()
