Invoke the `thedevkitchen-speckit-specify` subagent to generate a new feature specification (`specs/NNN-feature-name/spec-idea.md`), following this project's spec-kit convention (numbered `specs/NNN-feature-name/` directories, NNN = next sequential number), the project's ADRs, knowledge base, and multi-tenancy/security standards — including an explicit performance analysis (indexing, N+1 risk, caching, async offload).

This spec is meant to run **before** `superpowers:brainstorming`/`superpowers:writing-plans`, not after — its output is the grounded context those skills use once the spec is approved. Don't brainstorm the approach first; run this command to establish requirements, then brainstorm/plan only if an open design question remains.

Pass any argument provided by the user directly to the agent as the initial feature description or scope. If no argument is provided, the agent will ask the user interactively (MVP scope, solution type — API only / Odoo UI only / Both, primary goal, roles, user stories, data model, endpoints, testing requirements).

$ARGUMENTS
