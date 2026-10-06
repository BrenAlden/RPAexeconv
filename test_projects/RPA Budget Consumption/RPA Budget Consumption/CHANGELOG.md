# Changelog

All notable changes to this project will be documented in this file.

## [1.1.3] - 2025-08-25

### Changed
- Updating and deleting existing Windows credentials no longer requires inputting the current password

## [1.1.2] - 2025-07-16

### Improved
- Removed emoji's from error logging message when there's no windows credentials exist

## [1.1.1] - 2025-07-11

### Changed
- Log files renamed to 'Log 14_05_25 16_01_30 (`SERVICE_NAME`).log'

## [1.1.0] - 2025-07-11

### Changed
- `USERNAME` and `SERVICE_NAME` configurations have been moved to `Config.py`.
- Credential insertion now hides password input for better security.

### Added
- Updating existing Windows credentials now requires inputting the current password for verification.
- Deleting Windows credentials now requires password confirmation.
- Logs folder will now automatically keep a maximum of 30 folders; older logs will be deleted to save space.

### Improved
- New credentials can now be inserted without manually entering the `SERVICE_NAME`.

---

## [1.0.0] - 2025-05-21
- Initial release.