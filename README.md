# MutaGuard

A Python mutation testing engine that measures test suite quality by injecting systematic code faults and checking whether your tests catch them.

Code coverage tells you which lines ran. Mutation testing tells you whether your tests would actually catch a bug on those lines. A test suite with 100% coverage can still miss real faults — MutaGuard finds them.

## How it works

MutaGuard parses your source file into an AST, applies mutation operators to generate modified versions of the code (mutants), runs your test suite against each mutant in an isolated subprocess, and reports which mutants survived (tests did not catch the change) versus which were killed (tests failed as expected).

The mutation score is `killed / (total - equivalent)`. A surviving mutant means there is a real code change your tests cannot detect.

## Mutation operators

| Category | Example |
|---|---|
| Arithmetic | `a + b` -> `a - b` |
| Relational | `x > 0` -> `x >= 0` |
| Boolean | `a and b` -> `a or b` |
| Statement | `return result` -> `return None` |
| Constant | `0` -> `1`, `""` -> `"fuzz"` |
| Boundary | `x < n` -> `x < n+1`, `x < n-1` |

## Installation

Requires Python 3.10+. No external dependencies beyond pytest for running your tests.

```bash
git clone https://github.com/Nikiel54/mutaguard.git
cd mutaguard
pip install pytest
```

## Usage

```bash
# Basic usage
python cli.py path/to/source.py --tests path/to/tests/

# With options
python cli.py path/to/source.py \
  --tests path/to/tests/ \
  --workers 4 \
  --timeout 15 \
  --operators arithmetic,relational,boundary \
  --report report.html \
  --verbose
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--tests` | required | Test file or directory to run with pytest |
| `--workers` | auto | Number of parallel worker processes |
| `--timeout` | 10s | Per-mutant timeout before marking as killed |
| `--operators` | all | Comma-separated operator categories to use |
| `--report` | `mutaguard_report.html` | Output path for HTML report |
| `--exclude-lines` | none | Comma-separated line numbers to skip |
| `--verbose` | off | Print each mutant result as it completes |

## Results on real code

| Target | Mutants | Score | Notes |
|---|---|---|---|
| `simpleeval` | 69 | 69.6% | 20 survivors including boundary gap on max-exponent validation |
| `boltons/mathutils` | 73 | 100% | Validated tool correctness against well-tested production code |
| `boltons/statsutils` | 251 | 100% | 251 mutants, 0 errors |

## Limitations

- Targets Python 3.10+ source files only
- Assumes pytest as the test runner
- Equivalent mutant detection is heuristic and conservative — some equivalent mutants may still appear in the survived count
- Performance scales with test suite speed — fast unit tests make mutation testing practical, slow integration tests do not

## Consider giving this project a star if you found it useful ^_^
