import os
import logging
import sys
import shutil
from datetime import datetime
from pathlib import Path
from View.Menu import cmd_top_logo
from Config import SERVICE_NAME

# For logging folder deletion
def delete_oldest_folder_if_limit_exceeded(limit=30):
    path = Path("Logs")
    # List only folders
    folders = [f for f in path.iterdir() if f.is_dir()]

    # Keep deleting the oldest folder until only `limit` folders remain
    while len(folders) > limit:
        # Find the oldest folder by last modified time
        oldest_folder = min(folders, key=lambda f: f.stat().st_mtime)

        try:
            shutil.rmtree(oldest_folder)
        except Exception as e:
            print(f"❌ Failed to delete folder {oldest_folder}: {e}")
            break  # Stop to avoid infinite loop on repeated error

        # Refresh the folder list
        folders = [f for f in path.iterdir() if f.is_dir()]

def logging_top_logo(title):
    padding = 2  # Space on each side inside the box
    size = len(title) + padding * 2
    border = '=' * (size + padding + 2)  # +2 for the '|' borders

    logging.info(border)
    logging.info(f'| {title.center(size)} |')
    logging.info(border)

def configure_log():
    # Get current date and time
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')  # e.g., "2025-05-14"
    time_str = now.strftime('%d_%m_%y (%H_%M_%S)')  # e.g., "14_05_25 16_01_30"

    # Set up directories
    log_base_dir = os.path.join(".", "Logs")  # This moves one directory up
    log_date_dir = os.path.join(log_base_dir, date_str)
    os.makedirs(log_date_dir, exist_ok=True)

    # Log file path
    log_file_name = f"Log {time_str} ({SERVICE_NAME}).log"
    log_path = os.path.join(log_date_dir, log_file_name)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # === GLOBAL EXCEPTION HOOK ===
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Let Ctrl+C interrupt normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

def start_logging(TEMPLATE_SERVICE):
    configure_log()
    delete_oldest_folder_if_limit_exceeded()
    cmd_top_logo()
    logging_top_logo(TEMPLATE_SERVICE)
    start_time = datetime.now()
    logging.info('Start time: %s', start_time)
    return start_time

def finish_logging(start_time):
    finish_time = datetime.now()
    logging.info('Finish time: %s', finish_time)
    logging.info('Time duration: %s', finish_time - start_time)