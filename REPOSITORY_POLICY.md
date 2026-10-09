# Site Forge Repository Policy

## Authoritative development repository

The only authoritative GitHub repository for active Site Forge development is:

https://github.com/TheDeckofPoo/-Site-Forge-

All active development branches, candidate branches, analysis branches, fixes, qualification SHAs, tags, and future engineering commits must be pushed here unless Curtis explicitly changes this policy.

## LPS Engineering repository purpose

The repository:

https://github.com/LPS-Engineering/Site-Forge

is reserved for future company visibility / presentation when Curtis decides Site Forge is ready.

It is NOT currently an active development remote and must not receive new development work, candidate branches, qualification branches, or experimental commits.

Do not publish or sync new Site Forge work there until Curtis explicitly authorizes a visibility release or mirror.

## Migration rule for existing work

Any Site Forge branch, commit, tag, or candidate that currently exists only in LPS-Engineering/Site-Forge must be copied into TheDeckofPoo/-Site-Forge- without deleting or rewriting existing TheDeckofPoo history.

Migration must be non-destructive:
- no `git push --mirror`
- no force-push unless Curtis explicitly authorizes a specific conflicting ref
- preserve exact commit SHAs when histories permit
- report any branch/tag conflict instead of overwriting it

After migration:
- verify every migrated development branch head exists in TheDeckofPoo/-Site-Forge-
- verify important candidate SHAs are fetchable from TheDeckofPoo/-Site-Forge-
- set the normal development remote to TheDeckofPoo/-Site-Forge-
- remove or disable push access to the LPS remote locally for routine development

Do not delete or rewrite the LPS repository as part of this migration. It may later be used as a curated company-visibility repository when Curtis explicitly approves publication.

## Current project rule

Warden, Hunter, Patch, Relay, Anton, and any future agent must treat TheDeckofPoo/-Site-Forge- as the sole source of truth for active Site Forge development.

LPS-Engineering/Site-Forge is visibility-only and inactive until Curtis explicitly authorizes publication there.
