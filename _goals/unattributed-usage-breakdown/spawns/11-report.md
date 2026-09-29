**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: 03-readme-columns (document new lake columns)

### Requirements checklist
- [x] README lake section: both table bullets say `unknown` rows split additionally by (`attribution_source`, `unattributed_project`); attributed rows keep grain (README.md ~L306-312)
- [x] attribution_source table: timeline / no_remote / absent / desktop-scratch with meanings, plus `wrapper` not expected on unknown rows (new subsection "Unattributed usage in the lake tables", README ~L346-351)
- [x] unattributed_project rule: root folder only, outer zone (home prefix incl. WSL / Git Bash, run of outer folders and containers), in-project containers point to parent, per session, `local:(home)`, `local:(scratchpad)`, `local:(other)`, never path/username, query-time and retroactive, diagnostic only, accepted-mislabel caveats (README ~L353-393). Examples used: Dashnoard, source\repos\proj, C:\Cyclotron\proj\src\components, C:\Users\<name>\orbit. No real usernames. The task 01 spec's Definitions were not re-read, so wording rests on project_label.py alone, which I did read.
- [x] Module list: `project_label.py` bullet added after `attribute.py` (README L154); `export.py` bullet mentions the two columns, grain, and summing (README L167)
- [x] Power BI note: row counts changed, sum don't count, filter `repo = 'unknown' AND attribution_source <> ''`, real repo named `unknown` stays unsplit with blank class
- [x] Collision correction described (summing after `[1m]` / dated snapshots / email coalescing; totals match invoice.py; historical Fabric totals rise on next sync)
- [x] Grain lines (README lake bullets and export.py bullet) mention the additional grain for unknown rows
- [x] fabric/README.md: both "Result" lists equal the export field lists exactly, in order (drift fixed: bill_name -> repo; bill_name, repo -> repo, repo_key)
- [x] fabric/README.md: one sentence pointing to the top-level README

Out-of-scope follow-ups (hook scratchpad detection, cwd undercounting of work done in another repo by absolute path) are named only as known gaps, not as done. `cost_source` is not mentioned.

### Files changed
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\README.md — targeted insertions only (module bullets, lake bullets, new "###" subsection before the `---`)
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\fabric\README.md — column lists corrected plus a pointer sentence

### Verification
AC1 — Field lists printed from `billing.otel.export`:
- SUMMARY_FIELDS: `usage_date_utc, period_start, period_end, repo, user_email, tokens, actual_cost_usd, markup, total_billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`
- LINE_FIELDS: `usage_date_utc, period_start, period_end, repo, repo_key, model, user_email, tokens, actual_cost_usd, billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`

Grep of fabric/README.md (lines 42 and 43) shows the same lists, character for character, in the same order.

AC2 — Grep of README.md finds these names and labels:
- L346-349 (table rows): `timeline`, `no_remote`, `absent`, `desktop-scratch`
- L351: `wrapper` (not expected on unknown rows)
- L373-375: `local:(home)`, `local:(scratchpad)`, `local:(other)`
- L153 and L611 are pre-existing lines.

AC3 — `git diff --stat README.md fabric/README.md`: README.md 74 lines changed, fabric/README.md 8 lines changed (77 insertions, 5 deletions in total). The only deleted lines are the two lake grain bullets, the `export.py` bullet's old text, and the two old fabric column lists; every other change is an insertion. The full diff, unchanged:

```diff
diff --git a/README.md b/README.md
index f6211e7..bab4379 100644
--- a/README.md
+++ b/README.md
@@ -151,6 +151,7 @@ Shared:
   `python -m billing.otel.receiver` (`--host`, `--port`, `--db`, `--require-auth`)
 - **`transcript.py`** — (unchanged)
 - **`attribute.py`** — (unchanged)
+- **`project_label.py`** — turns one session's stored cwd history into a privacy-safe project-root label (`local:Dashnoard`) used only to explain `unknown` usage. Derived at query time from `session_repo_timeline`, never persisted, never a repo key. Read by `export.py`; see [Unattributed usage in the lake tables](#unattributed-usage-in-the-lake-tables).
 - **`otel_store.py`** — (unchanged)
@@ -163,7 +164,7 @@ Shared:
-- **`export.py`** — builds the two **running, all-history** lake tables (`claudeusagesummary`, `claudeusagelineitems`) from the store: flat single CSVs (no date-partition folders) with the usage month + `generated_at` as columns, regenerated in full each sync.
+- **`export.py`** — builds the two **running, all-history** lake tables (`claudeusagesummary`, `claudeusagelineitems`) from the store: flat single CSVs (no date-partition folders) with the usage month + `generated_at` as columns, regenerated in full each sync. Each table ends with two diagnostic columns, `attribution_source` and `unattributed_project`, filled only on `unknown` rows; those rows are additionally grained by the two columns, attributed rows keep their grain. Groups that collapse onto one row after model normalization or user-email coalescing are summed.
@@ -302,8 +303,13 @@
-  - `claudeusagesummary.csv` — one row per (usage date, repo/bill_name, user_email)
-  - `claudeusagelineitems.csv` — one row per (usage date, repo, model, user_email)
+  - `claudeusagesummary.csv` — one row per (usage date, repo/bill_name, user_email);
+    `unknown` rows additionally split by (`attribution_source`, `unattributed_project`)
+  - `claudeusagelineitems.csv` — one row per (usage date, repo, model, user_email);
+    `unknown` rows additionally split by (`attribution_source`, `unattributed_project`)
+
+  Rows billed to a real repo keep this grain exactly, and the two new columns
+  are blank on them.
@@ -328,6 +334,68 @@
   `ADLS_*`/`ONELAKE_*`, `AZURE_*`). Unset → invoices are written locally only.
 - **Runs where `otel.db` lives** (the receiver host); SQLite is single-host.
 
+### Unattributed usage in the lake tables
+
+Both tables end with two columns that explain `repo = unknown` rows. They are
+filled only on `unknown` rows and blank on rows billed to a real repo.
+
+**`attribution_source`** says why the usage is unattributed:
+
+| Value | Meaning |
+|---|---|
+| `timeline` | The repo hook fired, but the folder it reported has no git remote (a plain folder, an unzipped download, or a local repo with no `origin`). |
+| `no_remote` | No timeline rows; the launch-time wrapper tag was `unknown` because the launch directory had no git remote (a local repo with no remote counts). |
+| `absent` | No repo signal ever arrived: the hook is not installed or not firing, or the surface never ran the wrapper. |
+| `desktop-scratch` | Transcript-sourced usage (desktop app, and the cli / VS Code transcript backfill) with no billable repo. |
+
+`wrapper` is not expected on `unknown` rows: it only resolves to a real repo.
+
+**`unattributed_project`** names the project the developer was working in, as the
+root folder name only (`local:Dashnoard`). It is a hint for diagnosis, not a repo:
+it is never a repo key and never billed, and `resolved_repo`, invoices and
+`repo_name_map` are unaffected. The rule, in plain words:
+
+- One label per session, from that session's own cwd history. Cwds outside the
+  session's root still get the session's label.
+- The start of the path is the "outer zone": the home prefix (`C:\Users\<name>`,
+  `/home/<name>`, WSL `/mnt/c/...`, Git Bash `/c/...`) followed by any run of outer
+  folders (`OneDrive*`, `Desktop`, `Documents`, `Downloads`, `Library`,
+  `CloudStorage`, `Visual Studio *`) and container folders (`Code`, `src`, `source`,
+  `repos`, `projects`, `dev`, `git`, `GitHub`, `workspace`). The label is the first
+  folder after that zone, so `...\Code\Dashnoard` and
+  `...\Code\Dashnoard\OfficeDashboard\backend` both give `local:Dashnoard`, and
+  `...\source\repos\proj` gives `local:proj`.
+- Container folders inside a project point back to their parent
+  (`C:\Cyclotron\proj\src\components` gives `local:proj`). If the session's cwd
+  history visits a shallower folder on the same path, that folder is the root.
+- A folder directly inside the home folder is a valid label
+  (`C:\Users\<name>\orbit` gives `local:orbit`).
+- Special values: `local:(home)` when the session started in the outer zone with no
+  project folder; `local:(scratchpad)` for any Claude-internal folder (`.claude`,
+  `Temp\claude`); `local:(other)` when the folder name would still look like a path,
+  a `OneDrive*` name, a `C--` project slug, or the username (allowlist guard).
+- Never a full path, drive letter, `Users`/`home` or username. Derived at query time
+  from the stored timeline, so a late or corrected timeline relabels history
+  retroactively; nothing is persisted.
+
+Accepted mislabels: a session that visits a real ancestor folder outside the outer
+zone (e.g. `C:\Cyclotron`) takes that ancestor as its root, and a session that
+starts in a real repo and then works in a no-remote folder labels those `unknown`
+rows with the start folder's name. Known gaps, not fixed here: hook scratchpad
+detection for the project-slug layout, and cwd-based undercounting of work done in
+another repo by absolute path.
+
+**For Power BI / semantic-model owners:**
+
+- Row counts for `unknown` changed (one row per class and project). Sum tokens and
+  cost; don't count rows.
+- Filter unattributed usage with `repo = 'unknown' AND attribution_source <> ''`. A
+  real repo whose bill name happens to be `unknown` stays unsplit with a blank class.
+- Collision correction: the export now sums usage that collapses onto one row after
+  model normalization (`[1m]`, dated snapshots) or user-email coalescing, where it
+  previously kept only one group. Totals now match `invoice.py`, and some
+  historical Fabric totals rise on the next sync.
+
 ---
diff --git a/fabric/README.md b/fabric/README.md
@@ -39,8 +39,12 @@
-- **`claudeusagesummary`** — `usage_date_utc, period_start, period_end, bill_name, user_email, ... generated_at`
-- **`claudeusagelineitems`** — `usage_date_utc, period_start, period_end, bill_name, repo, model, ... generated_at`
+- **`claudeusagesummary`** — `usage_date_utc, period_start, period_end, repo, user_email, tokens, actual_cost_usd, markup, total_billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`
+- **`claudeusagelineitems`** — `usage_date_utc, period_start, period_end, repo, repo_key, model, user_email, tokens, actual_cost_usd, billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`
+
+`attribution_source` and `unattributed_project` are filled only on `repo = 'unknown'`
+rows; see "Unattributed usage in the lake tables" in the top-level
+[`README.md`](../README.md) for what they mean.
```
Note: unchanged context lines and the old fabric lists are abbreviated with "(unchanged)" or "..." in this printout. The real `git diff README.md fabric/README.md` output shows them in full.

### Notes for the evaluator
- I put the new material in a new "###" subsection at the end of the data-lake section, and linked the module bullet to it. That kept the insertions surgical and left existing headings alone.
- The mislabel caveat and "known gaps" sentence are in that subsection. The known gaps are named as not fixed.
- The goal.md Success Criteria say the export "SUMS" collisions. I documented that as the export.py behaviour without re-reading the export code beyond its field lists.
- I did not re-read the task 01 spec; the label rule comes from `project_label.py`, which I read.

### Footprint
files_read: 8 (~95000 chars: 11-context.md, 03-readme-columns.md, goal.md, project_label.py, fabric/README.md, and README.md and export.py and attribute.py in part)
commands_run: 2
