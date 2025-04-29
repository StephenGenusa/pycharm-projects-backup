#!/usr/bin/env python3
"""PyCharm Projects Backup Utility.

This script creates a backup of PyCharm projects by including only necessary
development files and excluding unnecessary or large files by default.
It includes features like module detection, progress tracking, compression options,
backup profiles, restore functionality, project filtering, dry run mode,
logging options, and post-backup actions.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Set, Optional, Union, Dict, Tuple, Any, Callable

try:
    from tqdm import tqdm
    tqdm_available = True
except ImportError:
    tqdm_available = False

try:
    from colorama import init, Fore, Style
    colorama_available = True
except ImportError:
    colorama_available = False

# Configure logging
logger = logging.getLogger("pycharm_backup")

# Constants
DEFAULT_CONFIG_DIR = Path.home() / ".pycharm_backup"
DEFAULT_PROFILE_PATH = DEFAULT_CONFIG_DIR / "profiles.json"
DEFAULT_PROFILE_NAME = "default"
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"
DEFAULT_BACKUP_DIR = DEFAULT_CONFIG_DIR / "backups"


class ColorFormatter:
    """Handles color formatting for terminal output."""

    @staticmethod
    def init_colors():
        """Initialize colorama if available."""
        if colorama_available:
            init()

    @staticmethod
    def color_text(text, color=None, style=None):
        """Return colored text if colorama is available."""
        if not colorama_available:
            return text

        color_code = getattr(Fore, color.upper()) if color else ''
        style_code = getattr(Style, style.upper()) if style else ''

        return f"{color_code}{style_code}{text}{Style.RESET_ALL}"

    @staticmethod
    def print_status(message, color="white", style=None):
        """Print a status message with color."""
        print(ColorFormatter.color_text(message, color=color, style=style))


class LoggingManager:
    """Manages logging configuration and operations."""

    @staticmethod
    def setup_logging(log_file=None, log_level=logging.INFO, console_level=logging.WARNING):
        """Set up logging configuration.

        Args:
            log_file: Path to log file (optional)
            log_level: Logging level for file
            console_level: Logging level for console

        Returns:
            logging.Logger: Configured logger
        """
        # Configure the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # Capture all levels

        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Create formatters
        detailed_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        simple_formatter = logging.Formatter('%(levelname)s: %(message)s')

        # Setup console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)

        # Setup file handler if specified
        if log_file:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(detailed_formatter)
            root_logger.addHandler(file_handler)

        return root_logger


class FilePatternMatcher:
    """Manages file pattern matching and filtering."""

    @staticmethod
    def is_module_directory(directory: Path) -> bool:
        """Check if a directory is a Python module directory.

        A directory is considered a module if it contains an __init__.py file.

        Args:
            directory: The directory to check

        Returns:
            bool: True if the directory is a Python module
        """
        return (directory / "__init__.py").exists()

    @staticmethod
    def is_important_file(filepath: Path, include_venv: bool) -> bool:
        """Check if a file is important for project backup.

        Args:
            filepath: Path object of the file to check
            include_venv: Whether to include virtualenv files

        Returns:
            bool: True if the file should be included in backup
        """
        # Define file extensions and names that are important to backup
        important_extensions = {
            '.py', '.json', '.yml', '.yaml', '.md', '.txt', '.ini', '.cfg',
            '.toml', '.html', '.css', '.js', '.xml', '.iml', '.gitignore',
            '.sql', '.rst', '.sh', '.bat', '.ps1', '.ipynb', '.java', '.properties',
            '.gradle', '.dart', '.kt', '.kts', '.tsx', '.ts', '.jsx'
        }

        important_filenames = {
            'requirements.txt', 'Pipfile', 'Pipfile.lock', 'pyproject.toml',
            'setup.py', 'setup.cfg', 'README.md', '.env.example', '.gitignore',
            'Dockerfile', 'docker-compose.yml', 'Makefile', 'LICENSE', '.flake8',
            'poetry.lock', 'package.json', 'package-lock.json', 'tsconfig.json',
            '.prettierrc', '.eslintrc', 'tox.ini', '.coveragerc', '.babelrc',
            'webpack.config.js', 'vue.config.js', 'angular.json', 'build.gradle'
        }

        # Check if file extension is in the list of important extensions
        if filepath.suffix.lower() in important_extensions:
            return True

        # Check if filename is in the list of important filenames
        if filepath.name in important_filenames:
            return True

        return False

    @staticmethod
    def is_excluded_dir(dirname: str, include_venv: bool, custom_excludes: Set[str]) -> bool:
        """Check if a directory should be excluded from backup.

        Args:
            dirname: Name of the directory
            include_venv: Whether to include virtualenv directories
            custom_excludes: Set of custom exclusion patterns

        Returns:
            bool: True if the directory should be excluded
        """
        # Common directories to exclude
        excluded_dirs = {
            '__pycache__', '.git', '.idea', 'dist', 'build', 'node_modules',
            'data', 'logs', 'temp', 'tmp', '.pytest_cache', '.mypy_cache',
            '.ipynb_checkpoints', 'output', 'downloads', 'coverage', 'htmlcov'
        }

        # Exclude venv directories if not explicitly included
        venv_dirs = {'venv', '.venv', 'env', '.env', 'virtualenv'}

        if not include_venv:
            excluded_dirs.update(venv_dirs)

        # Check if directory should be excluded based on default rules
        if dirname in excluded_dirs:
            return True

        # Check if directory matches any custom exclusion pattern
        for exclude_pattern in custom_excludes:
            if exclude_pattern in dirname:
                return True

        return False

    @staticmethod
    def should_exclude_file(filepath: Path, custom_excludes: Set[str]) -> bool:
        """Check if a file should be excluded based on custom exclusion patterns.

        Args:
            filepath: Path object of the file
            custom_excludes: Set of custom exclusion patterns

        Returns:
            bool: True if the file should be excluded
        """
        for exclude_pattern in custom_excludes:
            if exclude_pattern in str(filepath):
                return True
        return False

    @staticmethod
    def is_in_include_paths(rel_path: Path, include_paths: List[str]) -> bool:
        """Check if a path matches any of the include paths.

        Args:
            rel_path: Relative path to check
            include_paths: List of paths to include

        Returns:
            bool: True if the path should be included
        """
        if not include_paths:
            return False

        str_path = str(rel_path).replace('\\', '/')
        for include_path in include_paths:
            include_path = include_path.replace('\\', '/')
            if str_path.startswith(include_path):
                return True
        return False

    @staticmethod
    def find_all_modules(project_dir: Path) -> List[Path]:
        """Find all Python module directories in a project.

        Args:
            project_dir: The project directory to scan

        Returns:
            List[Path]: List of module directories
        """
        modules = []

        for root, dirs, files in os.walk(project_dir):
            root_path = Path(root)

            # Skip common directories to exclude
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', '.git', '.idea', 'dist', 'build', 'node_modules',
                'data', 'logs', 'temp', 'tmp', '.pytest_cache', '.mypy_cache',
                '.ipynb_checkpoints', 'output', 'downloads', 'coverage', 'htmlcov',
                'venv', '.venv', 'env', '.env', 'virtualenv'
            }]

            # Check if current directory is a module
            if FilePatternMatcher.is_module_directory(root_path):
                modules.append(root_path)

        return modules


class ProjectUtils:
    """Utilities for working with PyCharm projects."""

    @staticmethod
    def get_default_pycharm_dir() -> Path:
        """Determine the default PyCharm projects directory by checking configuration files.

        This function tries to detect the PyCharm projects directory from:
        1. Windows registry (Windows)
        2. JetBrains configuration directory (all platforms)
        3. Default locations based on OS

        Returns:
            Path: The path to the default PyCharm projects directory
        """
        # Check environment variable first (useful for custom setups)
        env_projects_dir = os.environ.get('PYCHARM_PROJECTS')
        if env_projects_dir and Path(env_projects_dir).exists():
            logger.debug(f"Using PyCharm projects directory from environment variable: {env_projects_dir}")
            return Path(env_projects_dir)

        # Platform-specific checks
        platform = sys.platform

        # Windows-specific detection
        if platform.startswith('win'):
            try:
                import winreg
                # Try to get path from registry
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\JetBrains\PyCharm") as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        name, value, _ = winreg.EnumValue(key, i)
                        if "recentProjectDirectories" in name or "lastProjectLocation" in name:
                            # Parse XML or string to get the path
                            matches = re.findall(r'[A-Z]:\\[^<>"]+', value)
                            if matches:
                                path = Path(matches[0])
                                if path.exists() and path.is_dir():
                                    logger.debug(f"Found PyCharm projects directory in registry: {path}")
                                    return path
            except (ImportError, FileNotFoundError, PermissionError, re.error):
                pass

        # Check JetBrains config directories on all platforms
        config_paths = []

        if platform.startswith('win'):
            # Windows: %APPDATA%\JetBrains\PyCharm*
            config_paths.append(Path(os.environ.get('APPDATA', '')) / "JetBrains")
        elif platform.startswith('darwin'):
            # macOS: ~/Library/Application Support/JetBrains/PyCharm*
            config_paths.append(Path.home() / "Library" / "Application Support" / "JetBrains")
            # macOS: ~/Library/Preferences/PyCharm*
            config_paths.append(Path.home() / "Library" / "Preferences")
        else:
            # Linux: ~/.config/JetBrains/PyCharm*
            config_paths.append(Path.home() / ".config" / "JetBrains")
            # Linux: ~/.PyCharm*/config
            for item in Path.home().glob(".PyCharm*"):
                if item.is_dir():
                    config_paths.append(item / "config")

        # Check config directories for project paths
        for config_path in config_paths:
            if not config_path.exists():
                continue

            # Look for directories matching PyCharm* pattern
            for pycharm_dir in config_path.glob("*[pP]y[cC]harm*"):
                if not pycharm_dir.is_dir():
                    continue

                # Try to find options directory with options.xml or other.xml
                options_dir = pycharm_dir / "options"

                # Check various option files that might contain project directory info
                option_files = ["options.xml", "other.xml", "recentProjects.xml", "workspace.xml"]
                for option_file in option_files:
                    file_path = options_dir / option_file
                    if not file_path.exists():
                        continue

                    try:
                        content = file_path.read_text(encoding='utf-8')

                        # Look for project directories in the content
                        patterns = [
                            r'PROJECT_DIRECTORY="([^"]+)"',
                            r'<option name="defaultProject[^>]+>([^<]+)',
                            r'<option[^>]+path="([^"]+)"',
                            r'<entry key="project.default.dir" value="([^"]+)"'
                        ]

                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                path = Path(match.strip())
                                if path.exists() and path.is_dir() and list(path.glob("*")):  # Check if dir has files
                                    logger.debug(f"Found PyCharm projects directory in config: {path}")
                                    return path
                    except (UnicodeDecodeError, PermissionError):
                        continue

        # Fall back to OS-specific default locations
        if platform.startswith('win'):
            default_dir = Path(os.environ.get('USERPROFILE', '')) / "PycharmProjects"
        elif platform.startswith('darwin'):  # macOS
            default_dir = Path.home() / "PycharmProjects"
        else:  # Linux and other Unix-like
            default_dir = Path.home() / "PycharmProjects"

        if default_dir.exists() and default_dir.is_dir():
            logger.debug(f"Using default PyCharm projects directory: {default_dir}")
            return default_dir

        # Create default directory if it doesn't exist
        logger.debug(f"Creating default PyCharm projects directory: {default_dir}")
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    @staticmethod
    def get_project_dirs(pycharm_dir: Path, include_projects: List[str], exclude_projects: List[str]) -> Dict[
        str, Path]:
        """Get dictionary of project names and directories to backup.

        Args:
            pycharm_dir: Path to PyCharm projects directory
            include_projects: List of project names to include (empty means all)
            exclude_projects: List of project names to exclude

        Returns:
            Dict[str, Path]: Dictionary of project names and their paths
        """
        result = {}
        if not pycharm_dir.exists():
            return result

        # Get all subdirectories in the PyCharm directory
        for item in pycharm_dir.iterdir():
            if item.is_dir():
                project_name = item.name

                # Skip if not in include list (when include list is provided)
                if include_projects and project_name not in include_projects:
                    logger.info(f"Skipping project '{project_name}' - not in include list")
                    continue

                # Skip if in exclude list
                if project_name in exclude_projects:
                    logger.info(f"Skipping project '{project_name}' - in exclude list")
                    continue

                result[project_name] = item

        return result

    @staticmethod
    def get_total_dirs_and_files(project_dirs: Dict[str, Path]) -> Tuple[int, int]:
        """Calculate the total number of directories and files for progress tracking.

        Args:
            project_dirs: Dictionary of project names and paths

        Returns:
            Tuple[int, int]: Total number of directories and files
        """
        total_dirs = len(project_dirs)
        total_files = 0

        for _, project_path in project_dirs.items():
            for _, _, files in os.walk(project_path):
                total_files += len(files)

        return total_dirs, total_files

    @staticmethod
    def parse_size(size_str: str) -> int:
        """Convert a human-readable size string to bytes.

        Args:
            size_str: Size string like "20MB" or "1GB"

        Returns:
            int: Size in bytes

        Raises:
            ValueError: If the size string format is invalid
        """
        size_str = size_str.upper().strip()
        if size_str.isdigit():
            return int(size_str)

        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 * 1024,
            'GB': 1024 * 1024 * 1024,
            'TB': 1024 * 1024 * 1024 * 1024,
        }

        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    value = float(size_str[:-len(unit)])
                    return int(value * multiplier)
                except ValueError:
                    pass

        raise ValueError(f"Invalid size format: {size_str}. Use formats like '20MB', '1GB', etc.")


class ProfileManager:
    """Manages backup profile operations."""

    @staticmethod
    def ensure_dir_exists(directory: Path):
        """Ensure a directory exists, creating it if needed."""
        directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_backup_profiles() -> Dict[str, Dict[str, Any]]:
        """Load backup profiles from the profiles.json file.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary of profile names and their settings
        """
        if not DEFAULT_PROFILE_PATH.exists():
            return {}

        try:
            with open(DEFAULT_PROFILE_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading profiles: {str(e)}")
            return {}

    @staticmethod
    def save_backup_profile(profile_name: str, settings: Dict[str, Any]) -> bool:
        """Save a backup profile to the profiles.json file.

        Args:
            profile_name: Name of the profile
            settings: Dictionary of profile settings

        Returns:
            bool: True if profile was saved successfully
        """
        # Ensure the config directory exists
        ProfileManager.ensure_dir_exists(DEFAULT_CONFIG_DIR)

        # Load existing profiles
        profiles = ProfileManager.load_backup_profiles()

        # Update or add the profile
        profiles[profile_name] = settings

        try:
            with open(DEFAULT_PROFILE_PATH, 'w') as f:
                json.dump(profiles, f, indent=2)
            logger.info(f"Profile '{profile_name}' saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving profile: {str(e)}")
            return False

    @staticmethod
    def create_default_profile(pycharm_dir: Path) -> bool:
        """Create a default backup profile.

        Args:
            pycharm_dir: Path to the PyCharm projects directory

        Returns:
            bool: True if profile was created successfully
        """
        if not pycharm_dir.exists():
            logger.error(f"PyCharm projects directory '{pycharm_dir}' not found.")
            ColorFormatter.print_status(f"Error: PyCharm projects directory '{pycharm_dir}' not found.", color="red")
            return False

        # Get all project names
        project_names = []
        for item in pycharm_dir.iterdir():
            if item.is_dir():
                project_names.append(item.name)

        # Create default profile
        default_profile = {
            "pycharm_dir": str(pycharm_dir),
            "include_venv": False,
            "exclude_dirs": ["logs", "temp", "data"],
            "include_paths": [],
            "include_projects": project_names,  # Include all projects by default
            "exclude_projects": [],
            "max_size_to_include": "20MB",
            "compression_level": 9,
            "auto_include_modules": True,
            "post_backup_actions": []
        }

        # Save the profile
        return ProfileManager.save_backup_profile(DEFAULT_PROFILE_NAME, default_profile)


class PostBackupActions:
    """Handles post-backup actions and commands."""

    @staticmethod
    def execute_post_backup_action(command: str, output_path: Path) -> bool:
        """Execute a post-backup action/command.

        Args:
            command: Command to execute
            output_path: Path to the backup file

        Returns:
            bool: True if command executed successfully
        """
        try:
            # Replace placeholders in command
            command = command.replace("{backup_file}", str(output_path))
            command = command.replace("{date}", datetime.now().strftime("%Y-%m-%d"))
            command = command.replace("{time}", datetime.now().strftime("%H-%M-%S"))

            # Run the command
            logger.info(f"Executing post-backup action: {command}")
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Post-backup action failed: {result.stderr}")
                return False

            logger.info(f"Post-backup action completed successfully: {result.stdout}")
            return True
        except Exception as e:
            logger.error(f"Error executing post-backup action: {str(e)}")
            return False


class PyCharmBackupRestoreManager:
    """Main class for backup and restore operations."""

    def __init__(self):
        """Initialize the backup manager."""
        # Initialize colors
        ColorFormatter.init_colors()

    def backup(self,
               pycharm_dir: Path,
               output_path: Path,
               include_venv: bool = False,
               custom_excludes: Optional[Set[str]] = None,
               max_size_bytes: int = 20 * 1024 * 1024,  # Default 20MB
               include_paths: Optional[List[str]] = None,
               include_projects: Optional[List[str]] = None,
               exclude_projects: Optional[List[str]] = None,
               compress_level: int = 9,
               dry_run: bool = False,
               auto_include_modules: bool = True,
               post_backup_actions: Optional[List[str]] = None
               ) -> bool:
        """Create a zip backup of important project files.

        Args:
            pycharm_dir: Path to the PyCharm projects directory
            output_path: Path to the output zip file
            include_venv: Whether to include virtualenv files
            custom_excludes: Set of custom exclusion patterns
            max_size_bytes: Maximum file size in bytes to include in backup
            include_paths: List of specific paths to include
            include_projects: List of specific project names to include
            exclude_projects: List of project names to exclude
            compress_level: ZIP compression level (0-9, 9 being maximum)
            dry_run: If True, don't actually create the backup, just simulate
            auto_include_modules: Whether to automatically detect and include module directories
            post_backup_actions: List of commands to execute after successful backup

        Returns:
            bool: True if backup was successful
        """
        if custom_excludes is None:
            custom_excludes = set()

        if include_paths is None:
            include_paths = []

        if include_projects is None:
            include_projects = []

        if exclude_projects is None:
            exclude_projects = []

        if post_backup_actions is None:
            post_backup_actions = []

        if not pycharm_dir.exists():
            logger.error(f"PyCharm projects directory '{pycharm_dir}' not found.")
            ColorFormatter.print_status(f"Error: PyCharm projects directory '{pycharm_dir}' not found.", color="red")
            return False

        # Create output directory if it doesn't exist and not in dry_run mode
        if not dry_run:
            output_dir = output_path.parent
            if output_dir != Path('.'):
                output_dir.mkdir(parents=True, exist_ok=True)

        # Special handling for venv files - only include these key files if venv is included
        venv_important_files = [
            'pyvenv.cfg',
            'requirements.txt',
            Path('Scripts') / 'activate',
            Path('Scripts') / 'activate.bat',
            Path('Scripts') / 'Activate.ps1',
            Path('bin') / 'activate',
        ]

        # Statistics for reporting
        stats = {
            'included_files': 0,
            'excluded_size': 0,
            'excluded_count': 0,
            'included_custom_paths': 0,
            'included_modules': 0
        }

        # Get projects to process
        project_dirs = ProjectUtils.get_project_dirs(pycharm_dir, include_projects, exclude_projects)

        # Module paths to include
        module_paths = []

        # In dry run mode, we'll just simulate
        if dry_run:
            ColorFormatter.print_status("\n--- DRY RUN MODE - No backup will be created ---", color="yellow")

        # Prepare progress bar
        total_dirs, total_files = ProjectUtils.get_total_dirs_and_files(project_dirs)
        progress_desc = "Preparing backup"

        if tqdm_available and not dry_run:
            # Create a progress bar with 0 initial total, we'll update it as we scan
            pbar = tqdm(total=0, desc=progress_desc, unit="file")
        else:
            pbar = None

        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED,
                                 compresslevel=compress_level) if not dry_run else contextlib.nullcontext() as zipf:
                # Process each project
                for project_name, project_dir in project_dirs.items():
                    # Update progress bar description
                    if pbar:
                        pbar.set_description(f"Processing {project_name}")
                    else:
                        ColorFormatter.print_status(f"Processing {project_name}...", color="cyan")

                    # Auto-detect module directories if requested
                    if auto_include_modules:
                        project_modules = FilePatternMatcher.find_all_modules(project_dir)
                        for module_dir in project_modules:
                            rel_path = module_dir.relative_to(pycharm_dir)
                            module_paths.append(str(rel_path))
                            stats['included_modules'] += 1
                            logger.info(f"Auto-detected module: {rel_path}")

                    # Walk through the project directory
                    for root, dirs, files in os.walk(project_dir):
                        root_path = Path(root)

                        # Get relative path from the pycharm_dir
                        rel_path = root_path.relative_to(pycharm_dir)

                        # Check if this path should be included due to include_paths or modules
                        path_explicitly_included = (
                                FilePatternMatcher.is_in_include_paths(rel_path, include_paths) or
                                FilePatternMatcher.is_in_include_paths(rel_path, module_paths)
                        )

                        # Don't filter out directories that match include paths
                        if not path_explicitly_included:
                            # Filter out directories to exclude
                            dirs[:] = [d for d in dirs
                                       if not FilePatternMatcher.is_excluded_dir(d, include_venv, custom_excludes) or
                                       FilePatternMatcher.is_in_include_paths(rel_path / d, include_paths) or
                                       FilePatternMatcher.is_in_include_paths(rel_path / d, module_paths)]

                        # Check if we're in a venv directory
                        in_venv = any(venv_dir in root_path.parts
                                      for venv_dir in ['venv', '.venv', 'env', '.env'])

                        for file in files:
                            file_path = root_path / file
                            zip_path = rel_path / file

                            # Update progress bar
                            if pbar:
                                pbar.update(1)

                            # Always include files from specified include paths or module paths
                            if path_explicitly_included:
                                # Skip if file matches custom exclusion pattern
                                if FilePatternMatcher.should_exclude_file(file_path, custom_excludes):
                                    continue

                                # Check file size
                                try:
                                    file_size = file_path.stat().st_size
                                    if file_size > max_size_bytes:
                                        stats['excluded_size'] += file_size
                                        stats['excluded_count'] += 1
                                        logger.info(
                                            f"Skipped (too large): {zip_path} ({file_size / (1024 * 1024):.2f} MB)")
                                        if not pbar:
                                            ColorFormatter.print_status(
                                                f"Skipped (too large): {zip_path} ({file_size / (1024 * 1024):.2f} MB)",
                                                color="yellow")
                                        continue
                                except Exception as e:
                                    logger.warning(f"Error checking file size for {file_path}: {str(e)}")
                                    continue

                                # Add file to zip
                                if not dry_run:
                                    try:
                                        zipf.write(file_path, zip_path)
                                    except Exception as e:
                                        logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                                        continue

                                stats['included_files'] += 1
                                stats['included_custom_paths'] += 1
                                logger.debug(f"Added (custom path): {zip_path}")
                                if not pbar:
                                    ColorFormatter.print_status(f"Added (custom path): {zip_path}", color="green")
                                continue

                            # For regular processing, skip if file matches custom exclusion pattern
                            if FilePatternMatcher.should_exclude_file(file_path, custom_excludes):
                                continue

                            # Check file size
                            try:
                                file_size = file_path.stat().st_size
                                if file_size > max_size_bytes:
                                    stats['excluded_size'] += file_size
                                    stats['excluded_count'] += 1
                                    logger.info(f"Skipped (too large): {zip_path} ({file_size / (1024 * 1024):.2f} MB)")
                                    if not pbar:
                                        ColorFormatter.print_status(
                                            f"Skipped (too large): {zip_path} ({file_size / (1024 * 1024):.2f} MB)",
                                            color="yellow")
                                    continue
                            except Exception as e:
                                logger.warning(f"Error checking file size for {file_path}: {str(e)}")
                                continue

                            # If we're in a venv directory and the venv flag is set
                            if in_venv and include_venv:
                                # For venv directories, only include specific files
                                for venv_file in venv_important_files:
                                    if file_path.match(f"*{venv_file}*"):
                                        if not dry_run:
                                            try:
                                                zipf.write(file_path, zip_path)
                                            except Exception as e:
                                                logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                                                break
                                        stats['included_files'] += 1
                                        logger.debug(f"Added: {zip_path}")
                                        if not pbar:
                                            ColorFormatter.print_status(f"Added: {zip_path}", color="cyan")
                                        break
                            # Otherwise, check if it's an important file based on extension/name
                            elif FilePatternMatcher.is_important_file(Path(file), include_venv):
                                if not dry_run:
                                    try:
                                        zipf.write(file_path, zip_path)
                                    except Exception as e:
                                        logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                                        continue
                                stats['included_files'] += 1
                                logger.debug(f"Added: {zip_path}")
                                if not pbar:
                                    ColorFormatter.print_status(f"Added: {zip_path}", color="cyan")

                # Close the progress bar
                if pbar:
                    pbar.close()

                # Print summary
                ColorFormatter.print_status("\nBackup Summary:", color="magenta", style="bright")
                ColorFormatter.print_status(f"- Files included: {stats['included_files']}", color="magenta")
                ColorFormatter.print_status(f"- Files from custom paths: {stats['included_custom_paths']}",
                                            color="magenta")
                ColorFormatter.print_status(f"- Auto-detected modules: {stats['included_modules']}", color="magenta")
                ColorFormatter.print_status(f"- Files excluded due to size: {stats['excluded_count']}", color="magenta")
                ColorFormatter.print_status(
                    f"- Data saved by size exclusion: {stats['excluded_size'] / (1024 * 1024):.2f} MB", color="magenta")

                if not dry_run:
                    ColorFormatter.print_status(f"\nBackup file created: {output_path}", color="green", style="bright")

                    # Execute post-backup actions
                    if post_backup_actions:
                        ColorFormatter.print_status("\nExecuting post-backup actions:", color="cyan")
                        for action in post_backup_actions:
                            success = PostBackupActions.execute_post_backup_action(action, output_path)
                            status = "Success" if success else "Failed"
                            ColorFormatter.print_status(f"- {action}: {status}",
                                                        color="green" if success else "red")
                else:
                    ColorFormatter.print_status("\nDry run completed. No backup file was created.", color="yellow",
                                                style="bright")

                return True

        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            ColorFormatter.print_status(f"Error creating backup: {str(e)}", color="red", style="bright")
            # Close the progress bar in case of error
            if pbar:
                pbar.close()
            return False

    def restore(self, backup_file: Path, extract_dir: Path, selected_projects: List[str] = None) -> bool:
        """Restore a backup file.

        Args:
            backup_file: Path to the backup file
            extract_dir: Directory to extract to
            selected_projects: List of project names to restore (None for all)

        Returns:
            bool: True if restore was successful
        """
        if not backup_file.exists():
            logger.error(f"Backup file '{backup_file}' not found.")
            ColorFormatter.print_status(f"Error: Backup file '{backup_file}' not found.", color="red")
            return False

        # Create extract directory if it doesn't exist
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract all files or specific projects
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                # Get list of all files in the zip
                all_files = zipf.namelist()

                # Get list of unique projects in the backup
                projects = set()
                for file_path in all_files:
                    parts = Path(file_path).parts
                    if parts:
                        projects.add(parts[0])

                # Filter projects if selection provided
                if selected_projects:
                    projects = {p for p in projects if p in selected_projects}
                    if not projects:
                        logger.error(f"None of the selected projects were found in the backup.")
                        ColorFormatter.print_status("Error: None of the selected projects were found in the backup.",
                                                    color="red")
                        return False

                # Setup progress bar
                project_files = [f for f in all_files if Path(f).parts and Path(f).parts[0] in projects]
                total_files = len(project_files)

                if tqdm_available:
                    pbar = tqdm(total=total_files, desc="Restoring backup", unit="file")
                else:
                    pbar = None

                # Print message about which projects are being restored
                ColorFormatter.print_status(f"Restoring {len(projects)} project(s): {', '.join(sorted(projects))}",
                                            color="cyan")

                # Extract each file
                for file_path in project_files:
                    if pbar:
                        pbar.update(1)

                    # Skip files not in selected projects
                    path_obj = Path(file_path)
                    if path_obj.parts and path_obj.parts[0] not in projects:
                        continue

                    # Extract the file
                    try:
                        zipf.extract(file_path, extract_dir)
                        logger.debug(f"Restored: {file_path}")
                    except Exception as e:
                        logger.error(f"Error extracting {file_path}: {str(e)}")
                        if not pbar:
                            ColorFormatter.print_status(f"Error extracting {file_path}: {str(e)}", color="red")

                # Close the progress bar
                if pbar:
                    pbar.close()

                ColorFormatter.print_status(f"\nRestore completed successfully to: {extract_dir}", color="green",
                                            style="bright")
                return True

        except Exception as e:
            logger.error(f"Error restoring backup: {str(e)}")
            ColorFormatter.print_status(f"Error restoring backup: {str(e)}", color="red", style="bright")
            return False


class HelpManager:
    """Manages help content and documentation display."""

    @staticmethod
    def print_help_and_exit():
        """Print detailed help documentation with colored text formatting."""
        ColorFormatter.init_colors()

        header = ColorFormatter.color_text("PyCharm Projects Backup Utility", color="cyan", style="bright")
        description = ColorFormatter.color_text(
            "This utility creates smart backups of PyCharm projects by selectively including essential "
            "development files while excluding unnecessary or large files. It helps create compact archives "
            "with just the code and configuration you need.",
            color="white"
        )

        section_title = lambda title: ColorFormatter.color_text(f"\n## {title}", color="yellow", style="bright")
        param_name = lambda name: ColorFormatter.color_text(name, color="green")
        command = lambda cmd: ColorFormatter.color_text(cmd, color="blue")
        note = lambda text: ColorFormatter.color_text(text, color="magenta")

        print(f"\n{header}\n")
        print(description)

        print(section_title("Usage"))
        print("\nIf run without any parameters, the program will show this help information.")
        print("\nBasic usage:")
        print(command("python backup_script.py -p /path/to/projects -o backup.zip"))

        print(section_title("Available Options"))

        print("\n" + param_name("Specify PyCharm Projects Directory"))
        print(command("python backup_script.py -p /path/to/projects"))
        print("or")
        print(command("python backup_script.py --pycharm-dir /path/to/projects"))

        print("\n" + param_name("Custom Output Location"))
        print(command("python backup_script.py -o /path/to/backup.zip"))
        print("or")
        print(command("python backup_script.py --output /path/to/backup.zip"))

        print("\n" + param_name("Include Virtual Environment Files"))
        print("By default, virtual environments are excluded. To include key virtualenv files:")
        print(command("python backup_script.py -v"))
        print("or")
        print(command("python backup_script.py --venv-include"))

        print("\n" + param_name("Exclude Specific Directories or Files"))
        print("You can specify patterns to exclude from the backup:")
        print(command("python backup_script.py -e logs temp"))
        print("or")
        print(command("python backup_script.py --exclude-dirs logs temp user_data"))

        print("\n" + param_name("Include Specific Paths"))
        print("Force inclusion of specific paths even if they would normally be excluded:")
        print(command("python backup_script.py -i venv/Lib/site-packages/mypackage"))
        print("or multiple paths:")
        print(command(
            "python backup_script.py --include-paths venv/Lib/site-packages/mypackage project1/data/sample_configs project2/special_files"))

        print("\n" + param_name("Include Specific Projects"))
        print("Backup only specific projects:")
        print(command("python backup_script.py --include-projects project1 project2"))

        print("\n" + param_name("Exclude Specific Projects"))
        print("Exclude specific projects from the backup:")
        print(command("python backup_script.py --exclude-projects old_project test_project"))

        print("\n" + param_name("Set Maximum File Size"))
        print("Control the maximum size of individual files to include:")
        print(command("python backup_script.py -m 50MB"))
        print("or")
        print(command("python backup_script.py --max-size-to-include 1GB"))
        print("Supported units: B, KB, MB, GB, TB")

        print("\n" + param_name("Control Compression Level"))
        print("Set the ZIP compression level (0-9, where 9 is maximum compression):")
        print(command("python backup_script.py -c 6"))
        print("or")
        print(command("python backup_script.py --compression-level 6"))

        print("\n" + param_name("Backup Profiles"))
        print("Create a named profile to save these settings:")
        print(command("python backup_script.py --create-profile my_profile"))
        print("\nUse a saved profile for backup:")
        print(command("python backup_script.py --use-profile my_profile"))
        print("\nCreate default profile with all projects:")
        print(command("python backup_script.py --create-default-profile"))
        print("\nList available profiles:")
        print(command("python backup_script.py --list-profiles"))

        print("\n" + param_name("Dry Run"))
        print("Simulate a backup without creating files:")
        print(command("python backup_script.py --dry-run"))

        print("\n" + param_name("Module Auto-Detection"))
        print("By default, the program automatically includes Python module directories.")
        print("To disable this feature:")
        print(command("python backup_script.py --no-auto-modules"))

        print("\n" + param_name("Restore Backup"))
        print("Restore a backup to a specified directory:")
        print(command("python backup_script.py --restore backup.zip --extract-dir /path/to/extract"))
        print("\nRestore only specific projects from backup:")
        print(command(
            "python backup_script.py --restore backup.zip --extract-dir /path/to/extract --restore-projects project1 project2"))

        print("\n" + param_name("Logging Options"))
        print("Control log levels and output:")
        print(command("python backup_script.py --log-file backup.log --log-level INFO"))

        print("\n" + param_name("Post-Backup Actions"))
        print("Execute commands after backup completes (use {backup_file} as placeholder for the output path):")
        print(command(
            "python backup_script.py --post-action \"cp {backup_file} /backup/\" --post-action \"echo Backup completed at {date} {time}\""))

        print(section_title("Examples"))

        print("\n" + param_name("Basic Backup with Default Settings"))
        print(command("python backup_script.py -p ~/PycharmProjects -o backup.zip"))

        print("\n" + param_name("Comprehensive Backup with Custom Settings"))
        print(command(
            "python backup_script.py -p /home/user/code/python_projects -o ~/backups/py_backup_2023.zip -v -m 30MB -c 9 -e logs temp test_data -i venv/Lib/site-packages/important_module project1/sample_data --include-projects project1 project2 --log-file backup.log --post-action \"echo Backup completed to {backup_file}\""))

        print("\n" + param_name("Using Profiles"))
        print("First create a profile:")
        print(command(
            "python backup_script.py --create-profile daily_backup -p ~/PycharmProjects -o ~/backups/daily_backup.zip -e logs temp data"))
        print("Then use it:")
        print(command("python backup_script.py --use-profile daily_backup"))

        print("\n" + param_name("Restore Example"))
        print(
            command("python backup_script.py --restore ~/backups/py_backup_2023.zip --extract-dir ~/restored_projects"))

        print(section_title("Understanding the Output"))

        print(
            "\nThe program provides real-time feedback on included and excluded files, and generates a summary when finished:")

        print(note("\nBackup Summary:"))
        print(note("- Files included: 425"))
        print(note("- Files from custom paths: 37"))
        print(note("- Auto-detected modules: 15"))
        print(note("- Files excluded due to size: 12"))
        print(note("- Data saved by size exclusion: 453.25 MB"))
        print(note("\nBackup file created: pycharm_backup_20230817_150432.zip"))

        sys.exit(0)


# Needed for the with statement in dry run mode
class contextlib:
    @staticmethod
    class nullcontext:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return None

        def __exit__(self, *args):
            pass


def main() -> None:
    """Main entry point for the script."""
    ColorFormatter.init_colors()

    parser = argparse.ArgumentParser(
        description="Backup PyCharm Projects with smart file selection"
    )

    # Basic options
    parser.add_argument(
        '-p', '--pycharm-dir',
        type=Path,
        default=ProjectUtils.get_default_pycharm_dir(),  # Set default directly here
        help='Path to the PyCharm Projects directory'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output zip file path'
    )

    parser.add_argument(
        '-v', '--venv-include',
        action='store_true',
        help='Include essential virtualenv files in the backup'
    )

    parser.add_argument(
        '-e', '--exclude-dirs',
        nargs='+',
        default=[],
        help='Directories or files to exclude (partial names supported)'
    )

    parser.add_argument(
        '-m', '--max-size-to-include',
        default='20MB',
        help='Maximum file size to include (e.g. 100MB, 1GB). Default: 20MB'
    )

    parser.add_argument(
        '-i', '--include-paths',
        nargs='+',
        default=[],
        help='Specific paths to include (relative to projects folder)'
    )

    # Project selection
    parser.add_argument(
        '--include-projects',
        nargs='+',
        default=[],
        help='Specific projects to include in the backup'
    )

    parser.add_argument(
        '--exclude-projects',
        nargs='+',
        default=[],
        help='Projects to exclude from the backup'
    )

    # Profile management
    parser.add_argument(
        '--create-profile',
        metavar='PROFILE_NAME',
        help='Create a named profile with current settings'
    )

    parser.add_argument(
        '--use-profile',
        metavar='PROFILE_NAME',
        help='Use a saved profile for backup'
    )

    parser.add_argument(
        '--create-default-profile',
        action='store_true',
        help='Create a default profile with all projects'
    )

    parser.add_argument(
        '--list-profiles',
        action='store_true',
        help='List available backup profiles'
    )

    # Compression options
    parser.add_argument(
        '-c', '--compression-level',
        type=int,
        choices=range(10),
        default=9,
        help='ZIP compression level (0-9, 9 being maximum)'
    )

    # Module detection
    parser.add_argument(
        '--no-auto-modules',
        action='store_true',
        help='Disable automatic module directory detection'
    )

    # Dry run option
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate backup without creating files'
    )

    # Restore functionality
    parser.add_argument(
        '--restore',
        type=Path,
        help='Restore from a backup file'
    )

    parser.add_argument(
        '--extract-dir',
        type=Path,
        help='Directory to extract restored backup'
    )

    parser.add_argument(
        '--restore-projects',
        nargs='+',
        help='Specific projects to restore from backup'
    )

    # Logging options
    parser.add_argument(
        '--log-file',
        type=str,
        help='Log file path (defaults to no file logging)'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Logging level'
    )

    # Post-backup actions
    parser.add_argument(
        '--post-action',
        action='append',
        dest='post_actions',
        default=[],
        help='Command to execute after backup (can be specified multiple times)'
    )

    # Help option
    parser.add_argument(
        '--help-detailed',
        action='store_true',
        help='Show detailed help with examples'
    )

    # If no arguments were provided, show help
    if len(sys.argv) == 1 or '--help-detailed' in sys.argv:
        HelpManager.print_help_and_exit()

    args = parser.parse_args()

    # Set up logging
    log_file = args.log_file
    log_level = getattr(logging, args.log_level)
    LoggingManager.setup_logging(log_file, log_level)

    # Create backup manager
    backup_manager = PyCharmBackupRestoreManager()

    # List profiles and exit
    if args.list_profiles:
        profiles = ProfileManager.load_backup_profiles()
        if profiles:
            ColorFormatter.print_status("Available backup profiles:", color="cyan", style="bright")
            for profile_name, profile_settings in profiles.items():
                ColorFormatter.print_status(f"- {profile_name}", color="green")
                for key, value in profile_settings.items():
                    ColorFormatter.print_status(f"  {key}: {value}", color="white")
                print()
        else:
            ColorFormatter.print_status("No backup profiles found.", color="yellow")
        return

    # Create default profile
    if args.create_default_profile:
        pycharm_dir = args.pycharm_dir or ProjectUtils.get_default_pycharm_dir()
        if ProfileManager.create_default_profile(pycharm_dir):
            ColorFormatter.print_status(f"Default profile '{DEFAULT_PROFILE_NAME}' created successfully!",
                                        color="green")
            ColorFormatter.print_status(f"Profile saved at: {DEFAULT_PROFILE_PATH}", color="cyan")
        else:
            ColorFormatter.print_status("Failed to create default profile.", color="red")
        return

    # Restore backup
    if args.restore:
        if not args.extract_dir:
            ColorFormatter.print_status("Error: --extract-dir is required with --restore", color="red")
            return

        backup_manager.restore(args.restore, args.extract_dir, args.restore_projects)
        return

    # Load profile if specified
    profile_settings = {}
    if args.use_profile:
        profiles = ProfileManager.load_backup_profiles()
        if args.use_profile not in profiles:
            ColorFormatter.print_status(f"Profile '{args.use_profile}' not found!", color="red")
            return

        profile_settings = profiles[args.use_profile]
        ColorFormatter.print_status(f"Using profile '{args.use_profile}'", color="cyan")

    # Determine effective settings, prioritizing command line arguments over profile settings
    pycharm_dir = args.pycharm_dir
    if 'pycharm_dir' in profile_settings and args.pycharm_dir == ProjectUtils.get_default_pycharm_dir():
        # Only use profile's pycharm_dir if user didn't explicitly specify one
        pycharm_dir = Path(profile_settings['pycharm_dir'])

    # Default timestamped output file if not specified
    if args.output:
        output_path = args.output
    elif 'output' in profile_settings:
        output_path = Path(profile_settings['output'])
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = Path(f"pycharm_backup_{timestamp}.zip")

    # Other settings with profile fallbacks
    include_venv = args.venv_include or profile_settings.get('include_venv', False)

    exclude_dirs = args.exclude_dirs
    if not exclude_dirs and 'exclude_dirs' in profile_settings:
        exclude_dirs = profile_settings['exclude_dirs']

    include_paths = args.include_paths
    if not include_paths and 'include_paths' in profile_settings:
        include_paths = profile_settings['include_paths']

    include_projects = args.include_projects
    if not include_projects and 'include_projects' in profile_settings:
        include_projects = profile_settings['include_projects']

    exclude_projects = args.exclude_projects
    if not exclude_projects and 'exclude_projects' in profile_settings:
        exclude_projects = profile_settings['exclude_projects']

    # Max file size
    max_size_to_include = args.max_size_to_include
    if not max_size_to_include and 'max_size_to_include' in profile_settings:
        max_size_to_include = profile_settings['max_size_to_include']

    try:
        max_size_bytes = ProjectUtils.parse_size(max_size_to_include)
    except ValueError as e:
        ColorFormatter.print_status(f"Error: {str(e)}", color="red")
        sys.exit(1)

    # Compression level
    compression_level = args.compression_level
    if args.compression_level == 9 and 'compression_level' in profile_settings:
        compression_level = profile_settings['compression_level']

    # Auto module detection
    auto_include_modules = not args.no_auto_modules
    if 'auto_include_modules' in profile_settings:
        auto_include_modules = profile_settings['auto_include_modules']

    # Post backup actions
    post_actions = args.post_actions
    if not post_actions and 'post_backup_actions' in profile_settings:
        post_actions = profile_settings['post_backup_actions']

    # Create a new profile if requested
    if args.create_profile:
        profile_to_save = {
            'pycharm_dir': str(pycharm_dir),
            'output': str(output_path),
            'include_venv': include_venv,
            'exclude_dirs': exclude_dirs,
            'include_paths': include_paths,
            'include_projects': include_projects,
            'exclude_projects': exclude_projects,
            'max_size_to_include': max_size_to_include,
            'compression_level': compression_level,
            'auto_include_modules': auto_include_modules,
            'post_backup_actions': post_actions
        }

        if ProfileManager.save_backup_profile(args.create_profile, profile_to_save):
            ColorFormatter.print_status(f"Profile '{args.create_profile}' created successfully!", color="green")
        else:
            ColorFormatter.print_status(f"Failed to create profile '{args.create_profile}'.", color="red")

    # Print summary of operations
    ColorFormatter.print_status("PyCharm Projects Backup Utility", color="cyan", style="bright")
    ColorFormatter.print_status("-" * 50, color="cyan")
    ColorFormatter.print_status(f"PyCharm Projects Directory: {pycharm_dir}", color="white")
    ColorFormatter.print_status(f"Output ZIP: {output_path}", color="white")
    ColorFormatter.print_status(f"Include venv files: {include_venv}", color="white")
    ColorFormatter.print_status(f"Maximum file size: {max_size_to_include} ({max_size_bytes:,} bytes)", color="white")
    ColorFormatter.print_status(f"Compression level: {compression_level}", color="white")
    ColorFormatter.print_status(f"Auto-detect modules: {auto_include_modules}", color="white")

    if exclude_dirs:
        ColorFormatter.print_status(f"Custom exclusions: {', '.join(exclude_dirs)}", color="white")
    if include_paths:
        ColorFormatter.print_status(f"Custom inclusions: {', '.join(include_paths)}", color="white")
    if include_projects:
        ColorFormatter.print_status(f"Included projects: {', '.join(include_projects)}", color="white")
    if exclude_projects:
        ColorFormatter.print_status(f"Excluded projects: {', '.join(exclude_projects)}", color="white")
    if post_actions:
        ColorFormatter.print_status(f"Post-backup actions: {len(post_actions)}", color="white")
    if args.dry_run:
        ColorFormatter.print_status("Mode: Dry run (no files will be created)", color="yellow")
    ColorFormatter.print_status("-" * 50, color="cyan")

    # Start backup process
    backup_manager.backup(
        pycharm_dir=pycharm_dir,
        output_path=output_path,
        include_venv=include_venv,
        custom_excludes=set(exclude_dirs),
        max_size_bytes=max_size_bytes,
        include_paths=include_paths,
        include_projects=include_projects,
        exclude_projects=exclude_projects,
        compress_level=compression_level,
        dry_run=args.dry_run,
        auto_include_modules=auto_include_modules,
        post_backup_actions=post_actions
    )


if __name__ == "__main__":
    main()