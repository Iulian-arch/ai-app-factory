# AI App Factory

AI App Factory is a modular, extensible framework for AI-assisted software engineering.

Its purpose is to help transform natural-language requirements into real, testable, maintainable software projects through workflows, contracts, reusable assets, and controlled AI execution.

## Current status

Version: `0.1.0-alpha`

Milestone: `M1 – Foundation`

Sprint: `S1 – Bootstrap CLI`

## Initial goal

The first usable version will provide a CLI foundation:

```bash
aif --version
aif doctor
aif init
aif new demo
aif list
aif status
```

No AI integration is implemented in the first sprint. The first sprint focuses only on repository bootstrap, workspace/project structure, configuration, and CLI foundations.

## Core principles

- Core Engine does not know implementation details.
- Everything important is a contract.
- Plugins are replaceable.
- AI providers are replaceable.
- Simplicity wins over premature architecture.
- Every sprint must leave a demonstrable result.

## Repository

Official repository:

```text
https://github.com/iulian-arch/ai-app-factory
```
