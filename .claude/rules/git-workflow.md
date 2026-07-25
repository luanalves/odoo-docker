# Git Workflow Rules

**Never `git push` or `git merge` into the `develop` or `master` branches without first asking the user for explicit confirmation** — even if a prior instruction in the same session approved a push/merge once. Feature work happens on other branches; landing on `develop`/`master` is a deliberate, user-approved step (PR merge, release, hotfix), not a routine one.
