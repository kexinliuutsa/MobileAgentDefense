# Double-anonymous release checklist

**Venue policy takes precedence.** Some conferences allow anonymized source links, some permit only supplementary ZIPs, and some have artifact-specific rules. Confirm the requirements for your actual conference and submission stage.

## Before any public push

- Publish a **clean export without old Git history**, not a fork of your identity-linked experimental repository. Avoid publishing from a personally identifiable account if it makes the venue's anonymity expectations difficult to meet.
- Review every filename, code comment, Markdown file, Python path, Git remote, notebook output, binary, EXIF, screenshot, log, result, and document for identifying details.
- Never commit API keys, `.env`, `.git/config` copied from another project, ADB device IDs, home directory paths, service credentials, internal server hostnames, or private screenshots and datasets.
- Never commit third-party models, commercial API SDKs, apps, or dataset assets until distribution rights are confirmed.
- For each new commit, inspect `git log --format=fuller` and `git show --stat`; local `user.name` / `user.email` and pushed GitHub account association are separate privacy surfaces.
- Run `python3 scripts/check_release.py`, optionally with one or more `--term 'PRIVATE_IDENTIFIER'` arguments. It catches only common patterns; it does not guarantee anonymization.
- Inspect all third-party dependencies, licenses, reproducing environment, and acknowledgments; conference policy governs what to redact during review.
- After clean review, choose a code license and add it as a new file (only if entitled to license every included component).

## Anonymous GitHub vs. distinct anonymous repository

[Anonymous GitHub](https://anonymous.4open.science/) creates a **read-only anonymized mirror** from a GitHub repository; it supports configurable term redaction and can refresh source updates. It should not be mistaken for removal of sensitive contents: **images and PDFs can remain unchanged**, and replaced terms inside executable source can break code. Check the final mirror as a reviewer would.

A separate anonymous publication account or venue-provided ZIP alternative may reduce linkability, but obey GitHub terms and the conference's policy. If the original source is public, it can still be identified by searching distinctive code, names, data or earlier commits. No service gives perfect anonymity.

Don't link a personal upstream repo, personal social profile, ORCID, university page, or prior public issue/PR from the paper artifact.

## Never reuse a contaminated history

Removing files from GitHub HEAD does **not** erase previously published commits, forks or caches. Rotate any leaked token immediately. See GitHub's official docs: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository

## After acceptance

Release the full reproducibility artifact, attribution, license and long-lived repository/DOI according to venue policy. Document exact evaluated binary hashes, versions, and environment separately from the anonymous review artifact.
