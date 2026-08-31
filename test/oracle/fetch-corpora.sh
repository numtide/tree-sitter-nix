#!/bin/sh
# Fetch the reference corpora pinned in corpora.lock into $CORPORA_DIR.
#
# Environment:
#   CORPORA_DIR   destination root (default: test/oracle/corpora, gitignored).
#                 Layout: $CORPORA_DIR/<NAME>/<SUBDIR>/... plus a
#                 $CORPORA_DIR/<NAME>/.corpus-rev marker; a corpus whose
#                 marker already matches the lock is left alone (idempotent).
#                 A $CORPORA_DIR/<NAME> that is a symlink is also left alone:
#                 that is how a sandboxed build (flake check) pre-populates
#                 the corpora from its own inputs.
#   NIX_SRC, RNIX_SRC, SNIX_SRC
#                 existing checkouts of the upstream repos (e.g. the audit's
#                 clones). When set, $CORPORA_DIR/<NAME> becomes a symlink to
#                 that directory and nothing is downloaded for it.
#   GIT, GH, CURL, TAR
#                 tool overrides (defaults: git, gh, curl, tar).
#   FETCH_VERBOSE set to 1 to see the underlying git/gh/curl errors (by
#                 default a failed strategy is silent and the next one runs).
#
# Fetch strategy per corpus, first one that works wins:
#   1. git: blobless, depth-1 fetch of the pinned SHA + sparse checkout of the
#      subdirs (works for any host that serves reachable SHAs; GitHub and
#      Forgejo do).
#   2. tarball of the SHA: for github.com `gh api .../tarball/<rev>` when gh
#      is installed and authenticated (survives ssh url rewrites), else curl
#      of /archive/<rev>.tar.gz; for other hosts the Forgejo/Gitea API
#      (/api/v1/repos/<owner>/<repo>/archive/<rev>.tar.gz — the web
#      /archive/<rev>.tar.gz URL is 404 on git.snix.dev), then the web URL.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
lock="$here/corpora.lock"
CORPORA_DIR=${CORPORA_DIR:-$here/corpora}
GIT=${GIT:-git}
GH=${GH:-gh}
CURL=${CURL:-curl}
TAR=${TAR:-tar}
if [ "${FETCH_VERBOSE:-0}" = 1 ]; then quiet=/dev/stderr; else quiet=/dev/null; fi

# shellcheck disable=SC1090
. "$lock"

log() { printf '%s\n' "fetch-corpora: $*" >&2; }

# copy_subdirs SRC DEST SUBDIRS — copy only the pinned subdirs.
copy_subdirs() {
  for sub in $3; do
    [ -d "$1/$sub" ] || { log "missing $sub in fetched tree"; return 1; }
    mkdir -p "$2/$(dirname "$sub")"
    cp -R "$1/$sub" "$2/$sub"
  done
}

fetch_git() { # url rev subdirs dest
  work=$(mktemp -d "$CORPORA_DIR/.git-XXXXXX")
  ok=0
  # shellcheck disable=SC2046  # the unquoted $(...) is intended: one sparse-checkout pattern per subdir
  if {
    $GIT -C "$work" init -q &&
      $GIT -C "$work" remote add origin "$1" &&
      $GIT -C "$work" fetch -q --depth 1 --filter=blob:none origin "$2" &&
      $GIT -C "$work" sparse-checkout set --no-cone $(for s in $3; do printf '/%s/ ' "$s"; done) &&
      $GIT -C "$work" checkout -q FETCH_HEAD
  } 2>"$quiet" && copy_subdirs "$work" "$4" "$3"; then
    ok=1
  fi
  rm -rf "$work"
  [ $ok = 1 ]
}

fetch_tarball() { # url rev subdirs dest
  work=$(mktemp -d "$CORPORA_DIR/.tar-XXXXXX")
  ok=0
  base=${1%.git}
  case "$base" in
    https://github.com/*)
      # an installed but unauthenticated gh (GitHub-hosted runners without
      # GH_TOKEN) exits 4; fall through to curl instead of giving up
      repo=${base#https://github.com/}
      { command -v "$GH" >/dev/null 2>&1 && $GH api "repos/$repo/tarball/$2" >"$work/src.tgz" 2>"$quiet"; } ||
        $CURL -fsSL "$base/archive/$2.tar.gz" -o "$work/src.tgz" 2>"$quiet" || :
      ;;
    *)
      host=${base%/*/*}; repo=${base#"$host"/}
      $CURL -fsSL "$host/api/v1/repos/$repo/archive/$2.tar.gz" -o "$work/src.tgz" 2>"$quiet" ||
        $CURL -fsSL "$base/archive/$2.tar.gz" -o "$work/src.tgz" 2>"$quiet" || : ;;
  esac
  if [ -s "$work/src.tgz" ] &&
    mkdir "$work/x" &&
    $TAR -xzf "$work/src.tgz" -C "$work/x" &&
    top=$(ls "$work/x") && [ -n "$top" ] &&
    copy_subdirs "$work/x/$top" "$4" "$3"; then
    ok=1
  fi
  rm -rf "$work"
  [ $ok = 1 ]
}

corpus() { # name url rev subdirs override
  dest="$CORPORA_DIR/$1"
  if [ -n "$5" ]; then
    [ -d "$5" ] || { log "override for $1 does not exist: $5"; exit 1; }
    rm -rf "$dest"
    ln -s "$(cd "$5" && pwd)" "$dest"
    log "$1: using $5 (env override)"
    return
  fi
  if [ -L "$dest" ]; then
    log "$1: $dest is a symlink, leaving it alone"
    return
  fi
  if [ -f "$dest/.corpus-rev" ] && [ "$(cat "$dest/.corpus-rev")" = "$3" ]; then
    log "$1: already at $3"
    return
  fi
  rm -rf "$dest"
  tmp="$CORPORA_DIR/.new-$1"
  rm -rf "$tmp"
  mkdir -p "$tmp"
  if fetch_git "$2" "$3" "$4" "$tmp"; then
    how=git
  elif fetch_tarball "$2" "$3" "$4" "$tmp"; then
    how=tarball
  else
    rm -rf "$tmp"
    log "$1: could not fetch $2 @ $3 (git and tarball both failed; FETCH_VERBOSE=1 shows why)"
    exit 1
  fi
  printf '%s\n' "$3" >"$tmp/.corpus-rev"
  mv "$tmp" "$dest"
  log "$1: fetched $3 via $how"
}

mkdir -p "$CORPORA_DIR"
corpus "$NIX_NAME" "$NIX_URL" "$NIX_REV" "$NIX_SUBDIRS" "${NIX_SRC:-}"
corpus "$RNIX_NAME" "$RNIX_URL" "$RNIX_REV" "$RNIX_SUBDIRS" "${RNIX_SRC:-}"
corpus "$SNIX_NAME" "$SNIX_URL" "$SNIX_REV" "$SNIX_SUBDIRS" "${SNIX_SRC:-}"
log "done: $CORPORA_DIR"
