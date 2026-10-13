Data updates at the 59 of each hour. 

The local batch launcher is `scripts/run_wcs_scripts.ps1`; its installed copy
lives in `C:\Scripts\run_wcs_scripts.ps1`. Keep that copy in sync after launcher
changes. Run individual scripts with the project Pipenv environment.

Article attempts have a 60-second deadline covering browser startup, navigation,
HTML capture, extraction, and cleanup. Timed-out attempts retain their last saved
content; if no body was extracted, they retain the feed excerpt with `error=Y`.
Processing then continues to the next article. RSS feeds have a 30-second
deadline and a 5 MiB response limit; failed feeds are skipped for this run.

Updates checkpoint feed entries, AI decisions, completed articles, and interrupted
article content in `masterdata/pending/`. Each queue is deduplicated by URL.
Completed results are saved to the archive and exports before a cooperative
timeout; after a forced timeout the batch runs a separate recovery step to save
the durable results. CSV or timestamp failures leave those results queued for
retry. Accepted articles do not repeat AI review when work resumes, and articles
with captured content retain that content if their process is stopped. TRICARE
also preserves extracted text while sentiment is pending. Counts in new
timestamp records reflect completed articles; `pending` and `partial` describe
unfinished work. These local queues are excluded from Git with `masterdata/`.

The batch continues after script failures and timeouts, then runs the first Git
publication step. It subsequently resumes unfinished queues in turns using the
remaining batch budget, and publishes again after continuation. Continuation
uses saved entries without refetching feeds or repeating completed processing.
Work that still does not fit carries into the next hourly update; a queue that
makes no progress is deferred instead of repeatedly retried in the same batch.
OS locks prevent overlapping batches or two instances of the same update from
writing a queue concurrently. Run a script directly with Pipenv to consume its
queue and collect fresh feeds without the batch's time limit.

Defaults are 180 seconds without output, at most
600 seconds per script, and a 2,700-second (45-minute) batch budget. Each script
gets a share of the remaining budget so later updates receive time too; unused
time becomes available to later steps and continuation. Recovery uses up to 60
seconds from the same budget, and continuation reserves time for its final push.
Git publication is capped at 120 seconds and requires preconfigured,
noninteractive authentication. Heartbeats and a final failure summary appear in
the live log; the batch returns a failure status if work remains queued or a
step still fails after continuation. Update scripts return exit code 75 when
work remains, and exit code 73 if another process owns their lock.
Override limits with `-ScriptTimeoutSeconds`,
`-IdleTimeoutSeconds`, and `-RunTimeoutSeconds` on the PowerShell launcher.

Watch `C:\Scripts\pipenv_scripts_log.txt` for live script output. Python appends
and flushes every output chunk directly to that file while also displaying it in
the console. The launcher keeps only the current run and
`C:\Scripts\pipenv_scripts_log.previous.txt`, replacing the previous log each run
and removing legacy timestamped archives.
PowerShell launcher diagnostics are recorded separately in
`C:\Scripts\pipenv_launcher_log.txt`, also retaining one `.previous.txt` log.
When running `run_scripts.py` directly,
use `--log-file` with the path you want to watch.

Article attempts to the same host use a randomly selected 0.5–5 second interval.
Time already spent processing the previous article counts toward that interval.
HTTP 403/429, HTTP 503 with `Retry-After`, and recognized challenge pages pause
that host for 24 hours (longer if `Retry-After` requests it). Cooldowns persist
across scripts and hourly runs in `development/article_request_state.json`.
Blocked pages retain available feed content instead of saving challenge text.
ResearchGate links use feed content only because the site restricts automated
access. Financial Times (`ft.com` and its subdomains) also uses original feed
content to avoid extracting login prompts. These safeguards reduce requests;
they cannot guarantee a site will
allow automated access or remove an existing block. Pacing applies to article
navigations, not every browser asset or RSS feed request. Browser startup,
pacing, and extraction still share the existing 60-second article deadline.

CSV archives/exports and timestamp rewrites use temporary files and replacement
to preserve the previous complete file if an update stops during writing. Each
file is replaced independently. An interrupted write may leave a `.tmp` file.

Regression checks: `pipenv run python -m unittest discover -s tests -v`.

## Recent News 

* [DHA](https://essbiewgt.github.io/WCS/web/dha.html)
* [SAF](https://essbiewgt.github.io/WCS/web/saf.html)

## Raw Data 

* [DHA](https://github.com/EssbieWGT/WCS/blob/main/data/tricare.csv)
* [SAF](https://github.com/EssbieWGT/WCS/blob/main/data/saf.csv)
