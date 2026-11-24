# Test suite

Install the test dependency and run the complete suite with:

```bash
python3 -m pip install -e '.[test]'
pytest
```

Every executable command in `scripts/plumbing-scripts/` is parameterized in
`tests/test_plumbing_scripts.py`. The shared `tests/plumbing_harness.py`
applies four baseline checks to each command:

1. The file is executable Python with a `main()` function and main guard.
2. Importing it cannot start a subprocess; process boundaries are mocked.
3. `--help` exits successfully without requiring root or contacting services.
4. The shared plumbing dispatcher resolves it while `subprocess.run` is mocked.

`test_plumbing_inventory.py` keeps the command manifest aligned with the
executable scripts and validates literal `run_plumbing(...)` targets.
Command-specific behavior belongs in a separate focused test module only when
the command has behavior that the shared parameterized checks do not cover.
