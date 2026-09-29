**Model (self-reported)**: claude-opus-5-5
## Verdict: NEEDS FIXES
VERDICT: NEEDS FIXES
**Score**: 3/5
**failure_class:** implementation

The task is nearly complete: field lists, class table, Power BI note, collision note, grain lines and write fence all check out. One claim fails: the README states a general walk-up rule for `unattributed_project`, and `project_label.py` does not follow it when the outer zone has no container folder. The README is the ground truth and the requirement names the walk-up rule, so this cannot be minor.

### What I verified
- AC1: fabric/README.md column lists equal `export.SUMMARY_FIELDS` / `export.LINE_FIELDS`, in order → ✅ Verified. I printed both lists from `billing.otel.export`, regex-parsed fabric/README.md lines 42–43 and compared the lists: `summary match: True`, `line match: True`. The drift is fixed (`bill_name` → `repo`; `bill_name, repo` → `repo, repo_key`).
- fabric/README.md pointer sentence to the top-level README → ✅ Verified (diff +`attribution_source` and `unattributed_project` are filled only on `repo = 'unknown'` rows; see ...).
- AC2: all five class names each have a meaning, and the special labels are present → ✅ Verified. grep: README.md:346–349 (`timeline`, `no_remote`, `absent`, `desktop-scratch`), :351 (`wrapper` not expected), :373–375 (`local:(home)`, `local:(scratchpad)`, `local:(other)`).
- The class wording matches the task's dictated text and the attribute.py:28-45,88-94 CASE order → ✅ Verified. The `wrapper` branch needs `repo != 'unknown'`, so "not expected on unknown rows" is correct.
- AC3: no unrelated lines changed → ✅ Verified. `git diff --stat`: README.md 74 (+71/−3), fabric/README.md 8 (+6/−2). I read the full real diff. The only deletions are the two lake grain bullets, the old `export.py` bullet and the two fabric lists. The rest are insertions (a `project_label.py` bullet, a new `###` subsection). Headings are unchanged.
- Lake-table bullets and the `export.py` bullet mention the extra grain for unknown rows, and attributed rows keep their grain → ✅ Verified against export.py:91–99,129. `src`/`label` are non-empty only when `resolved_repo == 'unknown'`.
- Power BI filter `repo = 'unknown' AND attribution_source <> ''`, and "a real repo whose bill name is unknown stays unsplit" → ✅ Verified. The split keys on `resolved_repo` (repo key), while `repo` is `name_of(repo_key)` (export.py:95,120).
- Collision correction (sums after normalize_model and user coalescing; totals match invoice.py) → ✅ Verified at code level. export.py:96–97,104,109 sum into keys after `normalize_model` and `or UNKNOWN_USER`. invoice.py:86–99 also sums per `(repo, normalize_model(model))`. No test proves equality yet (that is task 04).
- Module list: `project_label.py` bullet sits next to `attribute.py` (README:154), and the anchor link target heading exists → ✅ Verified.
- README label examples produce the stated labels (I ran `root_label` on a placeholder user `zz`) → ✅ Verified for every example given: `...\Code\Dashnoard` and `...\Code\Dashnoard\OfficeDashboard\backend` → `local:Dashnoard`; `...\source\repos\proj` → `local:proj`; `C:\Cyclotron\proj\src\components` → `local:proj`; `C:\Users\<name>\orbit` → `local:orbit`; home/OneDrive root → `local:(home)`; `.claude\projects\C--...` and `Temp\claude\...` → `local:(scratchpad)`; folder = username or `C--` slug → `local:(other)`; accepted mislabel `C:\Cyclotron\proj` + visit `C:\Cyclotron` → `local:Cyclotron`; outside-root cwd keeps the session label. WSL and Git Bash forms of the Dashnoard path also give `local:Dashnoard`.
- General statement "The label is the first folder after that zone" (README ~L381–382) → ❌ Contradicted. I ran:
  - `C:\Users\zz\Documents\foo\bar` → `local:bar` (the README rule gives `local:foo`)
  - `C:\Users\zz\OneDrive - Cyclotron Inc\Clients\Acme\backend` → `local:backend` (README: `local:Clients`)
  - `C:\Cyclotron\proj\sub\deeper` → `local:deeper`
  - Sumit shape `C:\Cyclotron\Insights Agent\ai-presales-agent-main\ai-presales-agent-main` → `local:ai-presales-agent-main` (README: `local:Cyclotron`)

  In project_label.py:129–146 the outer-zone index `o` is a candidate only when `has_container` is true. Otherwise the label is the start folder, walked up only to the parent of an in-project container or to the shallowest visited cwd on the same path.
- Privacy: no real person's name, username or full path → ✅ Verified. grep for derek/sumit/mcconnell/bhatia/zanec/ZaneChing in both READMEs found nothing. Paths use `<name>`. `Dashnoard`/`orbit` are folder names, not usernames.
- Out-of-scope follow-ups are described as not done → ✅ Verified ("Known gaps, not fixed here: ..."). `cost_source` is not mentioned.
- Write fence → ✅ Verified. `git status --short` shows only README.md and fabric/README.md besides the pre-existing dirty files. By mtime, export.py (11:46) and project_label.py (11:42) predate 11-context.md (13:24), and client-package.zip is dated 09-25. The READMEs are dated 13:24:46, inside the run window. The fence was delivered in 11-context per the report.
- Test evidence (docs task; README-reading tests) → ✅ `python -m pytest tests/test_cli_backfill.py -k "ac05 or ac06"`: 4 passed. `python -m pytest tests/test_export.py -q`: 6 passed.
- Auto-fail triggers: none fired (docs only; no secrets, no code changes).

### Issues found
1. **[major]** README.md ~L381–384 — The line "The label is the first folder after that zone, so `...\Code\Dashnoard` and ..." states a general rule that the code follows only when the outer zone contains a container folder (`Code`, `src`, `source`, ...). With no container in the outer zone, the label is the start folder unless an in-project container or a shallower visited cwd walks it up. Two readings follow from this:
   - `...\Documents\foo\bar` gives `local:bar`, not `local:foo`.
   - The goal's own Sumit example gives `local:ai-presales-agent-main`. Under the README rule it would be `local:Cyclotron`.

   This is the "walk-up rule (outer vs in-project containers)" that the requirement names. README is ground truth, and Power BI owners will misread labels. This is not minor because a requirement names it.
2. **[minor]** README.md ~L366–367 ("They are filled only on `unknown` rows...") and fabric/README.md — Neither says that `unattributed_project` is also blank on many unknown rows. That covers every `no_remote`/`absent` row (those sessions have no timeline, so no label) and any session whose label is "". Minor because it is non-normative prose that no requirement names, and the sentence is not false.
3. **[minor]** README.md ~L376–377 (`local:(other)` guard) — The list omits some guard triggers: a leading `.`, the `-Users-` slug form, control characters, and a bare `Users`/`home`. It also says "a `OneDrive*` name" where the code matches `onedrive` anywhere in the name. Minor: "would still look like a path" covers most of this, and the requirement asks only for "(allowlist guard)".
4. **[minor]** README.md ~L378–379 — WSL `/mnt/c/...` and Git Bash `/c/...` are listed as home prefixes. In the code they are drive prefixes, stripped before the `Users\<name>` home check (a `/mnt/c/Cyclotron/proj` start has no home zone). `/root` and `~` are also home forms and are not mentioned. Minor wording: the examples still resolve correctly.

### Notes (non-blocking)
- Issues 2–4 above are minor. They are listed here so they are not dropped.
- The implementer's report says it did not re-read task 01's Definitions. Issue 1 is the kind of gap that caused.

### Required fixes (if NEEDS FIXES)
- [ ] README.md: replace
  "`repos`, `projects`, `dev`, `git`, `GitHub`, `workspace`). The label is the first folder after that zone, so `...\Code\Dashnoard` and `...\Code\Dashnoard\OfficeDashboard\backend` both give `local:Dashnoard`, and `...\source\repos\proj` gives `local:proj`."

  with wording that matches project_label.py:129–146, for example:

  "`...`workspace`). When that zone includes a container folder, the label is the first folder after it, so `...\Code\Dashnoard` and `...\Code\Dashnoard\OfficeDashboard\backend` both give `local:Dashnoard`, and `...\source\repos\proj` gives `local:proj`. Otherwise the label is the session's start folder, walked up only by the two rules below (so `...\Documents\foo\bar` gives `local:bar`, and `C:\Cyclotron\Insights Agent\ai-presales-agent-main\ai-presales-agent-main` gives `local:ai-presales-agent-main`)."

  Keep the next bullet (in-project containers → parent; shallower visited folder is the root) as "the two rules below". Run each new example through `billing.otel.project_label.root_label` before shipping.
- [ ] (Optional, clears the minor notes) After "They are filled only on `unknown` rows", add: "`unattributed_project` is also blank on unknown rows whose session has no timeline (always for `no_remote` and `absent`)". Extend the `local:(other)` list with "starts with `.`". Describe `/mnt/c` and `/c` as drive prefixes before `Users\<name>`.

### Footprint
files_read: 10 (~62000 chars: 12-context.md, 03-readme-columns.md, 11-report.md, goal.md, task-criteria SKILL.md, project_label.py, export.py, attribute.py (head), test_cli_backfill.py (excerpt), README/fabric diffs)
commands_run: 8
