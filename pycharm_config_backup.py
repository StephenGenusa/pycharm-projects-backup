#!/usr/bin/env python3
"""PyCharm Configuration Backup Tool.

This script provides functionality to backup and restore PyCharm project
configuration files from the .idea directories, recent projects lists,
and global IDE settings.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union


def setup_logging(log_file: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """Configure logging for the application.

    Args:
        log_file: Optional path to log file.
        verbose: Whether to use verbose (DEBUG) logging.

    Returns:
        Configured logger instance.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("pycharm_backup")
    logger.setLevel(log_level)

    # Clear existing handlers if any
    if logger.handlers:
        logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_pycharm_config_dirs() -> List[str]:
    """Find PyCharm configuration directories based on OS.

    Returns:
        List of paths to PyCharm configuration directories.
    """
    config_dirs = []

    if sys.platform.startswith("win"):
        # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            jetbrains_dir = os.path.join(appdata, "JetBrains")
            if os.path.exists(jetbrains_dir):
                config_dirs = [os.path.join(jetbrains_dir, d) for d in os.listdir(jetbrains_dir)
                               if d.startswith("PyCharm")]

    elif sys.platform.startswith("darwin"):
        # macOS
        home = os.path.expanduser("~")
        app_support = os.path.join(home, "Library", "Application Support", "JetBrains")
        if os.path.exists(app_support):
            config_dirs = [os.path.join(app_support, d) for d in os.listdir(app_support)
                           if d.startswith("PyCharm")]

    else:
        # Linux/Unix
        home = os.path.expanduser("~")
        config = os.path.join(home, ".config", "JetBrains")
        if os.path.exists(config):
            config_dirs = [os.path.join(config, d) for d in os.listdir(config)
                           if d.startswith("PyCharm")]

    return config_dirs


def get_global_settings_files() -> Dict[str, List[str]]:
    """Find important PyCharm global settings files.

    Returns:
        Dictionary with categories of settings files and their paths.
    """
    settings_files = {
        "ide_settings": [],
        "code_style": [],
        "templates": [],
        "dictionaries": [],
        "plugin_settings": [],
        "scratches": [],
        "other": []
    }

    config_dirs = get_pycharm_config_dirs()

    for config_dir in config_dirs:
        # IDE Settings
        options_dir = os.path.join(config_dir, "options")
        if os.path.exists(options_dir):
            # General IDE settings
            ide_settings_files = [
                "ide.general.xml",
                "editor.xml",
                "keymap.xml",
                "colors.scheme.xml",
                "editor-font.xml",
                "ui.lnf.xml",
                "updates.xml",
                "terminal.xml"
            ]

            for file in ide_settings_files:
                file_path = os.path.join(options_dir, file)
                if os.path.exists(file_path):
                    settings_files["ide_settings"].append(file_path)

            # Code Style Settings
            code_style_files = [
                "code.style.schemes.xml",
            ]

            for file in code_style_files:
                file_path = os.path.join(options_dir, file)
                if os.path.exists(file_path):
                    settings_files["code_style"].append(file_path)

            # Code style schemes directory
            code_style_dir = os.path.join(options_dir, "code.style.schemes")
            if os.path.exists(code_style_dir):
                for file in os.listdir(code_style_dir):
                    if file.endswith(".xml"):
                        settings_files["code_style"].append(
                            os.path.join(code_style_dir, file)
                        )

            # Live Templates
            templates_dir = os.path.join(options_dir, "templates")
            if os.path.exists(templates_dir):
                for file in os.listdir(templates_dir):
                    if file.endswith(".xml"):
                        settings_files["templates"].append(
                            os.path.join(templates_dir, file)
                        )

            # File Templates
            file_templates_dir = os.path.join(options_dir, "fileTemplates")
            if os.path.exists(file_templates_dir):
                for root, _, files in os.walk(file_templates_dir):
                    for file in files:
                        settings_files["templates"].append(
                            os.path.join(root, file)
                        )

            # Plugin Settings
            plugin_files = [
                "pluginSettings.xml",
                "other.xml"
            ]

            for file in plugin_files:
                file_path = os.path.join(options_dir, file)
                if os.path.exists(file_path):
                    settings_files["plugin_settings"].append(file_path)

        # Scratches and Consoles
        scratches_dir = os.path.join(config_dir, "scratches")
        if os.path.exists(scratches_dir):
            for root, _, files in os.walk(scratches_dir):
                for file in files:
                    settings_files["scratches"].append(
                        os.path.join(root, file)
                    )

        consoles_dir = os.path.join(config_dir, "consoles")
        if os.path.exists(consoles_dir):
            for root, _, files in os.walk(consoles_dir):
                for file in files:
                    settings_files["scratches"].append(
                        os.path.join(root, file)
                    )

    return settings_files


def get_recent_projects_files() -> Dict[str, List[str]]:
    """Find PyCharm's recent projects list files.

    Returns:
        Dictionary mapping PyCharm versions to their recent projects files.
    """
    recent_files = {}
    config_dirs = get_pycharm_config_dirs()

    for config_dir in config_dirs:
        pycharm_version = os.path.basename(config_dir)
        options_dir = os.path.join(config_dir, "options")
        if not os.path.exists(options_dir):
            continue

        version_files = []

        recent_projects = os.path.join(options_dir, "recentProjects.xml")
        if os.path.exists(recent_projects):
            version_files.append(recent_projects)

        recent_solutions = os.path.join(options_dir, "recentSolutions.xml")
        if os.path.exists(recent_solutions):
            version_files.append(recent_solutions)

        if version_files:
            recent_files[pycharm_version] = version_files

    return recent_files


def get_default_projects_dir() -> str:
    """Detect the default PyCharm projects directory based on OS.

    Returns:
        The default PyCharm projects directory path for the current OS.
    """
    home_dir = os.path.expanduser("~")

    if sys.platform.startswith("win"):
        # Windows: Usually in Documents
        if os.path.isdir(os.path.join(home_dir, "Documents", "PyCharmProjects")):
            return os.path.join(home_dir, "Documents", "PyCharmProjects")
        else:
            return os.path.join(home_dir, "PyCharmProjects")
    elif sys.platform.startswith("darwin"):
        # macOS
        return os.path.join(home_dir, "PycharmProjects")
    else:
        # Linux/Unix
        return os.path.join(home_dir, "PycharmProjects")


def find_idea_files(
        project_dir: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        logger: Optional[logging.Logger] = None
) -> List[str]:
    """Find important .idea configuration files in project directories.

    Args:
        project_dir: Directory containing PyCharm projects.
        include_patterns: Optional list of glob patterns to include.
        exclude_patterns: Optional list of glob patterns to exclude.
        logger: Optional logger for detailed logging.

    Returns:
        A list of paths to important configuration files.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    idea_files = []

    # Default important files
    default_important_files = [
        "workspace.xml",  # Run configurations and layout
        "misc.xml",  # Python interpreter and other settings
        "modules.xml",  # Module definitions
        ".name",  # Project name
        "vcs.xml",  # Version control settings
        "remote-mappings.xml",  # Remote interpreter settings
        "deployment.xml",  # Deployment configurations
        "jsLibraryMappings.xml",  # JavaScript library mappings
        "dataSources.xml",  # Database connections
        "dataSources.ids",  # Database IDs
    ]

    for root, dirs, _ in os.walk(project_dir):
        # Skip directories that are not PyCharm project directories
        if ".idea" in dirs:
            project_name = os.path.basename(root)
            idea_dir = os.path.join(root, ".idea")
            logger.debug(f"Found PyCharm project: {project_name} at {root}")

            # Process runConfigurations directory
            run_config_dir = os.path.join(idea_dir, "runConfigurations")
            if os.path.exists(run_config_dir):
                for run_file in os.listdir(run_config_dir):
                    if run_file.endswith(".xml"):
                        file_path = os.path.join(run_config_dir, run_file)
                        # Check include/exclude patterns
                        if should_process_file(file_path, include_patterns, exclude_patterns):
                            idea_files.append(file_path)
                            logger.debug(f"Adding run configuration: {file_path}")

            # Process tools directory
            tools_dir = os.path.join(idea_dir, "tools")
            if os.path.exists(tools_dir):
                for tool_file in os.listdir(tools_dir):
                    file_path = os.path.join(tools_dir, tool_file)
                    if os.path.isfile(file_path) and should_process_file(
                            file_path, include_patterns, exclude_patterns
                    ):
                        idea_files.append(file_path)
                        logger.debug(f"Adding tool configuration: {file_path}")

            # Process dictionaries directory
            dictionaries_dir = os.path.join(idea_dir, "dictionaries")
            if os.path.exists(dictionaries_dir):
                for dict_file in os.listdir(dictionaries_dir):
                    file_path = os.path.join(dictionaries_dir, dict_file)
                    if os.path.isfile(file_path) and should_process_file(
                            file_path, include_patterns, exclude_patterns
                    ):
                        idea_files.append(file_path)
                        logger.debug(f"Adding dictionary: {file_path}")

            # Add other important files
            for file in default_important_files:
                file_path = os.path.join(idea_dir, file)
                if os.path.exists(file_path) and should_process_file(
                        file_path, include_patterns, exclude_patterns
                ):
                    idea_files.append(file_path)
                    logger.debug(f"Adding configuration file: {file_path}")

    logger.info(f"Found {len(idea_files)} configuration files across all projects")
    return idea_files


def should_process_file(
        file_path: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
) -> bool:
    """Determine if a file should be processed based on include/exclude patterns.

    Args:
        file_path: Path to the file to check.
        include_patterns: List of glob patterns to include.
        exclude_patterns: List of glob patterns to exclude.

    Returns:
        True if the file should be processed, False otherwise.
    """
    import fnmatch

    # If no patterns are specified, include everything
    if not include_patterns and not exclude_patterns:
        return True

    # Check exclude patterns first (exclude takes precedence)
    if exclude_patterns:
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return False

    # If include patterns exist, file must match at least one
    if include_patterns:
        for pattern in include_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    # If we got here, no include patterns and file wasn't excluded
    return True


def create_backup(
        projects_dir: str,
        output_file: Optional[str] = None,
        output_dir: Optional[str] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        backup_recent_projects: bool = True,
        backup_global_settings: bool = False,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None
) -> bool:
    """Create a backup of PyCharm project configurations.

    Args:
        projects_dir: Directory containing PyCharm projects.
        output_file: Optional path for the backup file. If not provided,
                     a default name will be generated.
        output_dir: Optional directory for storing the backup file.
                    Defaults to current working directory.
        include_patterns: Optional list of glob patterns to include.
        exclude_patterns: Optional list of glob patterns to exclude.
        backup_recent_projects: Whether to include recent projects files.
        backup_global_settings: Whether to include global IDE settings.
        dry_run: If True, only simulate the backup.
        logger: Optional logger for detailed logging.

    Returns:
        True if backup was successful, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    if not os.path.isdir(projects_dir):
        logger.error(f"Directory not found: {projects_dir}")
        return False

    # If output_dir is not provided, use the current working directory
    if output_dir is None:
        output_dir = os.getcwd()

    # Ensure output_dir exists
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logger.info(f"Created output directory: {output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory {output_dir}: {str(e)}")
            return False

    # Create backup filename
    if output_file is None:
        today = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        output_file = os.path.join(output_dir, f"pycharm_idea_backup_{today}.zip")
    elif not os.path.isabs(output_file):
        # If output_file is a relative path, make it relative to output_dir
        output_file = os.path.join(output_dir, output_file)

    # Find all .idea configuration files
    logger.info(f"Scanning for PyCharm projects in {projects_dir}")
    idea_files = find_idea_files(
        projects_dir, include_patterns, exclude_patterns, logger
    )

    # Add recent projects files if requested
    recent_files = []
    if backup_recent_projects:
        recent_files_dict = get_recent_projects_files()
        total_recent_files = sum(len(files) for files in recent_files_dict.values())
        if total_recent_files > 0:
            logger.info(
                f"Found {total_recent_files} recent projects list files across {len(recent_files_dict)} PyCharm versions")
            for version, files in recent_files_dict.items():
                for file in files:
                    recent_files.append(
                        (file, os.path.join("_pycharm_recent_projects", version, os.path.basename(file))))

    # Add global settings if requested
    global_settings_files = []
    if backup_global_settings:
        settings = get_global_settings_files()
        for category, files in settings.items():
            if files:
                logger.info(f"Found {len(files)} {category.replace('_', ' ')} files")
                for file in files:
                    # Get PyCharm version from the path
                    pycharm_version = None
                    for config_dir in get_pycharm_config_dirs():
                        if file.startswith(config_dir):
                            pycharm_version = os.path.basename(config_dir)
                            rel_path = os.path.relpath(file, config_dir)
                            break

                    if pycharm_version:
                        # Store global settings with PyCharm version to avoid conflicts
                        arcname = os.path.join("_pycharm_global_settings", pycharm_version, rel_path)
                        global_settings_files.append((file, arcname))

    all_files_count = len(idea_files) + len(recent_files) + len(global_settings_files)

    if all_files_count == 0:
        logger.warning("No PyCharm configuration files found to back up")
        return False

    if dry_run:
        logger.info(f"DRY RUN: Would back up {all_files_count} configuration files to {output_file}")
        if idea_files:
            logger.info(f"  {len(idea_files)} project configuration files")
        if recent_files:
            logger.info(f"  {len(recent_files)} recent projects list files")
        if global_settings_files:
            logger.info(f"  {len(global_settings_files)} global settings files")
        return True

    # Create a zip archive with the configuration files
    try:
        with zipfile.ZipFile(
                output_file, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        ) as zipf:
            # Add project configuration files
            for file in idea_files:
                # Store files with relative paths to preserve directory structure
                arcname = os.path.relpath(file, start=os.path.dirname(projects_dir))
                zipf.write(file, arcname)
                logger.debug(f"Added to backup: {arcname}")

            # Add recent projects files
            for file, arcname in recent_files:
                zipf.write(file, arcname)
                logger.debug(f"Added to backup: {arcname}")

            # Add global settings files
            for file, arcname in global_settings_files:
                zipf.write(file, arcname)
                logger.debug(f"Added to backup: {arcname}")

        # Verify the backup
        original_files = idea_files + [f for f, _ in recent_files] + [f for f, _ in global_settings_files]
        backup_verified = verify_backup(output_file, original_files, logger)

        logger.info(f"Backup created: {output_file}")
        logger.info(f"Backed up {len(idea_files)} project configuration files")
        if recent_files:
            logger.info(f"Backed up {len(recent_files)} recent projects list files")
        if global_settings_files:
            logger.info(f"Backed up {len(global_settings_files)} global settings files")

        if not backup_verified:
            logger.warning("Backup verification failed. The backup may be incomplete or corrupted.")
            return False

        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")
        return False


def verify_backup(
        backup_file: str, original_files: List[str], logger: Optional[logging.Logger] = None
) -> bool:
    """Verify the integrity of the backup file.

    Args:
        backup_file: Path to the backup file.
        original_files: List of original files that were backed up.
        logger: Optional logger for detailed logging.

    Returns:
        True if verification passed, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    try:
        logger.info("Verifying backup integrity...")

        # Get the list of files in the backup
        with zipfile.ZipFile(backup_file, "r") as zipf:
            backup_files = zipf.namelist()

        # Check if backup contains expected number of files
        if len(backup_files) < len(original_files):
            logger.warning(
                f"Backup contains fewer files ({len(backup_files)}) "
                f"than expected ({len(original_files)})"
            )
            return False

        # Basic integrity check passed
        logger.info("Backup verification passed")
        return True
    except Exception as e:
        logger.error(f"Backup verification failed: {str(e)}")
        return False


def restore_recent_projects(
        backup_file: str,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None
) -> bool:
    """Restore PyCharm's recent projects list files.

    Args:
        backup_file: Path to the backup file.
        dry_run: If True, only simulate the restore operation.
        logger: Optional logger for detailed logging.

    Returns:
        True if restore was successful, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        return False

    # Check if backup contains recent projects files
    recent_files_in_backup = []
    with zipfile.ZipFile(backup_file, "r") as zipf:
        for file_info in zipf.infolist():
            if file_info.filename.startswith("_pycharm_recent_projects/"):
                recent_files_in_backup.append(file_info.filename)

    if not recent_files_in_backup:
        logger.warning("No recent projects list files found in backup")
        return False

    logger.info(f"Found {len(recent_files_in_backup)} recent projects list files in backup")

    # Get current PyCharm config directories
    config_dirs = get_pycharm_config_dirs()
    if not config_dirs:
        logger.error("No PyCharm configuration directories found on this system")
        return False

    # Restore each recent projects file
    files_restored = 0

    with zipfile.ZipFile(backup_file, "r") as zipf:
        for file_path in recent_files_in_backup:
            file_name = os.path.basename(file_path)

            # Try to find a matching config directory
            for config_dir in config_dirs:
                options_dir = os.path.join(config_dir, "options")
                target_path = os.path.join(options_dir, file_name)

                if dry_run:
                    logger.info(f"DRY RUN: Would restore {file_name} to {target_path}")
                    files_restored += 1
                    continue

                if os.path.exists(options_dir):
                    # Extract the file
                    with zipf.open(file_path) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                    logger.info(f"Restored {file_name} to {target_path}")
                    files_restored += 1
                    break
            else:
                logger.warning(f"Could not find a suitable location to restore {file_name}")

    if files_restored > 0:
        logger.info(f"Successfully restored {files_restored} recent projects list files")
        return True
    else:
        logger.warning("No recent projects list files were restored")
        return False


def restore_global_settings(
        backup_file: str,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None
) -> bool:
    """Restore PyCharm global settings files.

    Args:
        backup_file: Path to the backup file.
        dry_run: If True, only simulate the restore operation.
        logger: Optional logger for detailed logging.

    Returns:
        True if restore was successful, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        return False

    # Check if backup contains global settings files
    global_settings_in_backup = []
    pycharm_versions_in_backup = set()

    with zipfile.ZipFile(backup_file, "r") as zipf:
        for file_info in zipf.infolist():
            if file_info.filename.startswith("_pycharm_global_settings/"):
                global_settings_in_backup.append(file_info.filename)

                # Extract PyCharm version from path
                parts = file_info.filename.split('/')
                if len(parts) >= 3:
                    pycharm_versions_in_backup.add(parts[1])

    if not global_settings_in_backup:
        logger.warning("No global settings files found in backup")
        return False

    logger.info(
        f"Found {len(global_settings_in_backup)} global settings files for {len(pycharm_versions_in_backup)} PyCharm versions in backup")

    # Get current PyCharm config directories
    config_dirs = get_pycharm_config_dirs()
    if not config_dirs:
        logger.error("No PyCharm configuration directories found on this system")
        return False

    # Restore global settings files
    files_restored = 0

    with zipfile.ZipFile(backup_file, "r") as zipf:
        for version in pycharm_versions_in_backup:
            # Find matching config directory for this version
            matching_dirs = [d for d in config_dirs if os.path.basename(d) == version]

            if not matching_dirs:
                logger.warning(f"No matching PyCharm installation found for version {version}")
                continue

            config_dir = matching_dirs[0]
            logger.info(f"Restoring global settings to {config_dir}")

            # Get files for this version
            version_files = [f for f in global_settings_in_backup
                             if f.startswith(f"_pycharm_global_settings/{version}/")]

            for file_path in version_files:
                # Extract the relative path within the config dir
                rel_path = '/'.join(file_path.split('/')[2:])  # Skip _pycharm_global_settings/version/
                target_path = os.path.join(config_dir, rel_path)

                if dry_run:
                    logger.info(f"DRY RUN: Would restore {rel_path} to {target_path}")
                    files_restored += 1
                    continue

                # Create directory structure if needed
                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                # Extract the file
                try:
                    with zipf.open(file_path) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                    logger.info(f"Restored {rel_path}")
                    files_restored += 1
                except Exception as e:
                    logger.error(f"Failed to restore {rel_path}: {str(e)}")

    if files_restored > 0:
        logger.info(f"Successfully restored {files_restored} global settings files")
        return True
    else:
        logger.warning("No global settings files were restored")
        return False


def clean_old_backups(max_backups: int, logger: Optional[logging.Logger] = None) -> None:
    """Keep only the most recent backups and delete older ones.

    Args:
        max_backups: Maximum number of backups to keep.
        logger: Optional logger for detailed logging.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    if max_backups <= 0:
        return

    backup_pattern = re.compile(r"pycharm_idea_backup_\d{2}_\d{2}_\d{4}\.zip")
    backups = [f for f in os.listdir(".") if backup_pattern.match(f)]

    if len(backups) <= max_backups:
        return

    # Sort backups by modification time (newest first)
    backups.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    # Delete oldest backups beyond max_backups
    for old_backup in backups[max_backups:]:
        try:
            logger.info(f"Removing old backup: {old_backup}")
            os.remove(old_backup)
        except Exception as e:
            logger.error(f"Failed to remove old backup {old_backup}: {str(e)}")


def list_backups(logger: Optional[logging.Logger] = None) -> List[str]:
    """List available backups in the current directory.

    Args:
        logger: Optional logger for detailed logging.

    Returns:
        A list of available backup file names.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    backup_pattern = re.compile(r"pycharm_idea_backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.zip")
    backups = [f for f in os.listdir(".") if backup_pattern.match(f)]

    if not backups:
        logger.info("No backups found in the current directory")
        return []

    # Sort by modification time (newest first)
    backups.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    logger.info("Available backups:")
    for i, backup in enumerate(backups, 1):
        size = os.path.getsize(backup) / 1024  # Size in KB
        mod_time = datetime.datetime.fromtimestamp(
            os.path.getmtime(backup)
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Get contents summary
        try:
            with zipfile.ZipFile(backup, "r") as zipf:
                projects_count = len(set([
                    path.split('/')[1]
                    for path in zipf.namelist()
                    if '/' in path and not path.startswith('_')
                ]))

                has_recent = any(name.startswith("_pycharm_recent_projects/") for name in zipf.namelist())
                has_global = any(name.startswith("_pycharm_global_settings/") for name in zipf.namelist())

                content_info = []
                if projects_count > 0:
                    content_info.append(f"{projects_count} projects")
                if has_recent:
                    content_info.append("recent projects list")
                if has_global:
                    content_info.append("global settings")

                content_str = ", ".join(content_info)

            logger.info(f"  {i}. {backup} ({size:.1f} KB, {mod_time}) - {content_str}")
        except Exception:
            logger.info(f"  {i}. {backup} ({size:.1f} KB, {mod_time})")

    return backups


def list_projects_in_backup(
        backup_file: str, logger: Optional[logging.Logger] = None
) -> List[str]:
    """List projects contained in a backup file.

    Args:
        backup_file: Path to the backup file.
        logger: Optional logger for detailed logging.

    Returns:
        List of project names found in the backup.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        return []

    try:
        projects = set()
        has_recent_projects = False
        has_global_settings = False

        with zipfile.ZipFile(backup_file, "r") as zipf:
            for file_info in zipf.infolist():
                if file_info.filename.startswith("_pycharm_recent_projects/"):
                    has_recent_projects = True
                    continue
                elif file_info.filename.startswith("_pycharm_global_settings/"):
                    has_global_settings = True
                    continue

                # Parse project name from path
                parts = file_info.filename.split("/")
                if len(parts) >= 2:
                    # The second element is the project name
                    projects.add(parts[1])

        if has_recent_projects:
            logger.info("Backup includes PyCharm recent projects list files")
        if has_global_settings:
            logger.info("Backup includes PyCharm global settings files")

        return sorted(list(projects))
    except Exception as e:
        logger.error(f"Failed to list projects in backup: {str(e)}")
        return []


def restore_projects(
        projects_dir: str,
        projects: Union[str, List[str]],
        backup_file: Optional[str] = None,
        restore_recent_projects_files: bool = False,
        restore_global_settings_files: bool = False,
        dry_run: bool = False,
        show_diff: bool = False,
        logger: Optional[logging.Logger] = None
) -> bool:
    """Restore configuration files for one or more projects.

    Args:
        projects_dir: Directory containing PyCharm projects.
        projects: Project name or list of project names to restore.
        backup_file: Optional path to the backup file. If not provided,
                     will prompt user to select from available backups.
        restore_recent_projects_files: Whether to restore recent projects files.
        restore_global_settings_files: Whether to restore global settings files.
        dry_run: If True, only simulate the restore operation.
        show_diff: Whether to show differences before restoring.
        logger: Optional logger for detailed logging.

    Returns:
        True if restore was successful, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    # Convert single project name to list
    if isinstance(projects, str):
        if projects.lower() == "all":
            projects = []  # Will be populated with all projects from backup
        else:
            projects = [projects]

    # Get backup file if not specified
    if backup_file is None:
        backups = list_backups(logger)
        if not backups:
            return False

        while True:
            backup_choice = input("Enter backup number to use for restore: ")
            try:
                backup_file = backups[int(backup_choice) - 1]
                break
            except (ValueError, IndexError):
                logger.error("Invalid selection, please try again")

    # Check if backup exists
    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        return False

    # If 'all' was specified, get all projects from the backup
    if not projects:  # Empty list means all projects
        projects = list_projects_in_backup(backup_file, logger)
        logger.info(f"Found {len(projects)} projects in backup: {', '.join(projects)}")

    # Process each project
    projects_restored = 0
    for project_name in projects:
        if restore_project(
                projects_dir, project_name, backup_file, dry_run, show_diff, logger
        ):
            projects_restored += 1

    # Restore recent projects files if requested
    if restore_recent_projects_files:
        restore_recent_projects(backup_file, dry_run, logger)

    # Restore global settings files if requested
    if restore_global_settings_files:
        restore_global_settings(backup_file, dry_run, logger)

    logger.info(f"Restored {projects_restored}/{len(projects)} projects")
    return projects_restored > 0


def compare_files(file1: str, file2: str) -> List[str]:
    """Compare two files and return their differences.

    Args:
        file1: Path to the first file.
        file2: Path to the second file.

    Returns:
        List of lines showing the differences.
    """
    import difflib

    with open(file1, 'r', encoding='utf-8', errors='ignore') as f:
        file1_lines = f.readlines()

    with open(file2, 'r', encoding='utf-8', errors='ignore') as f:
        file2_lines = f.readlines()

    diff = difflib.unified_diff(
        file1_lines,
        file2_lines,
        fromfile=os.path.basename(file1),
        tofile=os.path.basename(file2),
        n=3
    )

    return list(diff)


def restore_project(
        projects_dir: str,
        project_name: str,
        backup_file: str,
        dry_run: bool = False,
        show_diff: bool = False,
        logger: Optional[logging.Logger] = None
) -> bool:
    """Restore configuration files for a specific project.

    Args:
        projects_dir: Directory containing PyCharm projects.
        project_name: Name of the project to restore.
        backup_file: Path to the backup file.
        dry_run: If True, only simulate the restore operation.
        show_diff: Whether to show differences before restoring.
        logger: Optional logger for detailed logging.

    Returns:
        True if restore was successful, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger("pycharm_backup")

    project_path = os.path.join(projects_dir, project_name)
    if not os.path.exists(project_path):
        logger.error(f"Project directory not found: {project_path}")
        return False

    # Check if it's a PyCharm project
    idea_dir = os.path.join(project_path, ".idea")
    if not os.path.exists(idea_dir):
        logger.error(
            f"{project_path} does not appear to be a PyCharm project "
            "(no .idea directory)"
        )
        return False

    # Extract relevant files from the backup
    project_path_in_zip = os.path.basename(projects_dir) + "/" + project_name
    temp_dir = None
    files_to_restore = []

    with zipfile.ZipFile(backup_file, "r") as zipf:
        # First, identify files to restore
        for file_info in zipf.infolist():
            # Check if the file belongs to the project we're restoring
            if file_info.filename.startswith(project_path_in_zip):
                # Get the relative path within .idea directory
                rel_path = os.path.relpath(file_info.filename, project_path_in_zip)
                target_path = os.path.join(idea_dir, rel_path)
                files_to_restore.append((file_info.filename, target_path))

        # If no files found for this project
        if not files_to_restore:
            logger.warning(f"No configuration files found for {project_name} in the backup")
            return False

        # Show what will be restored
        logger.info(f"Found {len(files_to_restore)} configuration files to restore for {project_name}")

        # If show_diff is enabled, extract files to temp dir and compare
        if show_diff:
            import tempfile
            temp_dir = tempfile.mkdtemp()

            for zip_path, target_path in files_to_restore:
                if os.path.exists(target_path):
                    # Extract to temp dir for comparison
                    temp_path = os.path.join(temp_dir, os.path.basename(target_path))
                    with zipf.open(zip_path) as source, open(temp_path, 'wb') as target:
                        shutil.copyfileobj(source, target)

                    # Show diff if files are different
                    if os.path.getsize(temp_path) != os.path.getsize(target_path):
                        logger.info(f"Differences in {os.path.basename(target_path)}:")
                        try:
                            diff = compare_files(target_path, temp_path)
                            if diff:
                                for line in diff:
                                    print(line, end='')
                            else:
                                logger.info("  Binary files differ in size but text content is identical")
                        except UnicodeDecodeError:
                            logger.info("  Binary files differ")

        # Perform the restore if not a dry run
        if not dry_run:
            files_restored = 0
            for zip_path, target_path in files_to_restore:
                # Create directory if needed
                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                # Extract the file
                with zipf.open(zip_path) as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

                files_restored += 1
                logger.debug(f"Restored: {os.path.relpath(target_path, idea_dir)}")

            logger.info(f"Successfully restored {files_restored} configuration files for {project_name}")
        else:
            logger.info(f"DRY RUN: Would restore {len(files_to_restore)} configuration files for {project_name}")
            for _, target_path in files_to_restore[:5]:  # Show only first 5 to avoid spam
                logger.info(f"  Would restore: {os.path.relpath(target_path, idea_dir)}")
            if len(files_to_restore) > 5:
                logger.info(f"  (and {len(files_to_restore) - 5} more files...)")

    # Clean up temp directory if created
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    return True


def interactive_mode(logger: logging.Logger) -> None:
    """Run the application in interactive mode with a menu.

    Args:
        logger: Logger instance for logging.
    """
    projects_dir = get_default_projects_dir()
    output_dir = os.getcwd()  # Default output directory

    while True:
        print("\nPyCharm Configuration Backup Tool")
        print("---------------------------------")
        print("1. Create a backup")
        print("2. Restore a backup")
        print("3. List available backups")
        print("4. Set projects directory")
        print("5. Set output directory")
        print("6. Restore recent projects list")
        print("7. Restore global settings")
        print("8. Exit")

        choice = input("\nEnter your choice (1-8): ")

        if choice == "1":
            # Create backup
            output_file = input("Enter backup filename (or press Enter for default): ")
            output_file = output_file if output_file else None

            include = input("Enter patterns to include (comma-separated, or Enter for all): ")
            include_patterns = [p.strip() for p in include.split(",")] if include else None

            exclude = input("Enter patterns to exclude (comma-separated, or Enter for none): ")
            exclude_patterns = [p.strip() for p in exclude.split(",")] if exclude else None

            backup_recent = input("Backup recent projects list? (y/n, default=y): ").lower() != "n"
            backup_global = input("Backup global IDE settings? (y/n, default=n): ").lower() == "y"

            create_backup(
                projects_dir,
                output_file,
                output_dir,
                include_patterns,
                exclude_patterns,
                backup_recent,
                backup_global,
                False,
                logger
            )

        elif choice == "2":
            # Restore backup
            backups = list_backups(logger)
            if not backups:
                continue

            backup_choice = input("Enter backup number to use (or Enter to cancel): ")
            if not backup_choice:
                continue

            try:
                backup_file = backups[int(backup_choice) - 1]
            except (ValueError, IndexError):
                logger.error("Invalid selection")
                continue

            # List projects in the backup
            projects = list_projects_in_backup(backup_file, logger)
            if not projects:
                continue

            print("\nProjects in backup:")
            for i, proj in enumerate(projects, 1):
                print(f"{i}. {proj}")
            print(f"{len(projects) + 1}. All projects")

            proj_choice = input("Enter project number to restore (or Enter to cancel): ")
            if not proj_choice:
                continue

            try:
                choice_num = int(proj_choice)
                if choice_num == len(projects) + 1:
                    project_to_restore = "all"
                else:
                    project_to_restore = projects[choice_num - 1]
            except (ValueError, IndexError):
                logger.error("Invalid selection")
                continue

            restore_recent = input("Also restore recent projects list? (y/n, default=n): ").lower() == "y"
            restore_global = input("Also restore global settings? (y/n, default=n): ").lower() == "y"
            dry_run = input("Perform a dry run first? (y/n, default=y): ").lower() != "n"
            show_diff = input("Show differences before restoring? (y/n, default=n): ").lower() == "y"

            restore_projects(
                projects_dir,
                project_to_restore,
                backup_file,
                restore_recent,
                restore_global,
                dry_run,
                show_diff,
                logger
            )

            # If it was a dry run, ask if user wants to proceed with actual restore
            if dry_run:
                proceed = input("Proceed with actual restore? (y/n, default=y): ").lower()
                if proceed != "n":
                    restore_projects(
                        projects_dir,
                        project_to_restore,
                        backup_file,
                        restore_recent,
                        restore_global,
                        False,
                        False,
                        logger
                    )

        elif choice == "3":
            # List backups
            list_backups(logger)

        elif choice == "4":
            # Set projects directory
            new_dir = input(f"Enter projects directory (current: {projects_dir}): ")
            if new_dir and os.path.isdir(new_dir):
                projects_dir = new_dir
                logger.info(f"Projects directory set to: {projects_dir}")
            else:
                logger.error("Invalid directory")

        elif choice == "5":
            # Set output directory
            new_dir = input(f"Enter output directory (current: {output_dir}): ")
            if new_dir:
                if os.path.isdir(new_dir):
                    output_dir = new_dir
                    logger.info(f"Output directory set to: {output_dir}")
                else:
                    try:
                        os.makedirs(new_dir)
                        output_dir = new_dir
                        logger.info(f"Created and set output directory to: {output_dir}")
                    except Exception as e:
                        logger.error(f"Failed to create directory: {str(e)}")
            else:
                logger.error("Invalid directory")

        elif choice == "6":
            # Restore recent projects list
            backups = list_backups(logger)
            if not backups:
                continue

            backup_choice = input("Enter backup number to use (or Enter to cancel): ")
            if not backup_choice:
                continue

            try:
                backup_file = backups[int(backup_choice) - 1]
                dry_run = input("Perform a dry run first? (y/n, default=y): ").lower() != "n"

                restore_recent_projects(backup_file, dry_run, logger)

                if dry_run:
                    proceed = input("Proceed with actual restore? (y/n, default=y): ").lower()
                    if proceed != "n":
                        restore_recent_projects(backup_file, False, logger)

            except (ValueError, IndexError):
                logger.error("Invalid selection")

        elif choice == "7":
            # Restore global settings
            backups = list_backups(logger)
            if not backups:
                continue

            backup_choice = input("Enter backup number to use (or Enter to cancel): ")
            if not backup_choice:
                continue

            try:
                backup_file = backups[int(backup_choice) - 1]
                dry_run = input("Perform a dry run first? (y/n, default=y): ").lower() != "n"

                restore_global_settings(backup_file, dry_run, logger)

                if dry_run:
                    proceed = input("Proceed with actual restore? (y/n, default=y): ").lower()
                    if proceed != "n":
                        restore_global_settings(backup_file, False, logger)

            except (ValueError, IndexError):
                logger.error("Invalid selection")

        elif choice == "8":
            # Exit
            break

        else:
            logger.error("Invalid choice")


def load_config() -> Dict:
    """Load configuration from config file.

    Returns:
        Dictionary containing configuration values.
    """
    config = {}
    config_file = os.path.expanduser("~/.pycharmbackuprc")

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except Exception:
            # If config file is invalid, use defaults
            pass

    return config


def save_config(config: Dict) -> None:
    """Save configuration to config file.

    Args:
        config: Dictionary containing configuration values to save.
    """
    config_file = os.path.expanduser("~/.pycharmbackuprc")

    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save configuration: {str(e)}")


def main() -> None:
    """Process command line arguments and execute the requested operation."""
    # Load configuration
    config = load_config()

    parser = argparse.ArgumentParser(
        description="PyCharm Project Configuration Backup Tool"
    )

    # Main operation group (mutually exclusive)
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-b", "--backup", action="store_true",
        help="Backup configuration files"
    )

    group.add_argument(
        "-r", "--restore-project", metavar="PROJECT_NAME",
        help="Restore configuration for a specific project (or 'all' for all projects)"
    )

    group.add_argument(
        "-l", "--list-backups", action="store_true",
        help="List available backups"
    )

    group.add_argument(
        "-i", "--interactive", action="store_true",
        help="Run in interactive mode with a menu"
    )

    group.add_argument(
        "--restore-recent-only", action="store_true",
        help="Restore only the recent projects list files"
    )

    group.add_argument(
        "--restore-global-only", action="store_true",
        help="Restore only the global IDE settings"
    )

    # Common options
    parser.add_argument(
        "-p", "--pycharm-projects-directory",
        help="Directory containing PyCharm projects (defaults to OS-specific location)"
    )

    parser.add_argument(
        "-o", "--output-directory", default=os.getcwd(),
        help="Directory where backups will be stored (default: current working directory)"
    )

    parser.add_argument(
        "--output-file",
        help="Custom filename for the backup (default: pycharm_idea_backup_MM_DD_YYYY.zip)"
    )

    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )

    parser.add_argument(
        "--show-diff", action="store_true",
        help="Show differences. Forces dry-run"
    )

    parser.add_argument(
        "--include",
        help="Comma-separated list of patterns to include (e.g., '*.xml,*.iml')"
    )

    parser.add_argument(
        "--exclude",
        help="Comma-separated list of patterns to exclude (e.g., 'workspace.xml')"
    )

    parser.add_argument(
        "--max-backups", type=int, default=config.get("max_backups", 0),
        help="Maximum number of backups to keep (0 = keep all)"
    )

    # Recent projects backup options
    parser.add_argument(
        "-rp", "--recent-projects-backup", action="store_true", default=True,
        help="Include recent projects list files in backup (default: True)"
    )

    parser.add_argument(
        "--no-recent-projects-backup", action="store_false", dest="recent_projects_backup",
        help="Exclude recent projects list files from backup"
    )

    # Global settings backup options
    parser.add_argument(
        "-gs", "--global-settings-backup", action="store_true", default=False,
        help="Include global IDE settings in backup (default: False)"
    )

    # Restore options
    parser.add_argument(
        "--restore-recent", action="store_true", default=False,
        help="Also restore recent projects list when restoring project (default: False)"
    )

    parser.add_argument(
        "--restore-global", action="store_true", default=False,
        help="Also restore global IDE settings when restoring project (default: False)"
    )

    # Comprehensive backup
    parser.add_argument(
        "--comprehensive", action="store_true",
        help="Perform comprehensive backup including projects, recent lists, and global settings"
    )

    # Logging options
    parser.add_argument(
        "--log-file",
        help="Log to the specified file"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress normal output (errors will still be displayed)"
    )

    args = parser.parse_args()

    if args.show_diff:
        args.dry_run = True

    # Set up logging
    log_level = logging.ERROR if args.quiet else (logging.DEBUG if args.verbose else logging.INFO)
    logger = setup_logging(args.log_file, args.verbose)

    # Use default projects directory if not specified
    if not args.pycharm_projects_directory and (args.backup or args.restore_project):
        args.pycharm_projects_directory = get_default_projects_dir()
        logger.debug(f"Using default projects directory: {args.pycharm_projects_directory}")

    # Process include/exclude patterns
    include_patterns = args.include.split(",") if args.include else None
    exclude_patterns = args.exclude.split(",") if args.exclude else None

    # Apply comprehensive backup settings
    if args.comprehensive:
        args.recent_projects_backup = True
        args.global_settings_backup = True

    # Save configuration for future use if specified
    if args.pycharm_projects_directory != config.get("projects_dir") and args.pycharm_projects_directory:
        config["projects_dir"] = args.pycharm_projects_directory
        save_config(config)

    if args.max_backups != config.get("max_backups"):
        config["max_backups"] = args.max_backups
        save_config(config)

    # Run in interactive mode if requested
    if args.interactive:
        interactive_mode(logger)
        return

    # Execute requested operation
    if args.backup:
        if not args.pycharm_projects_directory:
            parser.error("Projects directory is required for backup operation")

        create_backup(
            args.pycharm_projects_directory,
            args.output_file,
            args.output_directory,
            include_patterns,
            exclude_patterns,
            args.recent_projects_backup,
            args.global_settings_backup,
            args.dry_run,
            logger
        )

        # Clean up old backups if max_backups is set
        if args.max_backups > 0:
            clean_old_backups(args.max_backups, logger)

    elif args.restore_project:
        if not args.pycharm_projects_directory:
            parser.error("Projects directory is required for restore operation")

        restore_projects(
            args.pycharm_projects_directory,
            args.restore_project,
            args.output_file,  # Using output_file param for backup file path if specified
            args.restore_recent,
            args.restore_global,
            args.dry_run,
            args.show_diff,
            logger
        )

    elif args.restore_recent_only:
        # Only restore recent projects lists
        if not args.output_file:
            backups = list_backups(logger)
            if not backups:
                logger.error("No backups found")
                return

            backup_choice = input("Enter backup number to use for restore: ")
            try:
                backup_file = backups[int(backup_choice) - 1]
            except (ValueError, IndexError):
                logger.error("Invalid selection")
                return
        else:
            backup_file = args.output_file

        restore_recent_projects(backup_file, args.dry_run, logger)

    elif args.restore_global_only:
        # Only restore global IDE settings
        if not args.output_file:
            backups = list_backups(logger)
            if not backups:
                logger.error("No backups found")
                return

            backup_choice = input("Enter backup number to use for restore: ")
            try:
                backup_file = backups[int(backup_choice) - 1]
            except (ValueError, IndexError):
                logger.error("Invalid selection")
                return
        else:
            backup_file = args.output_file

        restore_global_settings(backup_file, args.dry_run, logger)

    elif args.list_backups:
        list_backups(logger)

    else:
        # If no operation specified, show help
        parser.print_help()


if __name__ == "__main__":
    main()