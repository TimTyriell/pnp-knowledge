# PreToolUse guard: the repo's must-hold rules, enforced instead of requested.
#
# docs/plans/README.md used to ask agents, in prose, not to call DeepSeek, not
# to hand-edit the bundle and not to bump a prompt version. Prose is advisory;
# a hook is not. Exit 2 blocks the tool call and hands the message to Claude.
# ADR-005 explains which rules live here and which stay in REVIEW.md.
#
# Each rule has a named env override for the human, set before starting Claude:
#   PNP_ALLOW_PAID=1          paid pnp runs and prompt-version bumps
#   PNP_ALLOW_BUNDLE_EDIT=1   hand edits under knowledge/ (a plan says so)
#   PNP_ALLOW_MAIN_COMMIT=1   committing directly on main
#   PNP_ALLOW_GUARD_EDIT=1    editing .claude/hooks/ or .claude/settings.json
# graph/ has no override: it is frozen (ADR-002); thaw it by editing this file.
# Path rules see the Edit/Write tools, not shell writes (`>`, Set-Content);
# review covers that gap (ADR-005).

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
try { $hook = [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { exit 0 }
$in = $hook.tool_input
$cwd = if ($hook.cwd) { $hook.cwd } else { (Get-Location).Path }

function Block([string]$why) {
    [Console]::Error.WriteLine("Blocked by $repo\.claude\hooks\guard.ps1: $why")
    exit 2
}

# Path of $p relative to this repo, '/'-separated, or $null when outside it.
function RepoRel([string]$p) {
    if (-not $p) { return $null }
    if (-not [IO.Path]::IsPathRooted($p)) { $p = Join-Path $cwd $p }
    $full = [IO.Path]::GetFullPath($p)
    if (-not $full.StartsWith("$repo\", 'OrdinalIgnoreCase')) { return $null }
    return $full.Substring($repo.Length + 1) -replace '\\', '/'
}

if ($hook.tool_name -in 'Edit', 'Write', 'MultiEdit', 'NotebookEdit') {
    $file = if ($in.file_path) { $in.file_path } else { $in.notebook_path }
    $rel = RepoRel $file
    if (-not $rel) { exit 0 }

    if ($rel -match '^\.claude/(hooks/|settings(\.local)?\.json$)' -and $env:PNP_ALLOW_GUARD_EDIT -ne '1') {
        Block "the guards protect themselves: .claude/hooks/ and .claude/settings.json are the human's to change. Override: PNP_ALLOW_GUARD_EDIT=1."
    }
    if ($rel -like 'graph/*') {
        Block "graph/ is frozen (ADR-002). Reference only, no edits."
    }
    if ($rel -like 'knowledge/*' -and $rel -ne 'knowledge/entity_rules.yaml' -and $env:PNP_ALLOW_BUNDLE_EDIT -ne '1') {
        Block "knowledge/ is written by 'pnp run', not by hand (only knowledge/entity_rules.yaml is hand-written). Override: PNP_ALLOW_BUNDLE_EDIT=1."
    }

    # A *_PROMPT_VERSION change re-extracts the corpus (~$6.50) and renames
    # concept ids (PIPELINE.md sections 4 and 6). Only an existing assignment
    # whose value changes counts; new files and unrelated edits pass.
    $full = Join-Path $repo $rel
    if ((Test-Path $full) -and $env:PNP_ALLOW_PAID -ne '1') {
        $new = (@($in.new_string, $in.content) + @($in.edits | ForEach-Object { $_.new_string })) -join "`n"
        $old = Get-Content -Raw $full
        foreach ($m in [regex]::Matches($new, '(?m)^\s*(\w*PROMPT_VERSION)\s*=\s*(.+?)\s*$')) {
            $cur = [regex]::Match($old, "(?m)^\s*$($m.Groups[1].Value)\s*=\s*(.+?)\s*$")
            if ($cur.Success -and $cur.Groups[1].Value -ne $m.Groups[2].Value) {
                Block "$($m.Groups[1].Value) bump re-extracts the whole corpus (~`$6.50) and renames concept ids. Human decision. Override: PNP_ALLOW_PAID=1."
            }
        }
    }
    exit 0
}

if ($hook.tool_name -in 'Bash', 'PowerShell') {
    $cmd = [string]$in.command
    # Command position: start, or after a separator / env assignment / path.
    $at = '(?m)(^|[;&|(]\s*|\n\s*)(\w+=\S*\s+)*(\S*[\\/])?'
    # Rules about *running* something scan the whole command, so wrappers
    # (`uv run`, `timeout`, `bash -c "..."`) can't hide a call. Text that is only
    # a message is cut first: heredoc bodies and -m/--message/--body/--title.
    $scan = [regex]::Replace($cmd, '(?s)<<-?\s*[''"]?(\w+)[''"]?.*?\n\s*\1\b', '')
    $scan = [regex]::Replace($scan, '(-m|--message|--body|--title)\s+("[^"]*"|''[^'']*'')', '')

    # run/state accept --estimate (free). --no-api (D1 agent mode) is free on
    # every command: the CLI refuses it unless every step model is `agent:`,
    # so no DeepSeek call can happen.
    if ($env:PNP_ALLOW_PAID -ne '1' -and
        $scan -match '\b(pnp(\.exe)?|pnp_okf\.cli)\s+((run|state)\b(?![^\n;&|]*--(estimate|no-api))|(extract|dedup)\b(?![^\n;&|]*--no-api))' -and
        $scan -notmatch '--help|\s-h\b') {
        Block "'pnp run/extract/state/dedup' call DeepSeek and cost money. Run with --estimate first; the human runs the paid step. Override: PNP_ALLOW_PAID=1."
    }

    # Several sessions share this checkout and its index (an A7 commit once
    # landed on another session's branch). Commits belong on a branch, made
    # from a worktree.
    $c = [regex]::Match($cmd, "$at" + 'git\s+(-C\s+("[^"]+"|''[^'']+''|\S+)\s+)?commit\b')
    if ($c.Success -and $env:PNP_ALLOW_MAIN_COMMIT -ne '1') {
        $dir = $cwd
        $cd = [regex]::Matches($cmd.Substring(0, $c.Index), '(?m)(^|[;&|(]\s*)cd\s+("[^"]+"|''[^'']+''|\S+)')
        if ($cd.Count) { $dir = [IO.Path]::Combine($dir, $cd[$cd.Count - 1].Groups[2].Value.Trim('"', "'")) }
        if ($c.Groups[5].Success) { $dir = [IO.Path]::Combine($dir, $c.Groups[5].Value.Trim('"', "'")) }
        $top = git -C $dir rev-parse --show-toplevel 2>$null
        if ($top -and [IO.Path]::GetFullPath($top) -eq $repo -and (git -C $dir branch --show-current) -eq 'main') {
            Block "commit on main. Branch first, from a worktree: git worktree add -b <branch> <dir> origin/main. Override: PNP_ALLOW_MAIN_COMMIT=1."
        }
    }
}
exit 0
