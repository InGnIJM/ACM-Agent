export const meta = {
  name: 'fix-atcoder-rendering',
  description: 'Fix AtCoder problem data loss: cleanMathJaxTriplication truncates constraints/output format. TDD backend fix (skip AtCoder + code-fence awareness + empty-math regex + camelCase alias) + python verify + data migration + adversarial verification.',
  phases: [
    { title: 'Fix', detail: 'backend TDD (extract util + 3 root causes + camelCase alias) + python behavior verify' },
    { title: 'Data Repair', detail: 'rebuild all atcoder fullContent from rawDetail via the shared util' },
    { title: 'Verify', detail: 'run all tests + adversarial CF/NowCoder regression + root-cause confirmation' },
  ],
}

// Verified facts (hardcoded — do NOT re-scout):
//   backend test:  cd backend && npm test            (jest; backend/test/crawler.controller.spec.ts + crawler.controller.leetcode.spec.ts already cover buildFullContent/cleanMathJax)
//   frontend test: cd frontend && npm test          (vitest run; frontend/test/components/Markdown.test.tsx exists)
//   python test:   cd python && PYTHONPATH=. python -m pytest crawlers/test/test_atcoder.py -q   (36 passed, 2 pre-existing failures unrelated to this bug)
//   crawler.controller.ts: buildFullContent at ~1129 (private), cleanMathJaxTriplication at ~1024, parseSampleString ~926, parseLeetCodeSamples ~955
//   DB: postgresql://postgres:jm050711@localhost:5432/acm_agent ; columns full_content, raw_detail, source_platform='atcoder' ; content_vector + solution_summary exist (will go stale after rebuild — report only)
//   3 atcoder rows:
//     1202Contest_a  (9df69f64) snake_case full schema  -> safe rebuild
//     1202Contest_b  (91ce445b) snake_case full schema  -> THE USER'S REPORTED PROBLEM; constraints "$1 \leq H \leq 20$\n$1 \leq W \leq 20$\n..." must survive
//     1202Contest_j  (003a656c) camelCase schema (inputFormat/outputFormat/timeLimit/memoryLimit/note/platformMeta) + NO constraints key -> rebuild will correctly omit [数据范围]; report that j needs a re-crawl to recover constraints

const BT = String.fromCharCode(96)
const FENCE = BT + BT + BT

const BACKEND_FACTS =
  'VERIFIED FACTS (do not re-investigate):\n' +
  '  - Repo root: E:\\code\\ACM-Agent\n' +
  '  - File: backend/src/crawler/crawler.controller.ts — buildFullContent() is a PRIVATE instance method at ~line 1129; it calls this.cleanMathJaxTriplication() (~1024), this.parseSampleString() (~926), this.parseLeetCodeSamples() (~955).\n' +
  '  - There are FOUR divergent copies of buildFullContent in the repo: this controller (authoritative), backend/src/crawler/import-problems.ts (STALE), backend/scripts/import-318732.ts (nowcoder-specific verbatim copy), backend/scripts/reimport-two-sum.ts (leetcode-specific verbatim copy). For THIS task only the controller matters; do NOT touch the scripts.\n' +
  '  - Tests: backend/test/crawler.controller.spec.ts and backend/test/crawler.controller.leetcode.spec.ts already import the controller and cover buildFullContent/cleanMathJax. EXTEND those — do not invent a new test file.\n' +
  '  - Run backend tests: cd backend && npm test   (jest). For a faster targeted run: cd backend && npx jest crawler.controller\n\n'

phase('Fix')
log('Fix phase: backend TDD (extract util + 3 root causes + camelCase alias) parallel with python behavior verify')

const [fixReport, pythonReport] = await parallel([
  () => agent(
    'Fix a data-loss bug in the ACM-Agent backend using STRICT TDD (Red -> Green). Repo: E:\\code\\ACM-Agent.\n\n' +
    BACKEND_FACTS +
    'ROOT CAUSE: buildFullContent() applies cleanMathJaxTriplication() to EVERY platform. AtCoder data is already clean $...$ KaTeX, so the dedup wrongly classifies constraint lines like "$1 \\leq H \\leq 20$" and short tokens "|", "or", "-", "." as a 3-copy math island and DELETES them. Verified: rawDetail.constraints for problem 1202Contest_b is COMPLETE ("$1 \\leq H \\leq 20$\\n$1 \\leq W \\leq 20$\\n$\\textrm{move}$ is either\\nFirst\\nor\\nSecond\\n, where\\nFirst\\nmeans...\\nSecond\\nmeans...") but the stored full_content is TRUNCATED to just the "$\\textrm{move}$ is either..." line. Output format also lost "|", "or", "-", "." tokens.\n\n' +
    'SCOPE OF EDITS (one agent, in order):\n' +
    'A) EXTRACT a shared pure module: create backend/src/crawler/fullcontent.util.ts exporting buildFullContent(platform: string, record: any): string. MOVE buildFullContent + the three helpers it depends on (cleanMathJaxTriplication, parseSampleString, parseLeetCodeSamples) into that module as non-method functions. The controller then delegates: its buildFullContent becomes a thin wrapper calling buildFullContent(platform, record) from the util (keep the existing private method signature so call sites and tests keep working). This extraction is REQUIRED so the data-migration script can reuse the exact same logic (the current 4 divergent copies are how this bug recurred).\n' +
    'B) FIX 1 — skip cleanMathJaxTriplication for atcoder (and luogu). In buildFullContent, route the cleaner through a platform gate, e.g.:\n' +
    '     const skipMathClean = platform === \'atcoder\' || platform === \'luogu\';\n' +
    '     const clean = (t) => (skipMathClean ? (t ?? \'\') : cleanMathJaxTriplication(t));\n' +
    '   Apply clean() to: record.background, the desc block, record.constraints, record.input_format, record.output_format, record.hint. Keep leetcode/codeforces/nowcoder on the real cleaner. Preserve the limits/desc prefix (time/memory) logic exactly.\n' +
    'C) FIX 2 — make cleanMathJaxTriplication() code-fence-aware (defense in depth). In its island-collection loop, track fenced code blocks: when a trimmed line starts with ' + FENCE + ' or ~~~, toggle an in-fence flag; while in-fence, push the line VERBATIM and skip math-fragment detection. This mirrors the frontend dedupMathJax() guard already in frontend/src/components/common/Markdown.tsx (around its isMathFragment island loop — it already checks starts-with-triple-backtick correctly). Read that frontend file and copy the guard pattern.\n' +
    'D) FIX 3 — fix over-aggressive empty-math regexes (currently ~1120-1121):\n' +
    '     .replace(/\\$\\$/g, \'\')\n' +
    '     .replace(/\\$ \\$/g, \'\')\n' +
    '   The second destroys adjacent inline math like "$H$ $W$" (it matches the middle "$ $"). Change BOTH to match ONLY a standalone empty delimiter occupying a whole line:\n' +
    '     .replace(/^\\s*\\$\\$\\s*$/gm, \'\')\n' +
    '     .replace(/^\\s*\\$\\s*\\$\\s*$/gm, \'\')\n' +
    '   Verify mentally: "$H$ $W$ $\\textrm{move}$" must survive UNTOUCHED.\n' +
    'E) FIX 4 — camelCase alias support (the 3rd atcoder row 1202Contest_j stores inputFormat/outputFormat/timeLimit/memoryLimit/note instead of snake_case). In buildFullContent, read BOTH spellings, e.g. record.input_format ?? record.inputFormat, record.output_format ?? record.outputFormat, and for limits prefer record.limits?.time ?? record.timeLimit ?? record.limits?.timeLimit (and the same for memory). This makes the util robust to the two crawler schemas without dropping sections.\n\n' +
    'TDD ORDER (mandatory):\n' +
    '1. Write FAILING tests in backend/test/crawler.controller.spec.ts (extend the existing file). Cover:\n' +
    '   (a) buildFullContent(\'atcoder\', {description, constraints: a multi-line "$1 \\leq H \\leq 20$\\n$1 \\leq W \\leq 20$\\n$\\textrm{move}$ is either\\nFirst\\nor\\nSecond\\n, where\\nFirst\\nmeans...\\nSecond\\nmeans...", input_format, output_format, samples}) -> result CONTAINS "$1 \\leq H \\leq 20$" AND "$1 \\leq W \\leq 20$" AND "First" AND "Second".\n' +
    '   (b) cleanMathJaxTriplication preserves a fenced code block (a line of triple-backtick, lines A_i / B_i / C_i, then triple-backtick) intact.\n' +
    '   (c) cleanMathJaxTriplication does NOT mangle "$H$ $W$ $\\textrm{move}$".\n' +
    '   (d) buildFullContent reads camelCase aliases (inputFormat/outputFormat/timeLimit/memoryLimit).\n' +
    '   (e) REGRESSION: codeforces-style triplication "p\\ni\\n\\n\\np\\ni\\n\\n\\np_i" still collapses to contain "p_i".\n' +
    '2. Run: cd backend && npx jest crawler.controller   -> confirm the NEW tests FAIL (Red). Read ALL output.\n' +
    '3. Implement A-E.\n' +
    '4. Run again: cd backend && npm test   -> confirm ALL green (Green). Then run cd backend && npx jest crawler.controller --coverage and report coverage of fullcontent.util.\n' +
    '5. Commit nothing. Report: every file changed (file:line), and paste the final test output tail (last ~30 lines) plus the coverage line for fullcontent.util.',
    { label: 'fix:backend', phase: 'Fix', effort: 'high' },
  ),
  () => agent(
    'Verify the Python AtCoder crawler needs NO change and harden its tests (regression armour). Repo: E:\\code\\ACM-Agent.\n\n' +
    'CONTEXT: The bug is purely backend (buildFullContent + cleanMathJaxTriplication). The Python crawler\'s rawDetail is CORRECT (verified complete for 1202Contest_a and _b). Root cause #4 (LaTeX inside code-fence blocks not rendering) is deliberately LEFT AS-IS per the user\'s decision — that is standard Markdown behaviour, NOT a bug. So do NOT change atcoder.py behaviour.\n\n' +
    'TASKS:\n' +
    '1. Read python/crawlers/atcoder.py _extract_sections() (~line 241) and confirm it correctly: (i) emits multi-line $...$ constraints verbatim, (ii) wraps <pre> in triple-backtick fenced code blocks (so input_format "$H$ $W$ $\\textrm{move}$" lands inside a fence). This is EXPECTED and correct — leave it.\n' +
    '2. Read python/crawlers/test/test_atcoder.py.\n' +
    '3. If a test asserting "_extract_sections preserves multi-line $...$ constraints verbatim" or "_extract_sections wraps input-format <pre> in a fenced code block containing $H$ $W$ $\\textrm{move}$" does NOT exist, ADD it (it should PASS against current code — this is regression armour, not Red->Green).\n' +
    '4. Run: cd python && PYTHONPATH=. python -m pytest crawlers/test/test_atcoder.py -q   — read ALL output — confirm 36 passed (the 2 pre-existing failures test_basic_success_with_all_enrichments and test_unparseable_source_id are UNRELATED to this work; do not touch them unless they are trivially caused by your new test).\n' +
    '5. Report what you added (file:line) and paste the test output tail. Commit nothing.',
    { label: 'fix:python-verify', phase: 'Fix', effort: 'medium' },
  ),
])
log('Fix done. backend:\n' + fixReport + '\n---\npython:\n' + pythonReport)

// ───────────────────────────────────────────────────────────
phase('Data Repair')
log('Rebuilding atcoder fullContent from rawDetail via the shared util (3 rows)')

const repairReport = await agent(
  'Rebuild the full_content column for ALL atcoder problems so they reflect the FIXED buildFullContent logic. Repo: E:\\code\\ACM-Agent.\n\n' +
  'The backend fix just extracted a shared pure module: backend/src/crawler/fullcontent.util.ts exporting buildFullContent(platform, record). Existing DB rows still hold OLD truncated full_content. raw_detail is the correct source data — REBUILD FROM IT (do NOT re-crawl AtCoder).\n\n' +
  'VERIFIED FACTS:\n' +
  '  - DB: postgresql://postgres:jm050711@localhost:5432/acm_agent ; columns full_content (TEXT), raw_detail (JSONB), source_platform=\'atcoder\'\n' +
  '  - 3 rows, two schemas:\n' +
  '      1202Contest_a  (9df69f64-104e-49fb-854b-02bef2e05cd9) snake_case full schema\n' +
  '      1202Contest_b  (91ce445b-60c2-4e45-b055-b578d4263f88) snake_case full schema  <- USER\'S REPORTED PROBLEM\n' +
  '      1202Contest_j  (003a656c-b0b4-44a6-b2e2-08b5436ce297) camelCase schema, NO constraints key\n' +
  '  - content_vector and solution_summary columns exist; after rebuild they become STALE — note this in your report but do NOT regenerate them here (out of scope).\n\n' +
  'TASKS:\n' +
  '1. Create backend/scripts/rebuild-atcoder-fullcontent.ts. It MUST:\n' +
  '   - import { buildFullContent } from the new ../src/crawler/fullcontent.util (use tsx/ts-node to run TS directly; see how backend/scripts/reimport-two-sum.ts is invoked).\n' +
  '   - SELECT id, source_id, raw_detail FROM problems WHERE source_platform=\'atcoder\' AND deleted_at IS NULL.\n' +
  '   - For each row: newFullContent = buildFullContent(\'atcoder\', rawDetail). UPDATE problems SET full_content=$1, updated_at=NOW() WHERE id=$2.\n' +
  '   - Support a --dry-run flag that prints before/after LENGTHS and the section markers present ([描述]/[输入]/[输出]/[数据范围]/[样例]) WITHOUT writing.\n' +
  '   - Be idempotent (safe to re-run).\n' +
  '   - Use the Prisma client the same way reimport-two-sum.ts does (init/disconnect), OR raw pg via a connection. Match the existing script style.\n' +
  '2. RUN --dry-run first, print the 1202Contest_b before/after, eyeball it (after MUST contain "$1 \\leq H \\leq 20$").\n' +
  '3. RUN for real. Confirm rows updated == 3.\n' +
  '4. EXPECTED per-row outcome:\n' +
  '   - _a and _b: [数据范围] section contains the full constraints incl. "$1 \\leq H \\leq 20$" and "$1 \\leq W \\leq 20$".\n' +
  '   - _j: has NO constraints key in raw_detail, so its rebuilt full_content will correctly OMIT [数据范围] — this is HONEST (do NOT fabricate constraints). Report that _j needs a separate re-crawl to recover its constraints (out of scope here).\n' +
  '5. Report: script path, run command, rows updated count, and the before/after evidence (paste the new [数据范围] and [输出] sections for 1202Contest_b). Commit nothing.',
  { label: 'repair:rebuild-atcoder', phase: 'Data Repair', effort: 'high' },
)
log('Data repair done:\n' + repairReport)

// ───────────────────────────────────────────────────────────
phase('Verify')
log('Verify phase: full test suite + CF/NowCoder regression + root-cause confirmation (parallel)')

const [testResult, regressionResult, rootResult] = await parallel([
  () => agent(
    'Run the FULL test suites for the ACM-Agent repo (E:\\code\\ACM-Agent) and report pass/fail. Read ALL output of each.\n\n' +
    'Run:\n' +
    '  - Backend:   cd backend && npm test\n' +
    '  - Python:    cd python && PYTHONPATH=. python -m pytest crawlers/test/test_atcoder.py -q\n' +
    '  - Frontend:  cd frontend && npm test   (vitest; if it needs a DB/server, still run it — the Markdown component tests are pure unit tests)\n\n' +
    'Paste the tail (~30 lines) of each suite. Report: allTestsPassed = true ONLY if backend+frontend are fully green AND python is 36 passed (the 2 pre-existing failures test_basic_success_with_all_enrichments / test_unparseable_source_id are acceptable ONLY IF they were already failing before this work — verify they are unrelated to the atcoder changes). concerns = any new failure with suite + test name.',
    { label: 'verify:tests', phase: 'Verify', effort: 'high' },
  ),
  () => agent(
    'Adversarial regression check for the ACM-Agent backend fix (E:\\code\\ACM-Agent).\n\n' +
    'The fix made cleanMathJaxTriplication() code-fence-aware and changed the empty-math delimiter regexes ($ $ and $$) to match only standalone lines. Verify the original PURPOSE still works: collapsing Codeforces / NowCoder MathJax triplication.\n\n' +
    'Extend backend/test/crawler.controller.spec.ts with focused assertions that cleanMathJaxTriplication (imported from fullcontent.util if exported, or tested via a codeforces buildFullContent call) STILL collapses:\n' +
    '  - "p\\ni\\n\\n\\np\\ni\\n\\n\\np_i"  -> result contains "p_i"\n' +
    '  - "1\\n\\n≤\\n\\nx\\n\\n1 \\le x\\n\\n."  -> collapses to a single best line containing "\\le"\n' +
    'AND now PRESERVES:\n' +
    '  - a fenced code block (a line of triple-backtick, lines A_i / B_i / C_i, then triple-backtick) -> 3 content lines intact\n' +
    '  - "$H$ $W$ $\\textrm{move}$" -> unchanged (the middle "$ $" is NOT stripped)\n\n' +
    'Run: cd backend && npx jest crawler.controller   Read ALL output. Report: regressionsFound = true if ANY collapse assertion fails; otherwise false with the test output tail.',
    { label: 'verify:regression', phase: 'Verify', effort: 'high' },
  ),
  () => agent(
    'Confirm the root cause is actually fixed on REAL data, end to end. Repo: E:\\code\\ACM-Agent.\n\n' +
    'Do NOT trust unit tests alone — verify against the live DB.\n' +
    '1. DB: postgresql://postgres:jm050711@localhost:5432/acm_agent. SELECT full_content FROM problems WHERE id=\'91ce445b-60c2-4e45-b055-b578d4263f88\' (1202Contest_b).\n' +
    '2. Assert full_content CONTAINS:\n' +
    '   - "$1 \\leq H \\leq 20$"  (was MISSING before the fix)\n' +
    '   - "$1 \\leq W \\leq 20$"  (was MISSING before the fix)\n' +
    '   - section markers [数据范围], [输入], [输出], [样例]\n' +
    '3. Count triple-backtick fence lines in full_content — must be EVEN (balanced). Confirm the [输出] section still contains the "|", "or", "-", "." tokens that were previously dropped.\n' +
    '4. Cross-check: fetch https://atcoder.jp/contests/DEGwer2023/tasks/1202Contest_b?lang=en and confirm the constraints now in the DB match the source (H<=20, W<=20, move is First/Second).\n\n' +
    'Report: rootCauseFixed = true only if all checks pass. Paste the actual [数据范围] and [输出] sections from the rebuilt full_content as rootCauseEvidence. Also explicitly state the fence-line count and whether | / - / or tokens are present.',
    { label: 'verify:rootcause', phase: 'Verify', effort: 'high' },
  ),
])

return {
  fix: { backend: fixReport, python: pythonReport },
  repair: repairReport,
  verify: { tests: testResult, regression: regressionResult, rootCause: rootResult },
}
