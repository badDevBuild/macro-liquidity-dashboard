# Security policy

Please do not open a public issue for a suspected vulnerability that could expose credentials, private data, or a production host.

Use GitHub's private vulnerability reporting for this repository. Include the affected file or endpoint, reproduction steps, impact, and any suggested mitigation. Do not include real API keys, cookies, SSH material, personal trading data, or copied production logs.

## Supported version

Security fixes are applied to the current `main` branch.

## Deployment boundary

This repository contains public source code and examples only. Operators are responsible for keeping runtime data, `.env` files, Keychain entries, Codex login state, SSH keys, `known_hosts`, and `config/production-deploy.json` outside version control.
