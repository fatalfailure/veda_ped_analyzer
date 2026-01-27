# Contributing to veda_ped_analyzer

Thank you for your interest in contributing to **veda_ped_analyzer**.
This project is primarily intended as a research-oriented analysis tool,
and contributions are welcome under the guidelines below.

## Scope of contributions

Welcome:
- Bug fixes
- Improvements to parsers (ORCA / Gaussian)
- Documentation improvements
- Small usability enhancements

Please discuss large refactors or new features in an Issue before starting work.

## How to contribute

1. Fork the repository on GitHub.
2. Create a feature branch:
   ```bash
   git checkout -b feature/my-change
   ```
3. Commit your changes with clear messages.
4. Push to your fork and open a Pull Request.

## Coding style

- Use clear, explicit variable names.
- Prefer robustness and clarity over cleverness.
- Avoid adding external dependencies unless strongly justified.
- Keep scientific assumptions explicit in comments.

## Testing

If possible, test changes on:
- At least one ORCA output
- At least one Gaussian output
- Symmetric and non-symmetric molecules

Include notes about tested cases in the Pull Request description.

## Code of conduct

Please be respectful and constructive.
Scientific disagreement is welcome; personal attacks are not.
