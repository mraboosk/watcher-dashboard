# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`watcher-dashboard` is an OpenStack Horizon plugin that exposes the [Watcher](https://docs.openstack.org/watcher/latest/) infrastructure optimization service through a web UI. It is registered as an admin panel group in Horizon and communicates with the Watcher API via `python-watcherclient`.

## Commands

### Activate python virtual environment
```
source venv/bin/activate
```

### Run all tests
```bash
tox -e py3
```

### Run a single test module
```bash
python manage.py test --settings=watcher_dashboard.test.settings watcher_dashboard.content.audits.tests
```

### Run linting
```bash
tox -e pep8
```

### Run with coverage
```bash
tox -e cover
```

### Run the dev server (manual testing)
```bash
./run_tests.sh --runserver 0.0.0.0:8000
```

## Architecture

### Layer overview

```
watcher_dashboard/api/watcher.py        ← thin API wrapper (one class per resource)
watcher_dashboard/content/<panel>/      ← one directory per UI panel
watcher_dashboard/utils/errors.py       ← @handle_errors decorator used on API .get() methods
watcher_dashboard/test/helpers.py       ← base test classes (TestCase, APITestCase)
```

### API layer (`watcher_dashboard/api/watcher.py`)

Each Watcher resource (`Audit`, `AuditTemplate`, `ActionPlan`, `Action`, `Goal`, `Strategy`) is a class that inherits from Horizon's `base.APIDictWrapper`. The class methods call through `watcherclient(request)`, which is a per-request factory that reads the `infra-optim` service endpoint from the Keystone catalog.

The `@errors_utils.handle_errors(message)` decorator (from `watcher_dashboard/utils/errors.py`) is applied only to `.get()` methods — it wraps the call in a try/except and delegates to `horizon.exceptions.handle`. List/create/delete methods handle errors inline in the view layer instead.

### Panel/content layer

Each panel under `watcher_dashboard/content/` follows this identical structure:
- `panel.py` — registers the panel with Horizon's admin dashboard
- `tables.py` — `DataTable` subclasses; table actions call into `watcher_dashboard.api.watcher`
- `tabs.py` — detail page tab groups
- `views.py` — Django class-based views (`DataTableView`, `ModalFormView`, `MultiTableView`)
- `urls.py` — URL patterns wired to views
- `forms.py` — (where present) Django forms for create/edit workflows
- `tests.py` — (where present) unit tests using the `APITestCase` base class

The panels are: `goals`, `strategies`, `audit_templates`, `audits`, `action_plans`, `actions`.

The workflow to create a resource is: AuditTemplate → Audit → ActionPlan → (start) Actions.

### Test layer

`watcher_dashboard/test/helpers.py` provides three base classes:
- `TestCase` — for view tests; mocks are loaded from `test/test_data/`
- `APITestCase` — patches `api.watcher.watcherclient` with a `mock.Mock()` available as `self.watcherclient`, so tests assert calls like `self.watcherclient.audit.list.assert_called_once_with(...)`
- `BaseAdminViewTests` — for admin view tests

Integration tests are excluded from the default test run (`--exclude-tag integration`); they require a running Watcher service.

### Policy enforcement

`watcher_dashboard/conf/watcher_policy.json` defines RBAC rules. Each table action declares its required policy rule via `policy_rules = (("infra-optim", "resource:action"),)`. The file is injected into Horizon's `POLICY_FILES` setting at client-creation time by `insert_watcher_policy_file()`.

## Code conventions

- All user-visible strings must be wrapped in `gettext_lazy as _` for i18n.
- Flake8 ignores: `F405` (star imports in test settings), `W504` (line break after binary operator).
- The project follows [OpenStack hacking guidelines](https://github.com/openstack/hacking/blob/master/HACKING.rst).
- Contributions go through Gerrit at `review.opendev.org`, not GitHub PRs.
