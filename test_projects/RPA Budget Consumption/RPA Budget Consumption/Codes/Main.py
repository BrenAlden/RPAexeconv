from Controller.Logging_Controller import start_logging, finish_logging
from Controller.Browser_Setup import start_browser
from Controller.Navigation_Handler import login_and_go_to_rpa
from Controller.Download_Handler import execute_report_download, move_downloaded_file
from View.Menu import cmd_top_logo
from Config import SERVICE_NAME, USERNAME
from Setup import fetch_password
from pathlib import Path
import logging
import sys
import os

from Controller.Logging_Controller import start_logging, finish_logging
from Controller.Browser_Setup import start_browser
from Controller.Navigation_Handler import login_and_go_to_rpa
from Controller.Download_Handler import execute_report_download
from Controller.Data_Handler import handle_preview_data, get_budget_summary
from Controller.Email_Sender import send_budget_emails

# Start Logging
log_start_time = start_logging(SERVICE_NAME) # Start the logging
PASSWORD = fetch_password(log_start_time, SERVICE_NAME, USERNAME) # COMMENT THIS LINE IF THE PROJECT DOESN'T REQUIRE ANY CREDENTIALS

def show_menu():
    print("1. Download File and Process Data")
    print("2. Preview Data")
    print("3. Send to Email")
    print("4. Exit")
    return input("Choose menu (1-4): ")

def main():
    TARGET_URL = "http://adm-bi.daihatsu.astra.co.id/reports/powerbi/Budget/Budget%20Consumption%20Report_V2"
    base_path = str(Path(__file__).resolve().parents[2])
    INPUT_FOLDER = os.path.join(base_path, "Output RPA Budget Consumption", "Output", "Excel")
    
    while True:
        choice = show_menu()

        if choice == '1':
            logging.info("Starting Download & Process sequence...")
            driver = start_browser()
            
            if login_and_go_to_rpa(driver, TARGET_URL):
                if execute_report_download(driver):
                    driver.quit()
                    processed_file = move_downloaded_file(INPUT_FOLDER)
                    if processed_file:
                        logging.info("File is ready for processing.")
                

        elif choice == '2':
            logging.info("Displaying Data Preview...")
            handle_preview_data(INPUT_FOLDER, cmd_top_logo)

        elif choice == '3':
            logging.info("Starting division-wise email distribution...")
            summary_data = get_budget_summary(INPUT_FOLDER)
            if summary_data is not None:
                send_budget_emails(summary_data)
                print("\n[SUCCESS] All emails have been processed.")
            else:
                print("\n[!] Failed to generate summary data.")

        elif choice == '4':
            logging.info("Exiting Program.")
            print("Sampai jumpa, Bren!")
            finish_logging(log_start_time)
            sys.exit()

        else:
            print("Pilihan tidak valid, silakan coba lagi.")

if __name__ == "__main__":
    main()