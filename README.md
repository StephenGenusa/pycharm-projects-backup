# PyCharm Projects Backup Utility

A robust and customizable utility for backing up PyCharm projects by intelligently selecting essential development files while excluding unnecessary or large files.

## Features

- **Smart File Selection**: Automatically includes important development files (Python, config files, docs) while excluding unnecessary ones
- **Module Detection**: Automatically detects and includes Python module directories
- **Size Control**: Excludes files larger than a specified size threshold (default: 20MB)
- **Custom Inclusions/Exclusions**: Specify custom paths to include or exclude
- **Project Selection**: Include or exclude specific projects from backups
- **Compression Options**: Control ZIP compression level
- **Backup Profiles**: Save and reuse custom backup configurations
- **Dry Run Mode**: Simulate backups without creating files
- **Restore Functionality**: Easily restore backups to a specified directory
- **Post-backup Actions**: Execute custom commands after successful backups
- **Detailed Logging**: Comprehensive logging with configurable levels
- **Progress Tracking**: Visual feedback during backup operations (with tqdm if installed)
- **Colored Output**: Intuitive colored terminal output (with colorama if installed)

## Installation

```bash
# Clone the repository
git clone https://github.com/stephengenusa/pycharm-projects-backup.git
cd pycharm-backup-utility

# Optional but recommended dependencies
pip install tqdm colorama
```

## Basic Usage

```bash
# Basic backup with default settings
python pycharm_project_backup.py

# Specify custom PyCharm directory and output file
python pycharm_project_backup.py -p /path/to/projects -o my_backup.zip

# Include virtualenv files in backup
python pycharm_project_backup.py -v
```

## Advanced Options

```bash
# Exclude specific directories
python pycharm_project_backup.py -e logs temp data

# Include specific paths even if they match exclusion patterns
python pycharm_project_backup.py -i project1/data/sample_configs venv/important_lib

# Back up only specific projects
python pycharm_project_backup.py --include-projects project1 project2

# Set maximum file size to include (default is 20MB)
python pycharm_project_backup.py -m 50MB

# Control compression level (0-9)
python pycharm_project_backup.py -c 6
```

## Backup Profiles

```bash
# Create a named profile with current settings
python pycharm_project_backup.py --create-profile daily_backup

# Use a saved profile
python pycharm_project_backup.py --use-profile daily_backup

# Create default profile with all projects
python pycharm_project_backup.py --create-default-profile

# List available profiles
python pycharm_project_backup.py --list-profiles
```

## Restoring Backups

```bash
# Restore a backup to a specified directory
python pycharm_project_backup.py --restore backup.zip --extract-dir /path/to/extract

# Restore only specific projects
python pycharm_project_backup.py --restore backup.zip --extract-dir /path/to/extract --restore-projects project1 project2
```

## Logging and Simulation

```bash
# Perform a dry run without creating files
python pycharm_project_backup.py --dry-run

# Configure logging
python pycharm_project_backup.py --log-file backup.log --log-level DEBUG
```

## Post-Backup Actions

```bash
# Execute commands after backup completes
python pycharm_project_backup.py --post-action "cp {backup_file} /backup/" --post-action "echo Backup completed at {date} {time}"
```

## Help and Documentation

For detailed help with examples:

```bash
python pycharm_project_backup.py --help-detailed
```

## Configuration

The utility stores profiles and settings in `~/.pycharm_backup/` by default.

## Dependencies

- **Required**: Python 3.6+
- **Optional**: tqdm (for progress bars), colorama (for colored output)

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

