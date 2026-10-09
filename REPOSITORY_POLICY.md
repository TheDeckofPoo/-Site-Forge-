# Site Forge Repository Policy

## Authoritative repository

The only authoritative GitHub repository for Site Forge development is:

https://github.com/TheDeckofPoo/-Site-Forge-

All production development branches, candidate branches, analysis branches, fixes, qualification SHAs, tags, and future commits must be pushed here.

## Prohibited repository

Do not push Site Forge work to:

https://github.com/LPS-Engineering/Site-Forge

LPS-Engineering/Site-Forge is not an approved Site Forge development remote.

## Migration rule

Any Site Forge branch, commit, tag, or candidate that currently exists only in LPS-Engineering/Site-Forge must be copied into TheDeckofPoo/-Site-Forge- without deleting or rewriting existing TheDeckofPoo history.

Migration must be non-destructive:
- no `git push --mirror`
- no force-push unless Curtis explicitly authorizes a specific conflicting ref
- preserve exact commit SHAs when histories permit
- report any branch/tag conflict instead of overwriting it

After migration:
- verify every migrated branch head exists in TheDeckofPoo/-Site-Forge-
- verify important candidate SHAs are fetchable from TheDeckofPoo/-Site-Forge-
- set the normal development remote to TheDeckofPoo/-Site-Forge-
- remove or disable push access to the LPS remote locally

## Current project rule

Warden, Hunter, Patch, Relay, Anton, and any future agent must treat TheDeckofPoo/-Site-Forge- as the sole GitHub source of truth for Site Forge unless Curtis explicitly changes this policy.
