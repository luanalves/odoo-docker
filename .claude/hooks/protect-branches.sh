#!/usr/bin/env bash
# PreToolUse hook (Bash) — força confirmação manual antes de git push/merge
# que atinja as branches protegidas develop/master.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
[ -z "$cmd" ] && exit 0

is_protected() {
    case "$1" in
        develop|master) return 0 ;;
        *) return 1 ;;
    esac
}

current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || true
}

branch=""

if echo "$cmd" | grep -Eq '(^|;|&&|\|)[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
    # isola os argumentos depois de "git push"
    args="$(echo "$cmd" | sed -E 's/^.*git[[:space:]]+push([[:space:]]|$)//')"
    positional=()
    for tok in $args; do
        case "$tok" in
            -*) continue ;;
        esac
        case "$tok" in
            \;*|\&\&*|\|*) break ;;
        esac
        positional+=("$tok")
    done
    # positional[0] = remote (opcional), positional[1] = branch/ref (opcional)
    ref="${positional[1]:-}"

    if [ -z "$ref" ] || [ "$ref" = "HEAD" ]; then
        # sem ref explícita (ou HEAD): push vai para a branch atual
        cur="$(current_branch)"
        if is_protected "$cur"; then
            branch="$cur"
        fi
    else
        # ref pode vir como "local:remoto" — avalia o lado remoto
        remote_ref="${ref#*:}"
        if is_protected "$remote_ref"; then
            branch="$remote_ref"
        fi
    fi
elif echo "$cmd" | grep -Eq '(^|;|&&|\|)[[:space:]]*git[[:space:]]+merge([[:space:]]|$)'; then
    # merge sempre afeta a branch atual (checked out)
    cur="$(current_branch)"
    if is_protected "$cur"; then
        branch="$cur"
    fi
fi

if [ -n "$branch" ]; then
    reason="Push/merge para a branch protegida '$branch' requer confirmação manual do usuário."
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":%s}}' \
        "$(printf '%s' "$reason" | jq -Rs .)"
fi

exit 0
