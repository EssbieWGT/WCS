Data updates at the 59 of each hour. 

The local batch launcher is `scripts/run_wcs_scripts.ps1`; its installed copy
lives in `C:\Scripts\run_wcs_scripts.ps1`. Keep that copy in sync after launcher
changes. Run individual scripts with the project Pipenv environment.

Article attempts have a 60-second deadline covering browser startup, navigation,
HTML capture, extraction, and cleanup. Timed-out attempts retain their last saved
content; if no body was extracted, they retain the feed excerpt with `error=Y`.
Processing then continues to the next article. RSS feeds have a 30-second
deadline and a 5 MiB response limit; failed feeds are skipped for this run.

The batch continues after script failures and timeouts, including attempting the
final Git publication step. Defaults are 180 seconds without output, at most
600 seconds per script, and a 2,700-second (45-minute) batch budget. Each script
gets a share of the remaining budget so later updates receive time too; unused
time becomes available to later steps. Git publication is capped at 120 seconds
and requires preconfigured, noninteractive authentication. Heartbeats and a final
failure summary appear in the live log; the batch returns a failure status if
any step fails. Override limits with `-ScriptTimeoutSeconds`,
`-IdleTimeoutSeconds`, and `-RunTimeoutSeconds` on the PowerShell launcher.

Watch `C:\Scripts\pipenv_scripts_log.txt` for live script output. Python appends
and flushes every output chunk directly to that file while also displaying it in
the console. The launcher archives the previous run before starting a new log.
PowerShell launcher diagnostics are recorded separately in
`C:\Scripts\pipenv_launcher_log.txt`. When running `run_scripts.py` directly,
use `--log-file` with the path you want to watch.

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
