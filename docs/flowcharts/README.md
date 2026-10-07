# WCS workflow graphics

Each graphic covers news collection through the separate report-drafting command,
including filtering decisions, saved files and the handoff to an editor.

- `tricare-flowchart.png` and `shipping-flowchart.png`: shareable graphics, 2600 × 2060 pixels.
- Corresponding `.svg` files: scalable graphics with selectable text.
- `news-workflows.pdf`: both graphics in a two-page printable document.

The graphics are based on the local collection and report scripts, plus
`getFunc.py`, `aiFunc.py` and `newsFunc.py`. They describe the current code, without
running data collection, classification, publication or sending.

The collection exports include the last three days by publication date. The
report scripts instead select the last 72 hours by `firstEyes` by default.
The report scripts read the full archive, not the recent app export.

TRICARE adds sentiment during collection. In report drafting, it assigns topic
categories with Social and Outbound source-domain overrides and leaves market
blank. Shipping does not score sentiment during collection; its report draft
assigns topics and infers geographic markets from headline/description evidence.

The include/exclude thresholds are initial, adjustable rules. Missing headlines,
weak or conflicting scores, and uncertain shipping markets can require review;
TRICARE also flags undefined historical category codes. Exclusion requires low
relevance and strong irrelevance support with no preceding blocking flags.
Exact URL/headline deduplication does not resolve every duplicate event.

Optional `--sent-csv` inputs must represent reports actually finalized or sent.
Generating a draft does not change sent history. Optional `--evaluate` compares
URL-matched candidates against a harvested CSV; it does not feed historical
labels into classification or measure full end-to-end accuracy. `--preview`
prints candidate counts without loading the model or creating report files.

TRICARE collection is included in the current `run_scripts.py` batch. Shipping
collection and both report scripts must be invoked separately. The batch's
Git publication step is separate from creating or sending a client report.

Implementation edge case: TRICARE explicitly logs and exits if no articles pass
the AI filter. Shipping currently continues with an empty result; `process_csv`
can log an error and retain existing exports if the required columns are absent.
The shipping chart's downstream steps show the normal accepted-story path.

Regenerate with the existing project environment:

```powershell
pipenv run python docs/flowcharts/build_flowcharts.py
```

Rendering uses the already-installed Playwright and cached headless Chromium. The generator
writes only these graphics and checks SVG structure, canvas bounds and text bounds
within each box.

## State Summary workflow

`state-summary-flowchart.png` and its `.svg` copy explain the workflow around
`scripts/stateSummary.ps1`. `state-summary-workflow.pdf` is a one-page copy.
It uses the same dimensions and graphic style as the earlier charts.

The PowerShell launcher appends a transcript to `C:\Scripts\stateSummary.txt`,
changes to the project directory, and runs `scripts/stateSummary.py` through
Pipenv. The state-news collection script is an upstream dependency that runs
separately; it is not called by this launcher.

The Python script reads `masterdata/states.csv`, deduplicates exact titles before
filtering the last 24 hours by publication date, and maps outlet names to states
using `static/media_outlets.csv`. It loads BART-large-MNLI onto CUDA GPU 0 and
classifies headline batches of 16. Although scores are calculated with
`multi_label=True`, only the top topic is considered. It must meet its own
threshold: .70 for State Budget, K-12 Education, Public Health and Public Opinion
Polls; .95 for Protests and Civil Unrest; .90 for Immigration and Immigration
Enforcement. Other stories are removed before summarization.

Up to four worker threads send cleaned article text, its state and assigned issue
to the local Ollama API. The actual default model is `mistral-nemo`, as specified
in `call_ollama`; older comments do not determine the active model. The prompt
requests at most five sentences focused on policy/government impacts. Empty
responses, API errors and literal `SKIP` responses do not become report entries.
The active summary path reads only `text`, without an explicit description
fallback. Missing CSV values can become the string `nan` during text cleaning,
so the empty-text check is not a complete missing-content validator.

Results are grouped by state and issue in worker-completion order. Bullet
characters and asterisks are removed before writing:

- `development/state_issue_summary.json`: summaries with story metadata and scores.
- `development/issue_weekly_report.docx`: issue-first, then alphabetical states.
- `development/state_weekly_report.docx`: alphabetical states, then configured
  issue order, with page breaks between states.
- `uploads/state_summary.csv`: state, topic, outlet, headline, summary and URL.
- `static/stateSummary.json`: appended run-start timestamp and final CSV row count.

Despite the Word filenames, the input window is 24 hours. The script writes to
the same output paths each time. It requests an Ollama model unload at the end;
then the launcher stops its transcript. Per-summary API requests have a
600-second timeout; this launcher has no overall run deadline or explicit
Python exit-code handling.

The State Summary page in `templates/state_summary.html` reads the CSV and the
timestamp via Flask. It offers State -> Topic and Topic -> State grouping, linked
headlines, summaries and jump links with counts. The PowerShell launcher does
not launch the viewer or deploy the website.

Regenerate only the State Summary graphic:

```powershell
pipenv run python docs/flowcharts/build_flowcharts.py --workflow state-summary
```

Only the graphic generator was run. The actual analysis workflow was inspected
without executing it or replacing any of its reports or data files.
