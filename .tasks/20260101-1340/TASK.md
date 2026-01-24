# Feature: External Selenium Worker Fallback

- STATUS: PENDING
- PRIORITY: 2

## Objective
Integrate the external Selenium worker (previously prototyped in `seleniumnew.py`) as a fallback mechanism for Selenium-based data fetching. If the local Selenium worker fails (e.g., resource exhaustion, local driver issues), the system should attempt to fetch the URL using the external Selenium worker via the broker.

## Research
- **Prototype:** `seleniumnew.py` (contains logic to enqueue tasks to a remote broker).
- **Existing Extensions:**
  - `app/extensions/parsers/selenium.py`: Uses local `app.workers.selenium`.
- **Integration Points:** `get_html` method in `SeleniumParserExtension`.

## Plan

### 1. Configuration
- [ ] Add `EXTERNAL_SELENIUM_BROKER_URL` to `.env.dist`.
- [ ] Add `EXTERNAL_SELENIUM_BROKER_URL` to `.env`.
- [ ] Update `app/configs/env.py` to load `EXTERNAL_SELENIUM_BROKER_URL`.

### 2. Service Implementation
- [x] Create `app/services/selenium/` package.
- [x] Create `app/services/selenium/_worker.py` (wraps `app.workers.selenium`).
- [x] Create `app/services/selenium/_external.py` (implements broker communication).
- [x] Create `app/services/selenium/__init__.py`:
  - Implement `SeleniumService` class.
  - Logic: Try `_worker.get_html`. If it fails, try `_external.get_html`.

### 3. Integration (Fallback Logic)
- [x] **Modify `app/extensions/parsers/selenium.py`:**
  - Update to use `app.services.selenium.SeleniumService`.
  - Remove direct dependencies on `app.workers.selenium` or explicit fallback logic inside the extension (delegate to service).

### 4. Refactoring & Cleanup
- [ ] Remove `.tasks/20260101-1340/seleniumnew.py` once integrated.
- [x] Ensure types are correct (`mypy`).

## Problems & Handling Strategy
- **Redundancy:** Ensure the external worker is only used when the local one definitively fails.
- **Failures:** If both local and external workers fail, raise the original exception.