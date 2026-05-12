#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_DIR="/tmp/video-to-essay-autodeploy-$(id -u).lock"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*"
}

acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_DIR/pid"
        trap 'rm -rf "$LOCK_DIR"' EXIT
        return 0
    fi

    if [ -f "$LOCK_DIR/pid" ]; then
        local pid
        pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log "another autodeploy run is already active (pid $pid); skipping"
            exit 0
        fi
    fi

    log "removing stale lock"
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR"
    echo "$$" > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR"' EXIT
}

ensure_clean_worktree() {
    if [ -n "$(git status --porcelain)" ]; then
        log "worktree has local changes; skipping deploy"
        git status --short
        exit 0
    fi
}

current_upstream() {
    git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null
}

main() {
    acquire_lock

    cd "$INSTALL_DIR"
    log "checking for updates in $INSTALL_DIR"

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log "not a git worktree; skipping"
        exit 0
    fi

    ensure_clean_worktree

    local branch upstream local_sha remote_sha merge_base
    branch="$(git symbolic-ref --quiet --short HEAD || true)"
    if [ -z "$branch" ]; then
        log "repository is in detached HEAD state; skipping"
        exit 0
    fi

    upstream="$(current_upstream || true)"
    if [ -z "$upstream" ]; then
        log "branch $branch has no upstream; skipping"
        exit 0
    fi

    log "fetching $upstream"
    git fetch --prune

    local_sha="$(git rev-parse HEAD)"
    remote_sha="$(git rev-parse '@{u}')"

    if [ "$local_sha" = "$remote_sha" ]; then
        log "already up to date ($local_sha)"
        exit 0
    fi

    merge_base="$(git merge-base HEAD '@{u}')"
    if [ "$merge_base" != "$local_sha" ]; then
        log "local branch has commits not in $upstream; skipping auto-pull"
        log "local=$local_sha remote=$remote_sha merge_base=$merge_base"
        exit 0
    fi

    log "new commit available: $local_sha -> $remote_sha"
    git pull --ff-only

    log "redeploying workers via deploy/macos/setup.sh"
    bash "$INSTALL_DIR/deploy/macos/setup.sh"
    log "redeploy complete at $(git rev-parse HEAD)"
}

main "$@"
