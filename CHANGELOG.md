# Changelog

All notable changes to diny are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-23

Initial release of diny — dead simple dependency injection for Python.

### Added

- `@singleton` / `@factory` class decorators to mark a class's default injection scope.
- `@inject` function decorator that auto-resolves typed parameters on call.
- `Singleton[T]` / `Factory[T]` parameter annotations to request injection at a call site or override a class's default scope.
- `provide()` / `aprovide()` context managers that open a scope and register classes, instances, or factory functions as overrides. Scopes nest.
- Async support: `@inject` wraps coroutine functions, and `aprovide()` awaits async provider callables.
