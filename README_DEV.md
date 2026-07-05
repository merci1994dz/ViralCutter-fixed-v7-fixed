# Development Notes

## Current gaps
- No automated tests yet.
- `webui/app.py` is still large and should be split into smaller modules.
- Runtime validation exists, but more user-facing error messages can still be made clearer.

## Suggested next steps
1. Add a small test suite for argument validation and helper functions.
2. Split Gradio UI helpers into dedicated files.
3. Add a lightweight smoke test for the CLI startup path.
4. Tighten error reporting for missing dependencies and invalid project state.
