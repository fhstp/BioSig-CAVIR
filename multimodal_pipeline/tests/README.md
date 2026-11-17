# Tests

This folder contains test scripts for the data processing pipeline.

## Test Files

### Investigation Scripts
- `test_heartpy_timestamp_bug.py` - Investigation of HeartPy's timestamp handling behavior with synthetic vs. real timestamps
- `test_timestamp_simple.py` - Root cause analysis of the HeartPy timestamp bug (unit detection issue)

### Unit Tests
- `test_detect_rri_units.py` - Tests for RRI unit detection logic
- `test_load_data_file.py` - Tests for data loading functionality
- `test_pipeline_config.py` - Tests for pipeline configuration

### Configuration
- `conftest.py` - Pytest configuration and fixtures

## Running Tests

To run all tests:
```bash
pytest tests/
```

To run a specific test:
```bash
pytest tests/test_pipeline_config.py
```
